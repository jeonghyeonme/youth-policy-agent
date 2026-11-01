"""법률 정보안 v4: API 하나(현행 법령 본문), 법령 고정, LLM 질문당 2회로 토큰과 조문 선택을 잰다 (Q7).

v1~v3(trial.py)는 LLM이 검색 도구를 골라 부르는 루프였다. 검색이 헛돌고 조문 번호를 짐작해 틀렸다.
v4·v5는 청년 정책 D3와 같은 구조다(v5는 주제→조문 표 추가, --topics).
  준비: 다룰 법령을 미리 정하고, 법령 전체 본문을 한 번 받아 laws/에 조문 단위로 저장한다.
  1회차: LLM이 조문 목차를 보고 관련 조문을 최대 3개 고른다(JSON).
  서버: 고른 조문 원문을 laws/에서 꺼낸다. API를 부르지 않는다.
  2회차: LLM이 그 조문만으로 답한다. 서버가 답에 인용된 조문이 넘겨준 조문인지 검사한다.

실행: 저장소 루트에서 `python3 experiments/legal-tokens/two_call.py` (Windows는 `py ...`)
결과 요약만 보기: `--report` · 흐름만 확인(키·네트워크 없음): `--fake`
키는 `.env`의 GROQ_API_KEY, LAW_API_OC에서 읽는다. 법령 API는 처음 한 번 법령마다 2회(목록 1, 본문 1)만 부른다.
"""

import argparse
import json
import os
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from trial import (CALL_GAP_SECONDS, DAILY_TOKENS, MODELS, TARGET_PER_DAY, LawApi,  # noqa: E402
                   load_env, post_groq, search_items)

# v4: 목차에서 조문을 고른다. v5: --topics. 주제→조문 표(topics.json)를 1회차에 함께 주고,
# 고른 주제의 조문은 서버가 넣는다. 2회차에 원문 밖 기준·절차를 채우지 말라는 규칙을 더했다.
TOPICS_FILE = HERE / "topics.json"
MAX_ARTICLES = 4

# 다룰 법령. articles는 목차에 넣을 조문 범위다(민법은 임대차 절만).
LAWS = {
    "근로기준법": {"domain": "노동"},
    "최저임금법": {"domain": "노동"},
    "주택임대차보호법": {"domain": "주거"},
    "민법": {"domain": "주거", "articles": (618, 654)},
}
DOMAINS = sorted({spec["domain"] for spec in LAWS.values()})

# v3의 노동·주거 사례 3개(c03~c05)에 4개를 더했다. 질문은 직접 만든 문장이다.
CASES = [
    ("c03", "노동", "개념", "아르바이트도 휴게시간이 있나요? 일하는 시간에 따라 기준이 달라지나요?"),
    ("c04", "노동", "절차", "카페 아르바이트를 그만뒀는데 마지막 급여를 못 받았어요. 어디에 어떤 자료를 내야 하나요?"),
    ("c07", "노동", "적용", "주 15시간 넘게 편의점 알바를 하는데 주휴수당을 받을 수 있나요?"),
    ("c08", "노동", "적용", "시급이 최저임금보다 적은 것 같아요. 수습 기간이라고 덜 줘도 되나요?"),
    ("c05", "주거", "적용", "월세로 사는 집의 보일러가 고장 났어요. 수리비는 누가 부담하고 집주인에게 어떻게 요청하나요?"),
    ("c09", "주거", "개념", "월세 계약이 끝나면 보증금은 언제까지 돌려받을 수 있나요?"),
    ("c10", "주거", "적용", "계약 기간이 남았는데 집주인이 집을 팔았다고 나가래요. 나가야 하나요?"),
    # v5에서 더한 사례. 주제 표를 만든 뒤에 썼다. c15는 표에 없는 주제(목차로 찾아야 한다).
    ("c11", "노동", "적용", "밤 11시까지 일하는데 밤에 일한 시간은 돈을 더 받을 수 있나요?"),
    ("c12", "노동", "절차", "사장님이 내일부터 나오지 말라고 문자로만 보냈어요. 이래도 되나요?"),
    ("c13", "주거", "적용", "재계약하면서 집주인이 월세를 10% 올리겠대요. 그래도 되나요?"),
    ("c14", "주거", "절차", "전입신고를 아직 안 했는데 보증금을 지키려면 뭘 해야 하나요?"),
    ("c15", "노동", "적용", "알바하다가 손을 다쳤는데 치료비를 사장님한테 받을 수 있나요?"),
]

