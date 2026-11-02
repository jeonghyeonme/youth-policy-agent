"""청년 정책안의 서버 필터가 질문에 맞는 정책을 고르는지 LLM 없이 잰다 (Q7).

청년 정책 브랜치(claude/exciting-goldberg-y71yhi)의 수집 샘플 4,598건과 LLM 시험 질문 10개의 정답 조건을 쓴다.
LLM 해석은 완벽하다고 보고(시험 v1에서 50칸 중 50 정답), 코드 조건으로 거른 뒤 단순 키워드 순위 상위 3건을 보여 준다.

실행: 저장소 루트에서 `python3 experiments/youth-filter-check/check.py` (청년 정책 실험이 main에 합쳐진 뒤).
API·LLM을 부르지 않는다.
"""

import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "experiments/api-survey"))
from normalize import SOURCES  # noqa: E402

src = (root / "experiments/llm-providers/trial.py").read_text(encoding="utf-8")
CASES = eval("[" + re.search(r"INTERPRET_CASES = \[(.*?)\n\]", src, re.S).group(1) + "]")
OLD = {"교육": "교육·직업훈련", "복지문화": "금융·복지·문화", "참여권리": "참여·기반"}
STOP = set("요 은 는 이 가 을 를 에 에서 있나요 싶어요 주세요 알려 같은 데 하는 해요 있어요 없을까요 사는 살아요 하고".split())


def passes(r, g):
    if r["period"]["status"] == "closed":
        return False
    cats = {OLD.get(c, c) for c in r["categories"]}
    if cats and not (cats & g["categories"]):
        return False
    if g["region"] and r["regions"] and r["regions"] != ["전국"] and g["region"] not in r["regions"]:
        return False
    age = r["eligibility"]["age"]
    if g["age"] is not None and age:
        if age.get("min") is not None and g["age"] < age["min"]:
            return False
        if age.get("max") is not None and g["age"] > age["max"]:
            return False
    return True


def main():
    rows = [r for load in SOURCES.values() for r in load()]
    print(f"전체 {len(rows):,}건, 마감 제외 {sum(r['period']['status'] != 'closed' for r in rows):,}건")
    for case_id, question, gold in CASES:
        cand = [r for r in rows if passes(r, gold)]
        words = [w for w in re.findall(r"[가-힣A-Za-z]{2,}", question) if w not in STOP]
        text = lambda r: f"{r['title']} {r['summary'] or ''} {r['benefit'] or ''}"  # noqa: E731
        top = sorted(cand, key=lambda r: sum(text(r).count(w[:2]) for w in words), reverse=True)[:3]
        print(f"== {case_id} {question} → 후보 {len(cand)}건")
        for r in top:
            print(f"   - [{r['source']}] {r['title']}")


if __name__ == "__main__":
    main()
