"""청년 정책안을 질문부터 답까지 실제로 돌려 토큰과 정책 선택을 잰다 (Q7).

법률 정보안 v5(`experiments/legal-tokens/two_call.py`)와 같은 조건으로 맞췄다: Groq gpt-oss-120b, 질문당 LLM 2회(D3).
  1회차: 자유 문장 → 조건(분야·나이·지역·취업상태·학력) + 검색 낱말(JSON). 청년 정책 브랜치 시험 v2 프롬프트에 검색 낱말만 더했다.
  서버: 코드 조건으로 거르고(마감 제외, 생애주기에 청년이 없는 복지 서비스 제외), BM25(글자 두 개 단위)로 순위를 매기고, 같은 이름의 정책을 하나로 합쳐 상위 8건을 고른다.
  2회차: 후보 8건 중 질문에 맞는 정책을 최대 3개 고르고 설명한다(JSON). 후보 고르기를 2회차에 합쳐 호출 수를 2회로 지킨다.

데이터: policies.json.gz. 청년 정책 브랜치(claude/exciting-goldberg-y71yhi, 839b5ff)의 수집 샘플을 normalize.py로 변환한 4,598건.
질문: 청년 정책 팀이 LLM 시험에 쓴 질문 10개(같은 브랜치 trial.py의 INTERPRET_CASES)와 정답 조건.

실행: 저장소 루트에서 `python3 experiments/youth-e2e/pipeline.py` (Windows는 `py ...`)
결과 요약만 보기: `--report` · 흐름만 확인(키·네트워크 없음): `--fake`
서버 단계만(LLM 없이 정답 조건으로): `--offline`
키는 `.env`의 GROQ_API_KEY만 쓴다. 공공 API는 부르지 않는다.
"""

import argparse
import gzip
import json
import math
import os
import re
import statistics
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "legal-tokens"))
import trial  # noqa: E402
from trial import CALL_GAP_SECONDS, DAILY_TOKENS, MODELS, TARGET_PER_DAY, load_env, post_groq  # noqa: E402

VERSION = "y1"
TOP_K = 8
MAX_PICKS = 3

CATEGORY_GUIDE = {
    "일자리": "취업, 구직, 재직자 지원, 창업",
    "주거": "주택, 기숙사, 전월세, 주거급여",
    "교육·직업훈련": "역량 강화, 직업훈련, 교육비·학자금, 온라인 교육",
    "금융·복지·문화": "저축·자산형성, 금융 지원, 취약계층 지원, 건강, 문화활동, 예술인 지원",
    "참여·기반": "청년 참여, 위원회, 정책 기반, 국제교류, 권익 보호",
}
REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원",
           "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
JOB_STATUS = ["재직자", "자영업자", "미취업자", "프리랜서", "일용근로자", "(예비)창업자", "단기근로자", "영농종사자"]
EDUCATION = ["고졸 미만", "고교 재학", "고졸 예정", "고교 졸업", "대학 재학", "대졸 예정", "대학 졸업", "석·박사"]

# 청년 정책 팀의 질문과 정답 조건 (claude/exciting-goldberg-y71yhi experiments/llm-providers/trial.py).
CASES = [
    ("q01", "서울 사는 27살인데 월세가 너무 부담돼요",
     {"categories": {"주거"}, "age": 27, "region": "서울", "job_status": None, "education": None}),
    ("q02", "대학 졸업하고 1년째 취업 준비 중이에요. 지원받을 수 있는 거 있나요?",
     {"categories": {"일자리"}, "age": None, "region": None, "job_status": "미취업자", "education": "대학 졸업"}),
    ("q03", "부산에서 작은 회사 다니는 25살 직장인입니다. 목돈 모으는 방법 없을까요",
     {"categories": {"금융·복지·문화"}, "age": 25, "region": "부산", "job_status": "재직자", "education": None}),
    ("q04", "창업하고 싶은데 초기 자금 지원해 주는 데 있어요? 대구 살아요",
     {"categories": {"일자리"}, "age": None, "region": "대구", "job_status": "(예비)창업자", "education": None}),
    ("q05", "고등학교 졸업했고 경기도에 사는데 직업훈련 받고 싶어요",
     {"categories": {"교육·직업훈련", "일자리"}, "age": None, "region": "경기", "job_status": None, "education": "고교 졸업"}),
    ("q06", "인천 사는 29살 프리랜서예요. 건강검진이나 마음 상담 지원 같은 거 있을까요?",
     {"categories": {"금융·복지·문화"}, "age": 29, "region": "인천", "job_status": "프리랜서", "education": None}),
    ("q07", "학자금 대출 이자 때문에 힘들어요. 대학 다니고 있고 광주 살아요",
     {"categories": {"교육·직업훈련"}, "age": None, "region": "광주", "job_status": None, "education": "대학 재학"}),
    ("q08", "대전 사는 31살인데 전세 보증금 대출 같은 거 알려 주세요",
     {"categories": {"주거"}, "age": 31, "region": "대전", "job_status": None, "education": None}),
    ("q09", "청년 정책 정하는 위원회 같은 데 참여해 보고 싶어요",
     {"categories": {"참여·기반"}, "age": None, "region": None, "job_status": None, "education": None}),
    ("q10", "제주도에서 일하는 24살인데 이직 준비하면서 교육도 받고 싶어요",
     {"categories": {"일자리", "교육·직업훈련"}, "age": 24, "region": "제주", "job_status": "재직자", "education": None}),
]