PICK_PROMPT = (
    "너는 법률 정보 안내 서비스의 조문 선택기다. 사용자 질문에 답하는 데 필요한 조문을 아래 목차에서 최대 3개 고른다.\n"
    "목차에 없는 조문은 고르지 않는다. 관련 조문이 없으면 articles를 빈 배열로 둔다.\n"
    "intent는 질문 의도다(개념: 뜻·기준 설명, 적용: 내 상황에 해당하는지, 절차: 무엇을 어디에 하는지).\n"
    "need_info에는 답을 실제로 바꾸는 정보 중 질문에 없는 것만 짧게 적는다(예: 1주 근무시간). 없으면 빈 배열.\n"
)

PICK_PROMPT_V5 = (
    "너는 법률 정보 안내 서비스의 조문 선택기다.\n"
    "1. 아래 [자주 묻는 주제]에서 질문에 맞는 주제를 0~2개 고른다(topics). 고른 주제의 조문은 자동으로 들어간다.\n"
    "2. 주제로 부족하면 [조문 목차]에서 조문을 최대 2개 더 고른다(articles). 주제로 충분하면 빈 배열로 둔다.\n"
    "목차에 없는 조문은 고르지 않는다.\n"
    "intent는 질문 의도다(개념: 뜻·기준 설명, 적용: 내 상황에 해당하는지, 절차: 무엇을 어디에 하는지).\n"
    "need_info에는 답을 실제로 바꾸는 정보 중 질문에 없는 것만 짧게 적는다. 질문에 이미 있는 정보는 넣지 않는다. 없으면 빈 배열.\n"
)

PICK_PROMPT_TOPICS = (
    "너는 법률 정보 안내 서비스의 주제 분류기다. 아래 [자주 묻는 주제]에서 질문에 맞는 주제를 0~2개 고른다(topics).\n"
    "맞는 주제가 없으면 topics를 빈 배열로 둔다. articles는 항상 빈 배열로 둔다.\n"
    "intent는 질문 의도다(개념: 뜻·기준 설명, 적용: 내 상황에 해당하는지, 절차: 무엇을 어디에 하는지).\n"
    "need_info에는 답을 실제로 바꾸는 정보 중 질문에 없는 것만 짧게 적는다. 질문에 이미 있는 정보는 넣지 않는다. 없으면 빈 배열.\n"
)

ANSWER_PROMPT = (
    "너는 대학생·사회초년생에게 법률 정보를 안내하는 도우미다. 법률 상담이나 법적 판단을 하지 않는다.\n"
    "아래에 준 조문 원문만 근거로 쓴다. 근거를 쓸 때는 「법령명」 제N조처럼 법령명과 조문 번호를 붙인다.\n"
    "주지 않은 조문, 판례, 기관 절차는 인용하지 않는다. 원문으로 답할 수 없는 부분은 '확인하지 못함'이라고 쓴다.\n"
    "need_info가 있으면 마지막에 한 번만 되묻는다. 한국어 존댓말로 짧게 쓴다."
)

ANSWER_PROMPT_V5 = ANSWER_PROMPT + (
    "\n준 조문에 없는 시간·금액·기간 기준은 기억으로 채우지 않는다. 필요하면 '준 조문으로는 확인하지 못함'이라고 쓴다.\n"
    "절차를 물으면 준 조문에 있는 권리와 기한까지만 설명하고, 신고처·제출 서류·기관 이름은 쓰지 않는다. "
    "대신 '신고처와 서류는 관할 기관의 공식 안내에서 확인이 필요합니다'라고 쓴다."
)

