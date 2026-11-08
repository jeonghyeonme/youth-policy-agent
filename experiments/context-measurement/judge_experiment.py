"""Q4 실험: 서술형 자격 조건을 LLM(Groq gpt-oss-120b, D7)이 얼마나 맞게 판단하는지 정답표와 비교한다.

1) 사람이 로컬에서 실행해 Groq를 부른다(질문 A·B 각 1회, 총 2회). 결과는 samples/groq/에 저장된다.
       py experiments/context-measurement/judge_experiment.py --run
2) 누구나 저장된 결과로 채점한다(API 호출 없음).
       python3 experiments/context-measurement/judge_experiment.py

정책은 D9 3단계로 고른 상위 8건이다(rank_experiment.py와 같은 함수). 정답표: q4/labels.json.
사용자 정보는 가상 인물이다. 실제 사용자 값이 아니다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fetch_samples  # noqa: E402  (.env 읽기·키 지우기 재사용)
import rank_experiment as rank  # noqa: E402

OUT = HERE / "samples" / "groq"
LABELS = json.loads((HERE / "q4" / "labels.json").read_text(encoding="utf-8"))
URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
VERDICTS = ("가능", "불가", "확인 필요")

# 코드정의서(api-survey.md)에서 판단에 필요한 것만. 서버가 거르지 않은 코드라 LLM에 이름으로 준다.
CODES = {
    "0049001": "고졸 미만", "0049002": "고교 재학", "0049003": "고졸 예정", "0049004": "고교 졸업",
    "0049005": "대학 재학", "0049006": "대졸 예정", "0049007": "대학 졸업", "0049008": "석·박사",
    "0049009": "기타", "0049010": "제한없음",
    "0055001": "기혼", "0055002": "미혼", "0055003": "제한없음",
    "0014001": "중소기업", "0014002": "여성", "0014003": "기초생활수급자", "0014004": "한부모가정",
    "0014005": "장애인", "0014006": "농업인", "0014007": "군인", "0014008": "지역인재", "0014009": "기타",
    "0014010": "제한없음",
    "0013001": "재직자", "0013002": "자영업자", "0013003": "미취업자", "0013004": "프리랜서",
    "0013005": "일용근로자", "0013006": "(예비)창업자", "0013007": "단기근로자", "0013008": "영농종사자",
    "0013009": "기타", "0013010": "제한없음",
}
TEXT_FIELDS = ("plcyNm", "plcyExplnCn", "plcySprtCn", "operInstCdNm", "earnEtcCn", "addAplyQlfcCndCn", "ptcpPrpTrgtCn")

SYSTEM = """너는 한국 청년 정책 자격 판정 도우미다. 사용자 정보와 정책 목록을 받으면 정책마다 사용자가 지금 신청할 수 있는지 판정한다.
- verdict는 "가능", "불가", "확인 필요" 중 하나다.
- 사용자 정보만으로 판단할 수 없으면 "확인 필요"로 하고, ask_user에 사용자에게 물을 질문을 한 문장으로 쓴다. 판단할 수 있으면 ask_user는 null이다.
- 기업·사업주·기관이 신청하는 사업이면 "불가"다(청년 개인이 지금 신청할 수 없다).
- 정책 원문에 없는 조건을 지어내지 않는다.
JSON 하나만 출력한다: {"results": [{"plcyNm": "...", "verdict": "...", "reason": "한 문장", "ask_user": "..." 또는 null}]}"""


def decode(codes: str) -> str:
    return ", ".join(CODES.get(c.strip(), c.strip()) for c in codes.split(",") if c.strip())


def policy_for_llm(p: rank.Policy) -> dict[str, str]:
    item = {f: p[f].strip() for f in TEXT_FIELDS if p[f].strip()}
    lo, hi = p["sprtTrgtMinAge"].strip(), p["sprtTrgtMaxAge"].strip()
    item["나이"] = f"{lo}~{hi}세" if hi not in ("", "0") else "제한 없음"
    item["취업요건"] = decode(p["jobCd"])
    item["학력요건"] = decode(p["schoolCd"])
    item["혼인요건"] = decode(p["mrgSttsCd"])
    item["특화요건"] = decode(p["sbizCd"])
    return item


def selected(key: str) -> list[rank.Policy]:
    """D9 3단계 상위 8건. A는 키워드로 좁힌 A' 샘플을 쓴다."""
    q = {"A": rank.QUESTIONS[1], "B": rank.QUESTIONS[2]}[key]
    candidates = [p for p in rank.load(q.sample) if rank.eligible(p, q) and rank.is_open(p)]
    return rank.RANKERS["조합(추천)"](candidates, q)[:8]


