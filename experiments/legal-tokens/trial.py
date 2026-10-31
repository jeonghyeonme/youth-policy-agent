"""법률 정보 에이전트가 질문 하나에 쓰는 LLM 토큰을 잰다 (Q7).

LLM이 국가법령정보 API 도구(search_law, get_law)를 골라 부르는 루프를 실제로 돌리고,
호출마다 Groq가 돌려준 usage를 더해 질문당 토큰과 하루 처리 가능한 질문 수를 낸다.

실행: 저장소 루트에서 `python3 experiments/legal-tokens/trial.py` (Windows는 `py ...`)
결과 요약만 보기: `--report`
흐름만 확인(키·네트워크 없음): `--fake`
키는 `.env`의 GROQ_API_KEY, LAW_API_OC에서 읽는다. 키 값과 OC는 출력·저장하지 않는다.
법령 API 응답은 cache/에 저장하고 다시 부르지 않는다. 이미 저장된 사례는 LLM도 다시 부르지 않는다.
"""

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
# v1: 첫 실행. v2: 검색어 안내·본문 검색·재시도 안내 추가, 마지막 단계에서 도구를 뺀다.
# v3: 0건 판정 버그 수정(v2는 0건을 결과 1건으로 넘겼다), 목록에서 순번 id와 링크를 뺀다.
TOOL_VERSION = "v3"
DAILY_TOKENS = 200_000
TARGET_PER_DAY = 30
CALL_GAP_SECONDS = 3
LAW_BASE = "https://www.law.go.kr/DRF/"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

MODELS = {
    "gpt-oss-120b": {"model": "openai/gpt-oss-120b", "reasoning_effort": "low", "include_reasoning": False},
    "gpt-oss-20b": {"model": "openai/gpt-oss-20b", "reasoning_effort": "low", "include_reasoning": False},
    "qwen3.8-27b": {"model": "qwen/qwen3.8-27b", "reasoning_effort": "none"},
}

# 제안서 7.1 사례와 같은 질문이다. 축소 범위(용어·학사·노동)를 중심으로, 주거·교통을 하나씩 넣었다.
CASES = [
    ("c01", "법률용어", "개념", "법에서 말하는 고의와 과실은 어떻게 다른가요?"),
    ("c02", "학사 규정", "적용", "우리 학교는 일반휴학을 몇 학기까지 할 수 있나요? 복학했다가 다시 휴학할 수도 있나요?"),
    ("c03", "노동", "개념", "아르바이트도 휴게시간이 있나요? 일하는 시간에 따라 기준이 달라지나요?"),
    ("c04", "노동", "절차", "카페 아르바이트를 그만뒀는데 마지막 급여를 못 받았어요. 어디에 어떤 자료를 내야 하나요?"),
    ("c05", "주거", "적용", "월세로 사는 집의 보일러가 고장 났어요. 수리비는 누가 부담하고 집주인에게 어떻게 요청하나요?"),
    ("c06", "도로교통", "적용", "우회전하려는데 횡단보도 근처에 사람이 있어요. 어떤 조건에서 멈춰야 하나요?"),
]

TARGETS = {
    "lstrm": "법령용어. get_law의 id에는 용어명을 넣는다",
    "law": "현행 법령. get_law의 id에는 법령ID를 넣고, 필요한 조문만 article로 지정한다",
    "school": "대학 학칙·학교규정. get_law의 id에는 행정규칙일련번호를 넣는다",
    "admrul": "행정규칙(고시·훈령·지침). get_law의 id에는 행정규칙일련번호를 넣는다",
    "moelCgmExpc": "고용노동부 법령해석. get_law의 id에는 법령해석일련번호를 넣는다",
    "expc": "법제처 법령해석례. get_law의 id에는 법령해석례일련번호를 넣는다",
    "prec": "판례. get_law의 id에는 판례일련번호를 넣는다",
}