TAG_RE = re.compile(r"\s*<(?:개정|신설|전문개정|타법개정|본조신설|제목개정)[^>]*>")
CITE_RE = re.compile(r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?")


def article_key(no, branch):
    return f"{no}의{branch}" if branch and str(branch) not in ("0", "") else str(no)


def label(key):
    no, _, branch = key.partition("의")
    return f"제{no}조" + (f"의{branch}" if branch else "")


def texts(node):
    """항·호·목 안의 '…내용' 글을 순서대로 모은다."""
    if isinstance(node, list):
        return [t for x in node for t in texts(x)]
    if isinstance(node, dict):
        out = []
        for k, v in node.items():
            if k.endswith("내용") and isinstance(v, str):
                out.append(v)
            elif isinstance(v, (dict, list)):
                out.extend(texts(v))
        return out
    return []


def parse_articles(body):
    units = json.loads(body)["법령"]["조문"]["조문단위"]
    units = units if isinstance(units, list) else [units]
    articles = []
    for u in units:
        if u.get("조문여부") != "조문":
            continue
        lines = [u.get("조문내용", "")] + texts(u.get("항", []))
        text = TAG_RE.sub("", "\n".join(line.strip() for line in lines if line.strip()))
        articles.append({"key": article_key(u["조문번호"], u.get("조문가지번호")),
                         "no": int(u["조문번호"]), "title": u.get("조문제목", ""), "text": text})
    return articles


def collect(api, laws_dir):
    """법령마다 목록 1회로 법령ID를 찾고 본문 1회로 전체 조문을 받아 laws/에 둔다. 있으면 다시 받지 않는다."""
    for name in LAWS:
        path = laws_dir / f"{name}.json"
        if path.exists():
            continue
        body, _ = api.call("lawSearch.do", {"target": "law", "query": name, "display": 20})
        matches = [x for x in search_items(json.loads(body))
                   if x.get("법령명한글") == name and x.get("현행연혁코드") == "현행"]
        if not matches:
            raise SystemExit(f"{name}: 현행 법령을 찾지 못했다. cache/law의 검색 응답을 확인하세요")
        law_id = matches[0]["법령ID"]
        body, _ = api.call("lawService.do", {"target": "law", "ID": law_id})
        data = json.loads(body)["법령"]["기본정보"]
        record = {"name": name, "id": law_id, "시행일자": data.get("시행일자"), "articles": parse_articles(body)}
        laws_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {name}: 법령ID {law_id}, 조문 {len(record['articles'])}개 저장")


def load_laws(laws_dir):
    laws = {}
    for name, spec in LAWS.items():
        record = json.loads((laws_dir / f"{name}.json").read_text(encoding="utf-8"))
        lo, hi = spec.get("articles", (0, 10**6))
        laws[name] = {**spec, "articles": {a["key"]: a for a in record["articles"] if lo <= a["no"] <= hi}}
    return laws


def load_topics(laws):
    """topics.json을 읽고, 표의 조문이 laws/에 모두 있는지 확인한다. 없으면 멈춘다."""
    topics = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))["topics"]
    missing = [f"{t['name']}: {law} {key}" for t in topics for law, key in t["articles"]
               if key not in laws.get(law, {}).get("articles", {})]
    if missing:
        raise SystemExit("topics.json에 목차 범위 밖이거나 없는 조문이 있다: " + "; ".join(missing))
    return {t["name"]: t for t in topics}


def topic_table(topics, laws, domain):
    lines = []
    for t in topics.values():
        if domain in (None, t["domain"]):
            arts = ", ".join(f"{law} {label(key)}({laws[law]['articles'][key]['title']})" for law, key in t["articles"])
            lines.append(f"- {t['name']} (예: {', '.join(t['keywords'])}) → {arts}")
    return "\n".join(lines)