INTERPRET_PROMPT = (
    "너는 청년 정책 검색 조건을 뽑는 도구다. 사용자 문장에서 아래 JSON만 출력한다.\n"
    "- categories: 관련 정책 분야. 아래 중 하나 이상\n"
    + "".join(f"  - {name}: {guide}\n" for name, guide in CATEGORY_GUIDE.items())
    + "- age: 문장에 나온 만 나이. 없으면 null\n"
    f"- region: 사는 시도. {REGIONS} 중 하나. 없으면 null\n"
    f"- job_status: {JOB_STATUS} 중 하나. 취업 준비 중이거나 구직 중이면 미취업자. 없으면 null\n"
    f"- education: {EDUCATION} 중 하나. 없으면 null\n"
    "- keywords: 정책 이름이나 설명에 나올 법한 검색 낱말 3~6개. 사용자가 쓴 말과 그 말을 정책에서 부르는 이름을 함께 넣는다"
    "(예: 목돈 → 자산형성, 저축, 적금). 사람 이름이나 연락처는 넣지 않는다\n"
    "문장에 없는 값은 추측하지 말고 null로 둔다."
)

PICK_PROMPT = (
    "너는 청년 정책 안내 도우미다. 사용자 질문과 조건, 서버가 고른 정책 후보를 받는다.\n"
    f"후보 중 질문에 실제로 도움이 되는 정책을 최대 {MAX_PICKS}개 고른다. 맞는 후보가 없으면 picks를 빈 배열로 두고 none_reason에 이유를 쓴다.\n"
    "고른 정책마다 explanation을 3문장 이내로 쓴다: 1. 어떤 지원인지 2. 주어진 자격조건 글로 볼 때 이 사용자가 해당될 가능성 3. 직접 확인할 점.\n"
    "자격조건 글에 없는 내용은 지어내지 말고 '공고에서 확인 필요'라고 쓴다. "
    "사용자 조건에 없는 정보(성별, 장애 여부, 소득, 가구, 보호 이력 등)는 모른다고 보고, 있다거나 없다고 가정하지 않는다.\n"
    "한국어 존댓말로만 쓰고, 한자나 다른 언어 낱말을 섞지 않는다."
)


def nullable(enum):
    return {"anyOf": [{"type": "string", "enum": enum}, {"type": "null"}]}


INTERPRET_SCHEMA = {"type": "json_schema", "json_schema": {"name": "conditions", "strict": True, "schema": {
    "type": "object",
    "properties": {
        "categories": {"type": "array", "items": {"type": "string", "enum": list(CATEGORY_GUIDE)}},
        "age": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "region": nullable(REGIONS),
        "job_status": nullable(JOB_STATUS),
        "education": nullable(EDUCATION),
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["categories", "age", "region", "job_status", "education", "keywords"],
    "additionalProperties": False}}}

PICK_SCHEMA = {"type": "json_schema", "json_schema": {"name": "picks", "strict": True, "schema": {
    "type": "object",
    "properties": {
        "picks": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "explanation": {"type": "string"}},
            "required": ["id", "explanation"], "additionalProperties": False}},
        "none_reason": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["picks", "none_reason"], "additionalProperties": False}}}