TOOLS = [
    {"type": "function", "function": {
        "name": "search_law",
        "description": "국가법령정보에서 자료 목록을 검색한다. 결과는 최대 5건이다.\n"
                       "기본 검색은 자료 이름(법령명·용어명·규정명)만 본다. '근로기준법', '고의'처럼 이름 하나를 넣는다. "
                       "문장이나 여러 낱말을 넣으면 0건이 나오기 쉽다. 조문 내용으로 찾으려면 body_search를 true로 한다.\n"
                       + "\n".join(f"- {k}: {v}" for k, v in TARGETS.items()),
        "parameters": {"type": "object", "properties": {
            "target": {"type": "string", "enum": list(TARGETS)},
            "query": {"type": "string", "description": "자료 이름 하나. 사용자 문장을 넣지 않는다"},
            "body_search": {"type": "boolean", "description": "true면 이름 대신 본문에서 찾는다. lstrm에서는 쓰지 않는다"},
        }, "required": ["target", "query"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "get_law",
        "description": "search_law 결과에서 고른 자료의 본문을 가져온다. 길면 잘린다. "
                       "id는 지어내지 말고 search_law 결과에 나온 값을 그대로 쓴다.",
        "parameters": {"type": "object", "properties": {
            "target": {"type": "string", "enum": list(TARGETS)},
            "id": {"type": "string"},
            "article": {"type": "integer", "description": "law에서만. 조문 번호(제43조면 43)"},
        }, "required": ["target", "id"], "additionalProperties": False}}},
]

SYSTEM_PROMPT = (
    "너는 대학생·사회초년생에게 법률 정보를 안내하는 도우미다. 법률 상담이나 법적 판단을 하지 않는다.\n"
    "질문 의도(개념 설명 / 개인 상황 적용 / 절차 안내)를 먼저 구분하고, 필요한 만큼만 도구로 공식 원문을 찾는다.\n"
    "답은 원문에서 확인한 내용만 근거로 쓰고, 근거마다 법령명·조문 또는 자료명을 붙인다.\n"
    "확인하지 못한 것은 '확인하지 못함'이라고 쓴다. 학교·지역처럼 답을 바꾸는 정보가 없으면 마지막에 되묻는다.\n"
    "한국어 존댓말로 쓴다."
)


def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


class LawApi:
    """국가법령정보 공동활용 API. 응답은 OC를 지운 뒤 cache/에 저장하고, 같은 요청은 다시 보내지 않는다."""

    def __init__(self, oc, cache_dir, fetch=None):
        self.oc = oc
        self.cache_dir = cache_dir
        self.fetch = fetch or self._fetch
        self.network_calls = 0

    def _fetch(self, service, params):
        query = urllib.parse.urlencode({"OC": self.oc, "type": "JSON", **params})
        req = urllib.request.Request(f"{LAW_BASE}{service}?{query}", headers={"User-Agent": "legal-tokens/trial"})
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return res.status, res.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as e:
            return None, f"연결 실패: {e.reason}"

    def scrub(self, text):
        text = re.sub(r"OC=[^&\"'\s<]*", "OC={LAW_API_OC}", text)
        return text.replace(self.oc, "{LAW_API_OC}") if self.oc else text

    def call(self, service, params):
        key = json.dumps([service, sorted(params.items())], ensure_ascii=False)
        path = self.cache_dir / params["target"] / f"{hashlib.sha1(key.encode()).hexdigest()[:16]}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["body"], True
        status, body = self.fetch(service, params)
        self.network_calls += 1
        body = self.scrub(body)
        try:
            json.loads(body)
        except ValueError:
            return f"[API 오류] HTTP {status}: {body[:300]}", False
        if status == 200:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"service": service, "params": params, "body": body},
                                       ensure_ascii=False, indent=1), encoding="utf-8")
        return body, False


def search_items(data):
    """검색 응답 {"<종류>Search": {"<항목>": [...], "totalCnt": ...}}에서 결과 항목만 꺼낸다.
    결과가 1건이면 목록 대신 dict 하나, 0건이면 항목 키 자체가 없다."""
    wrapper = next(iter(data.values())) if isinstance(data, dict) and len(data) == 1 else data
    if not isinstance(wrapper, dict):
        return []
    for value in wrapper.values():
        if isinstance(value, list):
            items = [x for x in value if isinstance(x, dict)]
            break
        if isinstance(value, dict):
            items = [value]
            break
    else:
        return []
    # "id"는 목록 순번이라 모델이 본문 id로 착각한다(v2 실측). 링크에는 쓸 정보가 없다.
    return [{k: v for k, v in item.items() if k != "id" and "링크" not in k} for item in items]