def toc(laws, domain):
    lines = []
    for name, law in laws.items():
        if domain in (None, law["domain"]):
            lines.append(f"[{name}]")
            lines.extend(f"{label(k)} {a['title']}" for k, a in law["articles"].items())
    return "\n".join(lines)


def pick_schema(laws, topics=None):
    schema = {"type": "json_schema", "json_schema": {"name": "pick", "strict": True, "schema": {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": ["개념", "적용", "절차"]},
            "articles": {"type": "array", "items": {
                "type": "object",
                "properties": {"law": {"type": "string", "enum": list(laws)},
                               "article": {"type": "string", "description": "조문 번호. 제54조면 54, 제6조의3이면 6의3"}},
                "required": ["law", "article"], "additionalProperties": False}},
            "need_info": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["intent", "articles", "need_info"], "additionalProperties": False}}}
    if topics:
        inner = schema["json_schema"]["schema"]
        inner["properties"]["topics"] = {"type": "array", "items": {"type": "string", "enum": list(topics)}}
        inner["required"].append("topics")
    return schema


def normalize_article(raw):
    m = CITE_RE.search(f"제{raw}조") if raw else None
    return article_key(m.group(1), m.group(2)) if m else str(raw)


def uncited(answer, given_keys):
    """답에 나온 '제N조' 중 넘겨주지 않은 번호. 법령명까지는 맞춰 보지 않는다."""
    found = {article_key(m.group(1), m.group(2)) for m in CITE_RE.finditer(answer or "")}
    return sorted(found - given_keys, key=lambda k: (int(k.split("의")[0]), k))


def call(llm, model_name, messages, max_tokens, response_format=None):
    body = {**MODELS[model_name], "messages": messages, "max_completion_tokens": max_tokens}
    if response_format:
        body["response_format"] = response_format
    status, response, latency = llm(body)
    if status != 200:
        return {"status": status, "error": response.get("error"), "long_wait": bool(response.get("long_wait"))}, None
    return ({"status": 200, "latency_s": latency, "usage": response.get("usage")},
            response["choices"][0]["message"].get("content"))