OLD_CATEGORY = {"교육": "교육·직업훈련", "복지문화": "금융·복지·문화", "참여권리": "참여·기반"}
STOP = set("요 은 는 이 가 을 를 에 에서 있나요 싶어요 주세요 알려 같은 데 하는 해요 있어요 없을까요 사는 살아요 하고 있을까요 거 수".split())


def load_policies():
    with gzip.open(HERE / "policies.json.gz", "rt", encoding="utf-8") as f:
        return json.load(f)


def passes(r, cond):
    """코드 조건으로 거른다. 정책 쪽 값이 비어 있으면(제한 없음·정보 없음) 거르지 않는다."""
    if r["period"]["status"] == "closed":
        return False
    cats = {OLD_CATEGORY.get(c, c) for c in r["categories"]}
    want = set(cond.get("categories") or [])
    if cats and want and not (cats & want):
        return False
    region = cond.get("region")
    if region and r["regions"] and r["regions"] != ["전국"] and region not in r["regions"]:
        return False
    age, a = cond.get("age"), r["eligibility"]["age"]
    if age is not None and a:
        if a.get("min") is not None and age < a["min"]:
            return False
        if a.get("max") is not None and age > a["max"]:
            return False
    stages = r["eligibility"].get("life_stages")
    if stages and "청년" not in stages:
        return False
    for field in ("job_status", "education"):
        mine, allowed = cond.get(field), r["eligibility"][field]
        if mine and allowed and mine not in allowed and "제한없음" not in allowed:
            return False
    return True


def bigrams(text):
    out = []
    for run in re.findall(r"[가-힣A-Za-z0-9]+", text or ""):
        out.extend(run[i:i + 2] for i in range(max(1, len(run) - 1)))
    return out


def query_terms(question, keywords):
    words = [w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", question) if w not in STOP]
    return bigrams(" ".join(words + list(keywords or [])))


def rank(candidates, terms, k1=1.2, b=0.75):
    """BM25. 문서는 제목(두 번) + 요약 + 지원내용의 글자 두 개 단위."""
    docs = [bigrams(f"{r['title']} {r['title']} {r['summary'] or ''} {r['benefit'] or ''}") for r in candidates]
    if not docs:
        return []
    avg = sum(map(len, docs)) / len(docs)
    df = Counter(t for d in docs for t in set(d))
    n = len(docs)
    qt = Counter(terms)
    scored = []
    for r, d in zip(candidates, docs):
        tf = Counter(d)
        s = 0.0
        for t, q in qt.items():
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += q * idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg))
        scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    return [r for s, r in scored if s > 0]


def title_key(title):
    t = re.sub(r"\(.*?\)|\[.*?\]|\d{2,4}년도?|\s", "", title or "")
    return re.sub(r"[^가-힣A-Za-z0-9]", "", t)