RETRY_HINT = {
    "search_law": "검색 결과 0건. 자료 이름 하나로 다시 찾거나 body_search를 true로 해 본다.",
    "get_law": "해당 id의 자료가 없다. search_law 결과에 나온 id를 그대로 쓴다.",
}
FAILURE_MARKS = ("검색 결과 0건", "[API 오류]", "[도구", "[알 수 없는", "일치하는", "해당 id의 자료가 없다")


def useful(result):
    return not any(mark in result[:150] for mark in FAILURE_MARKS)


def run_tool(api, name, raw_args, max_chars):
    try:
        args = json.loads(raw_args or "{}")
        target = args["target"]
        if target not in TARGETS:
            raise KeyError(target)
    except (ValueError, KeyError, TypeError) as e:
        return f"[도구 인자 오류] {e}", None
    if name == "search_law":
        params = {"target": target, "query": args.get("query", ""), "display": 5}
        if args.get("body_search") and target != "lstrm":
            params["search"] = 2
        body, cached = api.call("lawSearch.do", params)
        try:
            items = search_items(json.loads(body))
            text = json.dumps(items[:5], ensure_ascii=False) if items else RETRY_HINT["search_law"]
        except ValueError:
            text = body
    elif name == "get_law":
        params = {"target": target}
        params["query" if target == "lstrm" else "ID"] = str(args.get("id", ""))
        if target == "law" and args.get("article"):
            params["JO"] = f"{int(args['article']):04d}00"
        text, cached = api.call("lawService.do", params)
        if "일치하는" in text[:150] and len(text) < 300:
            text = RETRY_HINT["get_law"]
    else:
        return f"[알 수 없는 도구] {name}", None
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n…(이하 {len(text) - max_chars}자 생략)"
    return text, cached


def post_groq(key, body):
    data = json.dumps(body).encode()
    for attempt in range(6):
        req = urllib.request.Request(GROQ_URL, data=data, headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "User-Agent": "legal-tokens/trial"})
        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                return 200, json.loads(res.read()), round(time.time() - started, 2)
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", errors="replace")
            if e.code == 429 and attempt < 5:
                wait = float(e.headers.get("retry-after") or 30)
                print(f"    한도 초과(429), {wait:.0f}초 기다린다")
                time.sleep(wait)
                continue
            return e.code, {"error": text[:500]}, None
        except urllib.error.URLError as e:
            return None, {"error": f"연결 실패: {e.reason}"}, None
    return 429, {"error": "재시도 횟수 초과"}, None