def run_case(llm, laws, model_name, field, question, toc_mode, max_chars, topics=None):
    calls, record = [], {"selected": [], "pick": None, "answer": None, "uncited": []}
    domain = field if toc_mode == "domain" else None
    if toc_mode == "fallback":
        # 1회차에는 주제 표만 준다. 맞는 주제가 없을 때만 목차로 한 번 더 고른다(그 질문만 LLM 3회).
        system = PICK_PROMPT_TOPICS + "\n[자주 묻는 주제]\n" + topic_table(topics, laws, None)
    elif topics:
        system = (PICK_PROMPT_V5 + "\n[자주 묻는 주제]\n" + topic_table(topics, laws, domain)
                  + "\n\n[조문 목차]\n" + toc(laws, domain))
    else:
        system = PICK_PROMPT + "\n[조문 목차]\n" + toc(laws, domain)
    meta, content = call(llm, model_name, [{"role": "system", "content": system},
                                           {"role": "user", "content": question}], 1024, pick_schema(laws, topics))
    calls.append({"step": 1, **meta})
    try:
        pick = json.loads(content) if content else None
    except ValueError:
        pick = None
    if pick and toc_mode == "fallback" and not [t for t in pick.get("topics", []) if t in topics]:
        meta, content = call(llm, model_name, [
            {"role": "system", "content": PICK_PROMPT + "\n[조문 목차]\n" + toc(laws, None)},
            {"role": "user", "content": question}], 1024, pick_schema(laws))
        calls.append({"step": 1, "fallback": True, **meta})
        try:
            pick = {**pick, "articles": json.loads(content)["articles"]} if content else None
        except (ValueError, KeyError):
            pick = None
    if not pick:
        return {**record, "outcome": "error", "calls": calls}
    record["pick"] = pick
    wanted = [(law, key, "주제") for name in pick.get("topics", [])[:2] if name in (topics or {})
              for law, key in topics[name]["articles"]]
    wanted += [(item["law"], normalize_article(item["article"]), "목차") for item in pick["articles"][:3]]
    seen, given = set(), []
    for law, key, source in wanted:
        if (law, key) in seen or len(seen) >= MAX_ARTICLES:
            continue
        seen.add((law, key))
        article = laws.get(law, {}).get("articles", {}).get(key)
        record["selected"].append({"law": law, "article": key, "source": source,
                                   "title": article["title"] if article else None, "found": bool(article)})
        if article:
            text = article["text"]
            given.append(f"「{law}」 {text[:max_chars]}" + ("…(생략)" if len(text) > max_chars else ""))
    user = json.dumps({"질문": question, "질문 의도": pick["intent"], "need_info": pick["need_info"],
                       "조문": given or ["관련 조문을 찾지 못함"]}, ensure_ascii=False)
    meta, content = call(llm, model_name, [{"role": "system", "content": ANSWER_PROMPT_V5 if topics else ANSWER_PROMPT},
                                           {"role": "user", "content": user}], 1500)
    calls.append({"step": 2, **meta})
    if meta["status"] != 200:
        return {**record, "outcome": "error", "calls": calls}
    given_keys = {s["article"] for s in record["selected"] if s["found"]}
    record.update(answer=content, uncited=uncited(content, given_keys),
                  outcome="answered" if (content or "").strip() else "empty", calls=calls)
    return record


def totals(calls):
    ok = [c for c in calls if c.get("usage")]
    t = {k: sum(c["usage"].get(k, 0) for c in ok) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    t["llm_calls"] = len(calls)
    t["pick_tokens"] = sum(c["usage"]["total_tokens"] for c in ok if c["step"] == 1)
    return t


def config_name(toc_mode, max_chars, topics=None):
    return f"{'v5' if topics else 'v4'}-toc{toc_mode}-chars{max_chars}"


def run(models, cases, toc_mode, max_chars, budget, results, llm_for, laws, gap, topics=None):
    for model_name in models:
        print(f"## {model_name} ({config_name(toc_mode, max_chars, topics)})")
        spent = 0
        for case_id, field, intent, question in cases:
            path = results / config_name(toc_mode, max_chars, topics) / model_name / f"{case_id}.json"
            if path.exists() and json.loads(path.read_text(encoding="utf-8"))["outcome"] != "error":
                continue
            if spent >= budget:
                print(f"  이번 실행 토큰 {spent:,}이 상한 {budget:,}을 넘어 멈춘다")
                break
            result = run_case(llm_for(model_name), laws, model_name, field, question, toc_mode, max_chars, topics)
            if any(c.get("long_wait") for c in result["calls"]):
                print(f"  {case_id}: Groq가 오래 기다리라고 한다(하루 한도로 보임). 여기서 멈춘다. 내일 같은 명령으로 이어서 하면 된다")
                return
            result["totals"] = totals(result["calls"])
            spent += result["totals"]["total_tokens"]
            record = {"model": model_name, "case": case_id, "field": field, "intent": intent,
                      "question": question, "toc": toc_mode, "max_chars": max_chars, "topics_on": bool(topics), **result}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
            picks = ", ".join(f"{s['law']} {s['article']}" + ("" if s["found"] else "(없음)") for s in result["selected"])
            print(f"  {case_id}: {result['outcome']}, {result['totals']['total_tokens']:,} 토큰, 고른 조문 [{picks}]")
            time.sleep(gap)


def report(results):
    print(f"하루 {DAILY_TOKENS:,} 토큰 기준. 조문 선택이 맞는지는 사람이 제목을 보고 판단한다")
    for config_dir in sorted(p for p in results.glob("*") if p.is_dir()):
        for model_dir in sorted(p for p in config_dir.glob("*") if p.is_dir()):
            records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(model_dir.glob("*.json"))]
            print(f"## {model_dir.name} · {config_dir.name}")
            for r in records:
                t = r["totals"]
                picks = ", ".join(f"{s['law']} {label(s['article'])}({s['title'] or '목차에 없음'})" for s in r["selected"])
                print(f"   {r['case']} {r['field']}/{r['intent']}: {r['outcome']}, 1회차 {t['pick_tokens']:,} + "
                      f"2회차 {t['total_tokens'] - t['pick_tokens']:,} = {t['total_tokens']:,}")
                chosen = (r.get("pick") or {}).get("topics")
                if chosen is not None:
                    print(f"      고른 주제: {', '.join(chosen) or '없음'}")
                print(f"      고른 조문: {picks or '없음'}")
                if r["uncited"]:
                    print(f"      넘겨주지 않은 조문 인용: {', '.join(label(k) for k in r['uncited'])}")
            done = [r for r in records if r["outcome"] == "answered"]
            if done:
                tokens = [r["totals"]["total_tokens"] for r in done]
                avg = statistics.mean(tokens)
                per_day = DAILY_TOKENS // avg
                print(f"   답을 낸 {len(done)}건: 질문당 평균 {avg:,.0f}, 최대 {max(tokens):,} → 하루 약 {per_day:.0f}개 "
                      f"(목표 {TARGET_PER_DAY}개: {'기준 충족' if per_day >= TARGET_PER_DAY else '기준 미달'})")
                print(f"   목차에 없는 조문 선택 {sum(not s['found'] for r in done for s in r['selected'])}건, "
                      f"넘겨주지 않은 조문 인용이 있는 답 {sum(bool(r['uncited']) for r in done)}건")
            failed = [r["case"] for r in records if r["outcome"] != "answered"]
            if failed:
                print(f"   답을 못 낸 사례: {', '.join(failed)}")