def dedupe(ranked):
    seen, out = set(), []
    for r in ranked:
        key = title_key(r["title"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def card(r):
    """2회차에 넘기는 후보 한 건. 길이를 잘라 토큰을 묶는다."""
    elig = " / ".join(f"{t['label']}: {t['text']}" for t in r["eligibility"]["texts"])
    return {"id": r["id"], "정책명": r["title"], "요약": (r["summary"] or "")[:150],
            "지원내용": (r["benefit"] or "")[:150], "자격조건": elig[:350],
            "나이": r["eligibility"]["age"], "지역": r["regions"], "마감": r["period"]["end"]}


def call(llm, model_name, messages, max_tokens, response_format):
    body = {**MODELS[model_name], "messages": messages, "max_completion_tokens": max_tokens,
            "response_format": response_format}
    status, response, latency = llm(body)
    if status != 200:
        return {"status": status, "error": response.get("error"), "long_wait": bool(response.get("long_wait"))}, None
    return ({"status": 200, "latency_s": latency, "usage": response.get("usage")},
            response["choices"][0]["message"].get("content"))


def server_step(policies, question, cond, keywords):
    cand = [r for r in policies if passes(r, cond)]
    top = dedupe(rank(cand, query_terms(question, keywords)))[:TOP_K]
    return cand, top


def run_case(llm, policies, model_name, question):
    calls = []
    meta, content = call(llm, model_name, [{"role": "system", "content": INTERPRET_PROMPT},
                                           {"role": "user", "content": question}], 1024, INTERPRET_SCHEMA)
    calls.append({"step": 1, **meta})
    try:
        cond = json.loads(content) if content else None
    except ValueError:
        cond = None
    if not cond:
        return {"outcome": "error", "calls": calls}
    cand, top = server_step(policies, question, cond, cond.get("keywords"))
    user = json.dumps({"질문": question, "조건": {k: v for k, v in cond.items() if k != "keywords"},
                       "후보": [card(r) for r in top]}, ensure_ascii=False)
    meta, content = call(llm, model_name, [{"role": "system", "content": PICK_PROMPT},
                                           {"role": "user", "content": user}], 2048, PICK_SCHEMA)
    calls.append({"step": 2, **meta})
    record = {"conditions": cond, "candidates": len(cand),
              "top": [{"id": r["id"], "title": r["title"], "source": r["source"]} for r in top], "calls": calls}
    if meta["status"] != 200:
        return {**record, "outcome": "error"}
    try:
        picked = json.loads(content)
    except ValueError:
        return {**record, "outcome": "error", "raw": content}
    by_id = {r["id"]: r for r in top}
    record["picks"] = [{"id": p["id"], "title": by_id[p["id"]]["title"] if p["id"] in by_id else None,
                        "in_candidates": p["id"] in by_id, "explanation": p["explanation"]}
                       for p in picked["picks"][:MAX_PICKS]]
    record["none_reason"] = picked.get("none_reason")
    record["outcome"] = "answered"
    return record


def totals(calls):
    ok = [c for c in calls if c.get("usage")]
    t = {k: sum(c["usage"].get(k, 0) for c in ok) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    t["llm_calls"] = len(calls)
    return t


def run(models, cases, budget, results, llm_for, policies, gap):
    for model_name in models:
        print(f"## {model_name} ({VERSION})")
        spent = 0
        for case_id, question, _ in cases:
            path = results / VERSION / model_name / f"{case_id}.json"
            if path.exists() and json.loads(path.read_text(encoding="utf-8"))["outcome"] != "error":
                continue
            if spent >= budget:
                print(f"  이번 실행 토큰 {spent:,}이 상한 {budget:,}을 넘어 멈춘다")
                break
            result = run_case(llm_for(model_name), policies, model_name, question)
            waits = [c for c in result["calls"] if c.get("long_wait")]
            if waits:
                print(f"  {case_id}: 여기서 멈춘다. {waits[0]['error']}")
                print("  같은 명령을 다시 실행하면 저장되지 않은 사례부터 이어서 한다")
                return
            result["totals"] = totals(result["calls"])
            spent += result["totals"]["total_tokens"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": model_name, "case": case_id, "question": question, **result},
                                       ensure_ascii=False, indent=1), encoding="utf-8")
            picks = ", ".join(p["title"] or "(후보 밖)" for p in result.get("picks", []))
            print(f"  {case_id}: {result['outcome']}, 후보 {result.get('candidates', 0)}건, "
                  f"{result['totals']['total_tokens']:,} 토큰, 고른 정책 [{picks}]")
            time.sleep(gap)


def report(results):
    print(f"하루 {DAILY_TOKENS:,} 토큰 기준. 고른 정책이 질문에 맞는지는 사람이 판단한다")
    gold = {c[0]: c[2] for c in CASES}
    for model_dir in sorted((results / VERSION).glob("*")):
        records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(model_dir.glob("*.json"))]
        print(f"## {model_dir.name} · {VERSION}")
        for r in records:
            t = r["totals"]
            c = r.get("conditions") or {}
            g = gold.get(r["case"], {})
            hits = sum(c.get(k) == g.get(k) for k in ("age", "region", "job_status", "education"))
            hits += bool(set(c.get("categories") or []) & set(g.get("categories") or []))
            print(f"   {r['case']} {r['question']}")
            print(f"      {r['outcome']}, 조건 정답 {hits}/5, 후보 {r.get('candidates', 0)}건, "
                  f"1회차 {r['calls'][0].get('usage', {}).get('total_tokens', 0):,} + "
                  f"2회차 {t['total_tokens'] - r['calls'][0].get('usage', {}).get('total_tokens', 0):,} = {t['total_tokens']:,}")
            print(f"      검색 낱말: {', '.join(c.get('keywords') or [])}")
            for p in r.get("picks", []):
                print(f"      고름: {p['title'] or '(후보에 없는 id)'}")
            if r.get("outcome") == "answered" and not r.get("picks"):
                print(f"      고른 정책 없음: {r.get('none_reason')}")
        done = [r for r in records if r["outcome"] == "answered"]
        if done:
            tokens = [r["totals"]["total_tokens"] for r in done]
            avg = statistics.mean(tokens)
            per_day = DAILY_TOKENS // avg
            print(f"   답을 낸 {len(done)}건: 질문당 평균 {avg:,.0f}, 최대 {max(tokens):,} → 하루 약 {per_day:.0f}개 "
                  f"(목표 {TARGET_PER_DAY}개: {'기준 충족' if per_day >= TARGET_PER_DAY else '기준 미달'})")
            print(f"   후보에 없는 id를 고른 경우 {sum(not p['in_candidates'] for r in done for p in r.get('picks', []))}건")
        failed = [r["case"] for r in records if r["outcome"] != "answered"]
        if failed:
            print(f"   답을 못 낸 사례: {', '.join(failed)}")


def offline(policies, cases):
    """LLM 없이 정답 조건과 질문 낱말만으로 서버 단계를 돌린다. 검색 낱말 확장이 없는 기준선이다."""
    for case_id, question, gold in cases:
        cand, top = server_step(policies, question, {**gold, "categories": sorted(gold["categories"])}, [])
        print(f"== {case_id} {question} → 후보 {len(cand)}건")
        for r in top[:MAX_PICKS]:
            print(f"   - [{r['source']}] {r['title']}")


def fake_llm_for(model_name):
    def llm(body):
        prompt = sum(len(m["content"]) for m in body["messages"]) // 2
        if body["response_format"]["json_schema"]["name"] == "conditions":
            content = json.dumps({"categories": ["주거"], "age": 27, "region": "서울", "job_status": None,
                                  "education": None, "keywords": ["월세", "주거비", "임차"]}, ensure_ascii=False)
        else:
            ids = re.findall(r'"id": "([^"]+)"', body["messages"][-1]["content"])
            content = json.dumps({"picks": [{"id": ids[0], "explanation": "가짜 설명"},
                                            {"id": "없는:id", "explanation": "가짜"}], "none_reason": None},
                                 ensure_ascii=False)
        return 200, {"choices": [{"message": {"content": content}}],
                     "usage": {"prompt_tokens": prompt, "completion_tokens": 50, "total_tokens": prompt + 50}}, 0.0
    return llm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="저장된 결과로 요약만 본다")
    parser.add_argument("--fake", action="store_true", help="키·네트워크 없이 흐름만 확인한다. 임시 폴더에 쓴다")
    parser.add_argument("--offline", action="store_true", help="LLM 없이 정답 조건으로 서버 단계만 본다")
    parser.add_argument("--models", default="gpt-oss-120b", help=f"쉼표로 구분. 후보: {', '.join(MODELS)}")
    parser.add_argument("--cases", default=",".join(c[0] for c in CASES), help="쉼표로 구분한 사례 id")
    parser.add_argument("--max-wait", type=int, default=trial.LONG_WAIT_SECONDS,
                        help="Groq가 이보다 오래(초) 기다리라고 하면 멈춘다")
    parser.add_argument("--budget", type=int, default=150_000, help="모델마다 이번 실행에서 쓸 토큰 상한")
    args = parser.parse_args()
    trial.LONG_WAIT_SECONDS = args.max_wait

    results = HERE / "results"
    if args.fake:
        results = Path(tempfile.mkdtemp(prefix="youth-e2e-"))
    if args.report:
        report(results)
        return 0
    wanted = {c.strip() for c in args.cases.split(",")}
    cases = [c for c in CASES if c[0] in wanted]
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if any(m not in MODELS for m in models) or not cases:
        print(f"모델이나 사례 id를 확인하세요. 모델 후보: {', '.join(MODELS)}")
        return 2
    policies = load_policies()
    print(f"정책 {len(policies):,}건 (마감 제외 {sum(r['period']['status'] != 'closed' for r in policies):,}건)")
    if args.offline:
        offline(policies, cases)
        return 0
    if args.fake:
        llm_for = fake_llm_for
    else:
        load_env()
        key = os.environ.get("GROQ_API_KEY", "")
        if not key:
            print(".env에 GROQ_API_KEY가 비어 있다. .env.example을 보세요")
            return 2

        def llm_for(model_name):
            return lambda body: post_groq(key, body)

    run(models, cases, args.budget, results, llm_for, policies, 0 if args.fake else CALL_GAP_SECONDS)
    print()
    report(results)
    if args.fake:
        print(f"\n가짜 실행 결과 위치: {results}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