def call_groq(key: str, api_key: str) -> dict:
    policies = [policy_for_llm(p) for p in selected(key)]
    user = f"사용자 정보: {LABELS['personas'][key]}\n\n정책 목록:\n{json.dumps(policies, ensure_ascii=False)}"
    body = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            "temperature": 0, "response_format": {"type": "json_object"}}
    req = urllib.request.Request(URL, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                                          "User-Agent": "youth-policy-agent-q4"})
    for attempt in (1, 2):
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                data = json.loads(res.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 1:  # 분당 토큰 한도. 한 번만 기다렸다 다시 부른다
                wait = int(e.headers.get("retry-after") or 60)
                print(f"  분당 한도에 걸려 {wait}초 기다린다")
                time.sleep(wait)
                continue
            return {"error": f"HTTP {e.code}", "body": fetch_samples.scrub(e.read().decode("utf-8", "replace")[:500], [api_key])}
    return {"seconds": round(time.monotonic() - started, 1), "usage": data.get("usage"),
            "content": data["choices"][0]["message"]["content"], "policies_sent": len(policies)}


def run() -> int:
    env = {**fetch_samples.load_env(fetch_samples.ROOT / ".env")}
    api_key = env.get("GROQ_API_KEY") or __import__("os").environ.get("GROQ_API_KEY")
    if not api_key:
        print(".env에 GROQ_API_KEY가 없다.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for key in ("A", "B"):
        path = OUT / f"judge_{key}.json"
        if path.exists():
            print(f"  - {path.name}: 이미 있음, 건너뜀")
            continue
        result = call_groq(key, api_key)
        path.write_text(fetch_samples.scrub(json.dumps(result, ensure_ascii=False, indent=2), [api_key]), encoding="utf-8")
        print(f"  {'✗' if 'error' in result else '✓'} {path.name}: {result.get('error') or result.get('usage')}")
    return 0


def score() -> int:
    total = correct = unsafe = 0
    for key in ("A", "B"):
        path = OUT / f"judge_{key}.json"
        if not path.exists():
            print(f"{path.name} 없음. 먼저 --run을 로컬에서 실행한다.")
            return 1
        result = json.loads(path.read_text(encoding="utf-8"))
        if "error" in result:
            print(f"{key}: 호출 실패 {result['error']} {result.get('body', '')[:200]}")
            continue
        answers = {r["plcyNm"].strip(): r for r in json.loads(result["content"])["results"]}
        print(f"\n## 질문 {key} — {result['seconds']}초, 토큰 {result['usage']}")
        print("| 정책 | 정답 | LLM | 맞음 | LLM 이유 | 사용자에게 물을 질문 |")
        print("| --- | --- | --- | --- | --- | --- |")
        for name, (truth, _) in LABELS["labels"][key].items():
            got = answers.get(name.strip(), {})
            verdict = got.get("verdict", "(없음)")
            ok = verdict == truth
            # 정답이 불가·확인 필요인데 LLM이 '가능'이라 하면 사용자를 잘못 이끈다
            bad = verdict == "가능" and truth != "가능"
            total, correct, unsafe = total + 1, correct + ok, unsafe + bad
            mark = "O" if ok else ("X(위험)" if bad else "X")
            print(f"| {name.strip()[:24]} | {truth} | {verdict} | {mark} | {got.get('reason', '')[:50]} | {got.get('ask_user') or ''} |")
    print(f"\n일치 {correct}/{total}, 정답이 가능이 아닌데 가능이라 한 것 {unsafe}건")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="store_true", help="Groq를 불러 결과를 저장한다(사람이 로컬에서)")
    args = parser.parse_args()
    return run() if args.run else score()


if __name__ == "__main__":
    sys.exit(main())
