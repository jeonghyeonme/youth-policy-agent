"""Q3 순위 기준 후보를 저장된 온통청년 샘플에 돌려 상위 10건을 비교한다. API를 호출하지 않는다.

    python3 experiments/context-measurement/rank_experiment.py

결과는 표준 출력으로 낸다. 해석은 q3-ranking.md에 있다.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
TODAY = dt.date(2026, 11, 8)  # 샘플을 받은 날. 결과가 날짜에 따라 바뀌지 않게 고정한다
TOP_N = 10

UNEMPLOYED, ANY_JOB = "0013003", "0013010"
CLOSED = "0057003"

Policy = dict[str, str]


@dataclass(frozen=True)
class Question:
    name: str
    sample: str
    age: int
    zip_prefix: str
    unemployed: bool
    keywords: tuple[str, ...]  # LLM이 질문에서 뽑았다고 가정한 키워드


QUESTIONS = [
    Question("A: 종로구 26살 미취업, 지원금", "samples/youthcenter/probe_zip_11110.json", 26, "11", True,
             ("지원금", "보조금", "수당", "장기미취업")),
    Question("A': A를 정책 키워드 '보조금'으로 요청 단계에서 좁힘(1단계)", "samples/youthcenter/probe_kywd_subsidy.json", 26, "11", True,
             ("지원금", "보조금", "수당", "장기미취업")),
    Question("B: 서울 27살 자취, 월세 지원", "samples/youthcenter/B_list.json", 27, "11", False,
             ("월세", "임차", "주거비")),
]


def zip_count(p: Policy) -> int:
    return len([c for c in p["zipCd"].split(",") if c.strip()])


def apply_end(p: Policy) -> dt.date | None:
    m = re.findall(r"(\d{8})", p["aplyYmd"])
    return dt.datetime.strptime(m[-1], "%Y%m%d").date() if m else None


def is_open(p: Policy) -> bool:
    end = apply_end(p)
    return p["aplyPrdSeCd"] != CLOSED and (end is None or end >= TODAY)


def eligible(p: Policy, q: Question) -> bool:
    """서버 필터: 지역, 나이, 취업 요건. 지역은 A는 API가 이미 걸렀고, B는 여기서 거른다."""
    in_region = any(c.strip().startswith(q.zip_prefix) for c in p["zipCd"].split(","))
    # 나이 제한 여부(sprtTrgtAgeLmtYn)가 N이어도 최소·최대 나이가 적혀 있는 정책이 있다(log/016). 숫자가 있으면 숫자를 믿는다.
    lo = int(p["sprtTrgtMinAge"].strip() or 0)
    hi = int(p["sprtTrgtMaxAge"].strip() or 0) or 99
    age_ok = lo <= q.age <= hi
    job_ok = not q.unemployed or any(c in p["jobCd"] for c in (UNEMPLOYED, ANY_JOB))
    return in_region and age_ok and job_ok


def keyword_hits(p: Policy, q: Question) -> int:
    text = " ".join(p[f] for f in ("plcyNm", "plcyKywdNm", "plcyExplnCn", "plcySprtCn"))
    return sum(k in text for k in q.keywords)


def locality(p: Policy) -> int:
    """시군구 전용 2, 시도 전역 1, 전국 0. 사용자가 스스로 찾기 어려운 동네 정책을 앞에 둔다."""
    n = zip_count(p)
    return 2 if n <= 5 else 1 if n <= 30 else 0


def fit(p: Policy, q: Question) -> int:
    """조건이 사용자에게 '딱 맞게' 정해진 정도. 제한없음보다 미취업을 콕 집은 정책을 앞에 둔다."""
    score = 0
    if q.unemployed and UNEMPLOYED in p["jobCd"]:
        score += 1
    hi = int(p["sprtTrgtMaxAge"].strip() or 0)  # 나이 제한 표시값은 믿지 않는다(log/017)
    if hi and hi <= 39:
        score += 1
    return score


def closing_key(p: Policy) -> dt.date:
    return apply_end(p) or dt.date.max  # 상시·기간 없음은 뒤로


RANKERS: dict[str, Callable[[list[Policy], Question], list[Policy]]] = {
    "API 순서(최신 등록)": lambda ps, q: ps,
    "조회수": lambda ps, q: sorted(ps, key=lambda p: -int(p["inqCnt"] or 0)),
    "마감 임박": lambda ps, q: sorted(ps, key=closing_key),
    "지역 전용 우선": lambda ps, q: sorted(ps, key=lambda p: -locality(p)),
    "키워드 일치": lambda ps, q: sorted(ps, key=lambda p: -keyword_hits(p, q)),
    "조합(추천)": lambda ps, q: sorted(
        ps, key=lambda p: (-(2 * keyword_hits(p, q) + fit(p, q) + locality(p)), closing_key(p), -int(p["inqCnt"] or 0))),
}


def load(path: str) -> list[Policy]:
    data = json.loads((HERE / path).read_text(encoding="utf-8"))
    return data["result"]["youthPolicyList"]


def main() -> None:
    for q in QUESTIONS:
        policies = load(q.sample)
        candidates = [p for p in policies if eligible(p, q) and is_open(p)]
        print(f"\n## {q.name}\n받은 {len(policies)}건 → 조건·신청 가능 {len(candidates)}건 (키워드: {', '.join(q.keywords)})")
        for name, rank in RANKERS.items():
            top = rank(list(candidates), q)[:TOP_N]
            hits = sum(keyword_hits(p, q) > 0 for p in top)
            local = sum(locality(p) > 0 for p in top)
            print(f"\n### {name} — 키워드 일치 {hits}/{len(top)}, 지역(서울·구) 정책 {local}/{len(top)}")
            for i, p in enumerate(top, 1):
                end = apply_end(p)
                print(f"{i:2}. {p['plcyNm'][:40]} | {p['operInstCdNm'][:12]} | 키워드 {keyword_hits(p, q)} "
                      f"| 지역 {['전국', '시도', '구'][locality(p)]} | 마감 {end or '상시/없음'}")


if __name__ == "__main__":
    main()