def fake_setup(oc="FAKEOC123"):
    """키·네트워크 없이 수집·두 호출·인용 검사·OC 지우기를 확인하는 가짜 API와 가짜 LLM."""
    ids = {name: f"{i:06d}" for i, name in enumerate(LAWS, 1)}

    def fake_fetch(service, params):
        if service == "lawSearch.do":
            return 200, json.dumps({"LawSearch": {"totalCnt": "2", "law": [
                {"id": "1", "법령명한글": params["query"], "법령ID": ids[params["query"]], "현행연혁코드": "현행",
                 "법령상세링크": f"/DRF/lawService.do?OC={oc}&ID=1"},
                {"id": "2", "법령명한글": params["query"] + " 시행령", "법령ID": "999999", "현행연혁코드": "현행"}]}},
                ensure_ascii=False)
        no_range = range(615, 660) if ids["민법"] == params["ID"] else range(1, 100)
        units = [{"조문번호": "1", "조문여부": "전문", "조문내용": "제1장 총칙"}]
        units += [{"조문번호": str(n), "조문여부": "조문", "조문제목": f"제목{n}", "조문내용": f"제{n}조(제목{n})",
                   "항": [{"항내용": f"① 내용 {n} <개정 2020.1.1>", "호": {"호내용": "1. 호 내용"}}]} for n in no_range]
        branches = {k for t in json.loads(TOPICS_FILE.read_text(encoding="utf-8"))["topics"]
                    for _, k in t["articles"] if "의" in k} | {"6의3"}
        units += [{"조문번호": k.split("의")[0], "조문가지번호": k.split("의")[1], "조문여부": "조문",
                   "조문제목": "가지", "조문내용": f"{label(k)}(가지) 본문"} for k in sorted(branches)]
        return 200, json.dumps({"법령": {"기본정보": {"시행일자": "20260101", "링크": f"OC={oc}"},
                                       "조문": {"조문단위": units}}}, ensure_ascii=False)

    def fake_llm_for(model_name):
        def llm(body):
            prompt = sum(len(m["content"]) for m in body["messages"]) // 2
            if "response_format" in body:
                props = body["response_format"]["json_schema"]["schema"]["properties"]
                hurt = "다쳤" in body["messages"][-1]["content"]
                extra = ({"topics": [] if hurt else [props["topics"]["items"]["enum"][0], "없는 주제"]}
                         if "topics" in props else {})
                content = json.dumps({**extra, "intent": "적용", "need_info": ["근무시간"], "articles": [
                    {"law": "근로기준법", "article": "54"}, {"law": "근로기준법", "article": "제6조의3"},
                    {"law": "민법", "article": "1"}]}, ensure_ascii=False)
            else:
                content = "「근로기준법」 제54조와 제6조의 3, 그리고 제99조에 따르면…"
            return 200, {"choices": [{"message": {"content": content}}],
                         "usage": {"prompt_tokens": prompt, "completion_tokens": 50, "total_tokens": prompt + 50}}, 0.0
        return llm
    return oc, fake_fetch, fake_llm_for


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="저장된 결과로 요약만 본다")
    parser.add_argument("--fake", action="store_true", help="키·네트워크 없이 흐름만 확인한다. 임시 폴더에 쓴다")
    parser.add_argument("--models", default="gpt-oss-120b", help=f"쉼표로 구분. 후보: {', '.join(MODELS)}")
    parser.add_argument("--cases", default=",".join(c[0] for c in CASES), help="쉼표로 구분한 사례 id")
    parser.add_argument("--toc", choices=["all", "domain", "fallback"], default="all",
                        help="1회차에 넣을 목차. all: 노동·주거 전부, domain: 질문 분야만(사용자가 분야 버튼을 눌렀다고 가정), "
                             "fallback: --topics와 함께. 주제 표만 주고 맞는 주제가 없을 때만 목차로 한 번 더 고른다")
    parser.add_argument("--max-chars", type=int, default=1500, help="조문 하나를 2회차에 넘길 최대 글자 수")
    parser.add_argument("--topics", action="store_true", help="v5: topics.json의 주제→조문 표를 1회차에 함께 준다")
    parser.add_argument("--budget", type=int, default=150_000, help="모델마다 이번 실행에서 쓸 토큰 상한")
    args = parser.parse_args()

    results, cache, laws_dir = HERE / "results-two-call", HERE / "cache", HERE / "laws"
    if args.fake:
        tmp = Path(tempfile.mkdtemp(prefix="legal-v4-"))
        results, cache, laws_dir = tmp / "results", tmp / "cache", tmp / "laws"
    if args.report:
        report(results)
        return 0

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    wanted = {c.strip() for c in args.cases.split(",")}
    cases = [c for c in CASES if c[0] in wanted]
    if any(m not in MODELS for m in models) or not cases:
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

    collect(api, laws_dir)
    laws = load_laws(laws_dir)
    topics = load_topics(laws) if args.topics else None
    if args.toc == "fallback" and not topics:
        print("--toc fallback은 --topics와 함께 쓴다")
        return 2
    print("목차 크기: " + ", ".join(f"{d} {len(toc(laws, d)):,}자" for d in DOMAINS) + f", 전체 {len(toc(laws, None)):,}자")
    if topics:
        print(f"주제 표 크기: 전체 {len(topic_table(topics, laws, None)):,}자")
    run(models, cases, args.toc, args.max_chars, args.budget, results, llm_for, laws,
        0 if args.fake else CALL_GAP_SECONDS, topics)
    print(f"법령 API 실제 호출 {api.network_calls}회 (나머지는 cache)")
    print()
    report(results)
    if args.fake:
        print(f"\n가짜 실행 결과 위치: {results.parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