def run_case(llm, api, model_name, question, max_steps, max_chars):
    """에이전트 루프 한 번. 마지막 단계에서는 도구를 끄고 답을 강제한다."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
    calls, answer, outcome = [], None, "forced"
    for step in range(1, max_steps + 1):
        last = step == max_steps
        body = {**MODELS[model_name], "messages": messages, "max_completion_tokens": 2048}
        if last:
            # gpt-oss는 tool_choice=none이어도 도구를 불러 400이 난다(v1 실측). 마지막에는 도구 정의를 뺀다.
            body["messages"] = messages + [{"role": "user", "content": "도구는 더 쓸 수 없다. 지금까지 확인한 원문만으로 답한다."}]
        else:
            body.update(tools=TOOLS, tool_choice="auto")
        status, response, latency = llm(body)
        if status != 200:
            calls.append({"step": step, "status": status, "error": response.get("error")})
            outcome = "error"
            break
        message = response["choices"][0]["message"]
        record = {"step": step, "status": 200, "latency_s": latency, "usage": response.get("usage"), "tools": []}
        calls.append(record)
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            answer = message.get("content")
            outcome = "empty" if not (answer or "").strip() else "forced" if last else "answered"
            break
        messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
        for tc in tool_calls:
            result, cached = run_tool(api, tc["function"]["name"], tc["function"].get("arguments"), max_chars)
            record["tools"].append({"name": tc["function"]["name"], "args": tc["function"].get("arguments"),
                                    "result_chars": len(result), "useful": useful(result),
                                    "result_head": result[:80], "cached": cached})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
    ok = [c for c in calls if c.get("usage")]
    totals = {k: sum(c["usage"].get(k, 0) for c in ok) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    totals.update(llm_calls=len(calls), tool_calls=sum(len(c.get("tools", [])) for c in calls))
    return {"outcome": outcome, "totals": totals, "calls": calls, "answer": answer}


def config_name(max_steps, max_chars):
    return f"{TOOL_VERSION}-steps{max_steps}-chars{max_chars}"


def run(models, cases, max_steps, max_chars, budget, results, llm_for, api, gap):
    for model_name in models:
        print(f"## {model_name} ({config_name(max_steps, max_chars)})")
        spent = 0
        for case_id, field, intent, question in cases:
            path = results / config_name(max_steps, max_chars) / model_name / f"{case_id}.json"
            if path.exists() and json.loads(path.read_text(encoding="utf-8"))["outcome"] != "error":
                continue
            if spent >= budget:
                print(f"  이번 실행 토큰 {spent:,}이 상한 {budget:,}을 넘어 멈춘다. 내일 다시 실행하면 이어서 한다")
                break
            result = run_case(llm_for(model_name), api, model_name, question, max_steps, max_chars)
            spent += result["totals"]["total_tokens"]
            record = {"model": model_name, "case": case_id, "field": field, "intent": intent,
                      "question": question, "max_steps": max_steps, "max_chars": max_chars, **result}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
            t = result["totals"]
            print(f"  {case_id}: {result['outcome']}, LLM {t['llm_calls']}회, 도구 {t['tool_calls']}회, "
                  f"{t['total_tokens']:,} 토큰")
            time.sleep(gap)
    print(f"법령 API 실제 호출 {api.network_calls}회 (나머지는 cache)")


def bodies_read(record):
    """본문 조회(get_law)가 실제 원문을 돌려준 횟수. v1 기록에는 판정이 없어 None."""
    tools = [t for c in record["calls"] for t in c.get("tools", []) if t["name"] == "get_law"]
    if any("useful" not in t for t in tools):
        return None
    return sum(t["useful"] for t in tools)


def summarize(label, records):
    if not records:
        print(f"   {label}: 없음")
        return
    tokens = [r["totals"]["total_tokens"] for r in records]
    avg = statistics.mean(tokens)
    per_day = DAILY_TOKENS // avg
    verdict = "기준 충족" if per_day >= TARGET_PER_DAY else "기준 미달"
    print(f"   {label} {len(records)}건: 질문당 평균 {avg:,.0f}, 중앙값 {statistics.median(tokens):,.0f}, "
          f"최대 {max(tokens):,} → 하루 약 {per_day:.0f}개 (목표 {TARGET_PER_DAY}개: {verdict})")


def report(results):
    print(f"하루 {DAILY_TOKENS:,} 토큰 기준. 유효 = 답을 냈고 본문을 1번 이상 실제로 읽은 사례")
    for config_dir in sorted(p for p in results.glob("*") if p.is_dir()):
        for model_dir in sorted(p for p in config_dir.glob("*") if p.is_dir()):
            records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(model_dir.glob("*.json"))]
            print(f"## {model_dir.name} · {config_dir.name}")
            for r in records:
                t, read = r["totals"], bodies_read(r)
                print(f"   {r['case']} {r['field']}/{r['intent']}: {r['outcome']}, LLM {t['llm_calls']}회, "
                      f"도구 {t['tool_calls']}회, 본문 확보 {'?' if read is None else read}회, "
                      f"입력 {t['prompt_tokens']:,} + 출력 {t['completion_tokens']:,} = {t['total_tokens']:,}")
            finished = [r for r in records if r["outcome"] in ("answered", "forced")]
            summarize("답을 낸 사례", finished)
            summarize("유효 사례", [r for r in finished if bodies_read(r)])
            for outcome, label in (("forced", "단계 상한으로 답을 강제"), ("empty", "빈 답"), ("error", "오류")):
                cases = [r["case"] for r in records if r["outcome"] == outcome]
                if cases:
                    print(f"   {label}: {', '.join(cases)}")


def fake_setup(oc="FAKEOC123"):
    """키·네트워크 없이 루프·저장·OC 지우기를 확인하는 가짜 LLM과 가짜 법령 API."""
    def fake_fetch(service, params):
        if service == "lawSearch.do":
            return 200, json.dumps({"LawSearch": {"totalCnt": "1", "law": [
                {"법령ID": "001872", "법령명한글": "근로기준법",
                 "법령상세링크": f"/DRF/lawService.do?OC={oc}&target=law&MST=1"}]}}, ensure_ascii=False)
        return 200, json.dumps({"법령": {"조문": "가" * 5000, "링크": f"OC={oc}"}}, ensure_ascii=False)

    def fake_llm_for(model_name):
        def llm(body):
            step = sum(1 for m in body["messages"] if m["role"] == "assistant") + 1
            prompt = sum(len(m.get("content") or "") for m in body["messages"]) // 2
            if "tools" not in body or step > 2:
                message = {"role": "assistant", "content": "가짜 답변"}
            else:
                name, args = (("search_law", {"target": "law", "query": "임금"}) if step == 1
                              else ("get_law", {"target": "law", "id": "001872", "article": 43}))
                message = {"role": "assistant", "content": None, "tool_calls": [{
                    "id": f"t{step}", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]}
            usage = {"prompt_tokens": prompt, "completion_tokens": 50, "total_tokens": prompt + 50}
            return 200, {"choices": [{"message": message}], "usage": usage}, 0.0
        return llm
    return oc, fake_fetch, fake_llm_for


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="저장된 결과로 요약만 본다")
    parser.add_argument("--fake", action="store_true", help="키·네트워크 없이 흐름만 확인한다. 임시 폴더에 쓴다")
    parser.add_argument("--models", default="gpt-oss-120b", help=f"쉼표로 구분. 후보: {', '.join(MODELS)}")
    parser.add_argument("--cases", default=",".join(c[0] for c in CASES), help="쉼표로 구분한 사례 id")
    parser.add_argument("--max-steps", type=int, default=6, help="질문당 LLM 호출 상한")
    parser.add_argument("--max-chars", type=int, default=3000, help="도구 결과 하나를 LLM에 넘길 최대 글자 수")
    parser.add_argument("--budget", type=int, default=150_000, help="모델마다 이번 실행에서 쓸 토큰 상한")
    args = parser.parse_args()

    results, cache = HERE / "results", HERE / "cache"
    if args.fake:
        tmp = Path(tempfile.mkdtemp(prefix="legal-tokens-"))
        results, cache = tmp / "results", tmp / "cache"
    if args.report:
        report(results)
        return 0

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    unknown = [m for m in models if m not in MODELS]
    wanted = {c.strip() for c in args.cases.split(",")}
    cases = [c for c in CASES if c[0] in wanted]
    if unknown or not cases:
        print(f"모델이나 사례 id를 확인하세요. 모델 후보: {', '.join(MODELS)}")
        return 2

    if args.fake:
        oc, fetch, llm_for = fake_setup()
        api = LawApi(oc, cache, fetch)
    else:
        load_env()
        key, oc = os.environ.get("GROQ_API_KEY", ""), os.environ.get("LAW_API_OC", "")
        missing = [n for n, v in (("GROQ_API_KEY", key), ("LAW_API_OC", oc)) if not v]
        if missing:
            print(f".env에 {', '.join(missing)}가 비어 있다. .env.example을 보세요")
            return 2
        api = LawApi(oc, cache)

        def llm_for(model_name):
            return lambda body: post_groq(key, body)

    run(models, cases, args.max_steps, args.max_chars, args.budget, results, llm_for, api,
        0 if args.fake else CALL_GAP_SECONDS)
    print()
    report(results)
    if args.fake:
        print(f"\n가짜 실행 결과 위치: {results}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
