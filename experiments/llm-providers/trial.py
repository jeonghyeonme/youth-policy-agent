"""무료 LLM 후보를 같은 질문으로 시험한다 (Q5, D3).

1회차(해석): 직접 만든 질문 10개를 조건 JSON으로 바꾼다. 정답과 비교해 맞힌 비율을 센다.
2회차(설명): 수집한 공개 정책 3건을 사용자 유형 3개에게 설명한다. 사람이 읽고 판단한다.

실행: 저장소 루트에서 `python3 experiments/llm-providers/trial.py` (Windows는 `py ...`)
결과 요약만 보기: `--report`
키는 `.env`의 GROQ_API_KEY, MISTRAL_API_KEY에서 읽고, 키가 없는 업체는 건너뛴다.
결과는 results/<모델>/<사례>.json에 저장한다. 이미 저장된 사례는 다시 호출하지 않는다.
입력은 직접 만든 문장과 공개 정책 텍스트뿐이라 커밋해도 된다.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "api-survey"))
from check_keys import load_env  # noqa: E402
from normalize import SOURCES  # noqa: E402

RESULTS = HERE / "results"
CALL_GAP_SECONDS = 3
DAILY_TOKENS = 200_000

MODELS = [
    {"name": "groq__gpt-oss-120b", "key_env": "GROQ_API_KEY",
     "url": "https://api.groq.com/openai/v1/chat/completions",
     "body": {"model": "openai/gpt-oss-120b", "reasoning_effort": "low", "include_reasoning": False},
     "schema": "strict"},
    {"name": "groq__gpt-oss-20b", "key_env": "GROQ_API_KEY",
     "url": "https://api.groq.com/openai/v1/chat/completions",
     "body": {"model": "openai/gpt-oss-20b", "reasoning_effort": "low", "include_reasoning": False},
     "schema": "strict"},
    {"name": "groq__qwen3.8-27b", "key_env": "GROQ_API_KEY",
     "url": "https://api.groq.com/openai/v1/chat/completions",
     "body": {"model": "qwen/qwen3.8-27b", "reasoning_effort": "none"},
     "schema": "strict"},
    {"name": "mistral__mistral-small", "key_env": "MISTRAL_API_KEY",
     "url": "https://api.mistral.ai/v1/chat/completions",
     "body": {"model": "mistral-small-latest"},
     "schema": "json_object"},
]

CATEGORIES = ["일자리", "주거", "교육", "복지문화", "참여권리"]
REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원",
           "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
JOB_STATUS = ["재직자", "자영업자", "미취업자", "프리랜서", "일용근로자", "(예비)창업자", "단기근로자", "영농종사자"]
EDUCATION = ["고졸 미만", "고교 재학", "고졸 예정", "고교 졸업", "대학 재학", "대졸 예정", "대학 졸업", "석·박사"]


def nullable(enum):
    return {"anyOf": [{"type": "string", "enum": enum}, {"type": "null"}]}


CONDITION_SCHEMA = {
    "type": "object",
    "properties": {
        "categories": {"type": "array", "items": {"type": "string", "enum": CATEGORIES}},
        "age": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "region": nullable(REGIONS),
        "job_status": nullable(JOB_STATUS),
        "education": nullable(EDUCATION),
    },
    "required": ["categories", "age", "region", "job_status", "education"],
    "additionalProperties": False,
}

INTERPRET_PROMPT = (
    "너는 청년 정책 검색 조건을 뽑는 도구다. 사용자 문장에서 아래 JSON만 출력한다.\n"
    f"- categories: 관련 정책 분야. {CATEGORIES} 중 하나 이상\n"
    "- age: 문장에 나온 만 나이. 없으면 null\n"
    f"- region: 사는 시도. {REGIONS} 중 하나. 없으면 null\n"
    f"- job_status: {JOB_STATUS} 중 하나. 없으면 null\n"
    f"- education: {EDUCATION} 중 하나. 없으면 null\n"
    "문장에 없는 값은 추측하지 말고 null로 둔다."
)

EXPLAIN_PROMPT = (
    "너는 청년 정책 안내 도우미다. 사용자 조건과 정책 정보를 받아 정책마다 3문장 이내로 설명한다.\n"
    "1. 어떤 지원인지 2. 주어진 자격조건 글로 볼 때 이 사용자가 해당될 가능성 3. 사용자가 직접 확인할 점.\n"
    "자격조건 글에 없는 내용은 지어내지 말고 '공고에서 확인 필요'라고 쓴다. 한국어 존댓말로 쓴다."
)

# 직접 만든 질문이다. 정답 categories는 맞다고 볼 수 있는 분야의 집합이다.
INTERPRET_CASES = [
    ("q01", "서울 사는 27살인데 월세가 너무 부담돼요",
     {"categories": {"주거"}, "age": 27, "region": "서울", "job_status": None, "education": None}),
    ("q02", "대학 졸업하고 1년째 취업 준비 중이에요. 지원받을 수 있는 거 있나요?",
     {"categories": {"일자리"}, "age": None, "region": None, "job_status": "미취업자", "education": "대학 졸업"}),
    ("q03", "부산에서 작은 회사 다니는 25살 직장인입니다. 목돈 모으는 방법 없을까요",
     {"categories": {"복지문화"}, "age": 25, "region": "부산", "job_status": "재직자", "education": None}),
    ("q04", "창업하고 싶은데 초기 자금 지원해 주는 데 있어요? 대구 살아요",
     {"categories": {"일자리"}, "age": None, "region": "대구", "job_status": "(예비)창업자", "education": None}),
    ("q05", "고등학교 졸업했고 경기도에 사는데 직업훈련 받고 싶어요",
     {"categories": {"교육", "일자리"}, "age": None, "region": "경기", "job_status": None, "education": "고교 졸업"}),
    ("q06", "인천 사는 29살 프리랜서예요. 건강검진이나 마음 상담 지원 같은 거 있을까요?",
     {"categories": {"복지문화"}, "age": 29, "region": "인천", "job_status": "프리랜서", "education": None}),
    ("q07", "학자금 대출 이자 때문에 힘들어요. 대학 다니고 있고 광주 살아요",
     {"categories": {"교육"}, "age": None, "region": "광주", "job_status": None, "education": "대학 재학"}),
    ("q08", "대전 사는 31살인데 전세 보증금 대출 같은 거 알려 주세요",
     {"categories": {"주거"}, "age": 31, "region": "대전", "job_status": None, "education": None}),
    ("q09", "청년 정책 정하는 위원회 같은 데 참여해 보고 싶어요",
     {"categories": {"참여권리"}, "age": None, "region": None, "job_status": None, "education": None}),
    ("q10", "제주도에서 일하는 24살인데 이직 준비하면서 교육도 받고 싶어요",
     {"categories": {"일자리", "교육"}, "age": 24, "region": "제주", "job_status": "재직자", "education": None}),
]

PERSONAS = [
    ("e01", {"age": 27, "region": "서울", "job_status": "미취업자", "education": "대학 졸업"}),
    ("e02", {"age": 24, "region": "경기", "job_status": "재직자", "education": "고교 졸업"}),
    ("e03", {"age": 31, "region": "부산", "job_status": "프리랜서", "education": "대학 졸업"}),
]


def explain_policies(persona, offset, count=3):
    """청년 대상이고 서술형 자격조건이 있는 공개 정책 중 사용자 지역에 맞는 것을, 사용자 유형마다 다르게 고른다."""
    rows = [r for source in ("welfare-central", "welfare-local") for r in SOURCES[source]()]
    picked = [r for r in sorted(rows, key=lambda r: r["id"])
              if r["eligibility"]["texts"] and "청년" in (r["eligibility"]["life_stages"] or [])
              and (r["regions"] == ["전국"] or persona["region"] in r["regions"])]
    return [{"title": r["title"], "summary": r["summary"], "eligibility": r["eligibility"]["texts"],
             "benefit": r["benefit"]} for r in picked[offset * count:(offset + 1) * count]]


def post(model, key, messages, response_format, max_tokens):
    body = {**model["body"], "messages": messages, "max_completion_tokens": max_tokens}
    if model["name"].startswith("mistral"):
        body["max_tokens"] = body.pop("max_completion_tokens")
    if response_format:
        body["response_format"] = response_format
    data = json.dumps(body).encode()
    for attempt in range(4):
        req = urllib.request.Request(model["url"], data=data, headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "User-Agent": "youth-policy-agent/trial"})
        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                return 200, json.loads(res.read()), round(time.time() - started, 2)
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", errors="replace")
            if e.code == 429 and attempt < 3:
                wait = float(e.headers.get("retry-after") or 20)
                print(f"    한도 초과(429), {wait:.0f}초 기다린다")
                time.sleep(wait)
                continue
            return e.code, {"error": text[:500]}, None
        except urllib.error.URLError as e:
            return None, {"error": f"연결 실패: {e.reason}"}, None
    return 429, {"error": "재시도 횟수 초과"}, None


def interpret_format(model):
    if model["schema"] == "strict":
        return {"type": "json_schema",
                "json_schema": {"name": "conditions", "strict": True, "schema": CONDITION_SCHEMA}}
    return {"type": "json_object"}


def run_case(model, key, case_id, messages, response_format, max_tokens, meta):
    path = RESULTS / model["name"] / f"{case_id}.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8"))["status"] == 200:
        return False
    status, response, latency = post(model, key, messages, response_format, max_tokens)
    content = None
    if status == 200:
        content = response["choices"][0]["message"].get("content")
    record = {"model": model["name"], "case": case_id, "status": status, "latency_s": latency,
              "messages": messages, "content": content,
              "usage": response.get("usage") if status == 200 else None,
              "error": response.get("error") if status != 200 else None, **meta}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {case_id}: HTTP {status}" + (f", {record['usage'].get('total_tokens')} 토큰" if record["usage"] else ""))
    return True


def run(model, key):
    print(f"## {model['name']}")
    for case_id, text, _ in INTERPRET_CASES:
        messages = [{"role": "system", "content": INTERPRET_PROMPT}, {"role": "user", "content": text}]
        if run_case(model, key, case_id, messages, interpret_format(model), 1024, {"kind": "interpret"}):
            time.sleep(CALL_GAP_SECONDS)
    for offset, (case_id, persona) in enumerate(PERSONAS):
        user = json.dumps({"사용자 조건": persona, "정책": explain_policies(persona, offset)}, ensure_ascii=False)
        messages = [{"role": "system", "content": EXPLAIN_PROMPT}, {"role": "user", "content": user}]
        if run_case(model, key, case_id, messages, None, 2048, {"kind": "explain"}):
            time.sleep(CALL_GAP_SECONDS * 4)


def score(predicted, gold):
    hits = {"categories": bool(set(predicted.get("categories") or []) & gold["categories"])}
    for field in ("age", "region", "job_status", "education"):
        hits[field] = predicted.get(field) == gold[field]
    return hits


def report():
    gold = {case_id: g for case_id, _, g in INTERPRET_CASES}
    for model_dir in sorted(p for p in RESULTS.glob("*") if p.is_dir()):
        records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(model_dir.glob("*.json"))]
        interpret = [r for r in records if r["kind"] == "interpret" and r["status"] == 200]
        explain = [r for r in records if r["kind"] == "explain" and r["status"] == 200]
        failed = [r["case"] for r in records if r["status"] != 200]
        fields = {"categories": 0, "age": 0, "region": 0, "job_status": 0, "education": 0}
        invalid = 0
        for r in interpret:
            try:
                hits = score(json.loads(r["content"]), gold[r["case"]])
            except (TypeError, ValueError):
                invalid += 1
                continue
            for k, v in hits.items():
                fields[k] += v
        avg = lambda rs: sum(r["usage"]["total_tokens"] for r in rs) / len(rs) if rs else 0  # noqa: E731
        per_question = avg(interpret) + avg(explain)
        print(f"## {model_dir.name}")
        print(f"   해석 {len(interpret)}건: " + " · ".join(f"{k} {v}/{len(interpret)}" for k, v in fields.items())
              + (f" · JSON 오류 {invalid}" if invalid else ""))
        print(f"   평균 토큰: 해석 {avg(interpret):.0f}, 설명 {avg(explain):.0f}, 질문당 {per_question:.0f}"
              + (f" → 하루 {DAILY_TOKENS // per_question:.0f}개 (하루 {DAILY_TOKENS:,} 토큰 기준)" if per_question else ""))
        if failed:
            print(f"   실패: {', '.join(failed)}")
        if explain:
            print(f"   설명 원문: {', '.join(str(model_dir / (r['case'] + '.json')) for r in explain)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if not args.report:
        load_env()
        for model in MODELS:
            key = os.environ.get(model["key_env"], "")
            if not key:
                print(f"[SKIP] {model['name']}: {model['key_env']}가 비어 있다")
                continue
            run(model, key)
        print()
    report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
