"""samples/의 원본 응답을 공통 정책 형식(schema.md)으로 옮기고, 필드별 채움률을 출력한다 (api-survey W3).

실행: 저장소 루트에서 `python3 experiments/api-survey/normalize.py` (Windows는 `py ...`)
`--out <파일>`을 주면 옮긴 레코드를 JSON Lines로 저장한다. 공공 API는 부르지 않는다.
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_samples import SAMPLES, records, to_tree  # noqa: E402

SIDO = {
    "서울": "서울", "부산": "부산", "대구": "대구", "인천": "인천", "광주": "광주", "대전": "대전",
    "울산": "울산", "세종": "세종", "경기": "경기", "강원": "강원", "충북": "충북", "충청북": "충북",
    "충남": "충남", "충청남": "충남", "전북": "전북", "전라북": "전북", "전남": "전남", "전라남": "전남",
    "경북": "경북", "경상북": "경북", "경남": "경남", "경상남": "경남", "제주": "제주",
}

# 온통청년 대분류는 옛 이름(복지문화, 교육, 참여권리)과 새 이름(금융･복지･문화 등)이 섞여 온다. 새 이름으로 맞춘다.
CATEGORY_NAMES = {
    "일자리": "일자리", "주거": "주거",
    "교육": "교육·직업훈련", "교육･직업훈련": "교육·직업훈련",
    "복지문화": "금융·복지·문화", "금융･복지･문화": "금융·복지·문화",
    "참여권리": "참여·기반", "참여･기반": "참여·기반",
}
CATEGORIES = sorted(set(CATEGORY_NAMES.values()))

# 복지로 관심주제를 공통 분류로 옮긴다. 없는 주제는 금융·복지·문화로 둔다.
WELFARE_THEME_TO_CATEGORY = {
    "일자리": "일자리", "주거": "주거", "교육": "교육·직업훈련", "법률": "참여·기반", "안전·위기": "참여·기반",
}

# 관심주제만으로는 "청년 주택임차보증금 이자 지원"이 서민금융(복지문화)으로만 분류된다. 제목 낱말로 보탠다.
TITLE_KEYWORD_TO_CATEGORY = {
    "주거": ("주거", "주택", "월세", "전세", "임차", "임대"),
    "일자리": ("취업", "일자리", "채용", "구직", "창업", "인턴"),
    "교육·직업훈련": ("교육", "학자금", "장학", "훈련"),
}

ELIGIBILITY_UNKNOWN = None


def sido_list(raw):
    """'전남광주통합특별시', '충청남도', '경기,서울' 같은 값을 짧은 시도명 목록으로 바꾼다."""
    if not raw:
        return []
    out = []
    for part in re.split(r"[,/·\s]+", raw):
        if not part:
            continue
        if part.startswith("전국"):
            return ["전국"]
        if part.startswith("전남광주"):
            out += ["전남", "광주"]
            continue
        for prefix, name in SIDO.items():
            if part.startswith(prefix):
                out.append(name)
                break
    return sorted(set(out))


def ymd(raw):
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) != 8 or digits.startswith("9999"):
        return None
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"


def split_names(raw):
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def texts(*pairs):
    return [{"label": label, "text": value.strip()} for label, value in pairs if value and value.strip()]


def policy(source, native_id, **fields):
    record = {
        "id": f"{source}:{native_id}",
        "source": source,
        "title": None,
        "summary": None,
        "categories": [],
        "regions": [],
        "period": {"start": None, "end": None, "status": "unknown"},
        "url": None,
        "eligibility": {
            "age": ELIGIBILITY_UNKNOWN,
            "income": ELIGIBILITY_UNKNOWN,
            "education": ELIGIBILITY_UNKNOWN,
            "job_status": ELIGIBILITY_UNKNOWN,
            "life_stages": ELIGIBILITY_UNKNOWN,
            "households": ELIGIBILITY_UNKNOWN,
            "texts": [],
            "in_attachment_only": False,
        },
        "benefit": None,
        "how_to_apply": None,
    }
    eligibility = fields.pop("eligibility", {})
    record.update(fields)
    record["eligibility"].update(eligibility)
    return record


def load_all(source, prefix, id_key):
    items = []
    for path in sorted((SAMPLES / source).glob(f"{prefix}*.json")):
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved["status"] == 200:
            items += records(to_tree(saved["body"]), id_key)
    return items


def jobalio():
    for j in load_all("jobalio", "list-", "recrutPblntSn"):
        education = split_names(j.get("acbgCondNmLst"))
        yield policy(
            "jobalio", j["recrutPblntSn"],
            title=f"[{j.get('instNm')}] {j.get('recrutPbancTtl')}",
            summary=" · ".join(filter(None, [j.get("hireTypeNmLst"), j.get("recrutSeNm"), j.get("ncsCdNmLst")])),
            categories=["일자리"],
            regions=sido_list(j.get("workRgnNmLst")),
            period={"start": ymd(j.get("pbancBgngYmd")), "end": ymd(j.get("pbancEndYmd")),
                    "status": "open" if j.get("ongoingYn") == "Y" else "closed"},
            url=(j.get("srcUrl") or "").strip() or None,
            eligibility={
                "education": [] if education == ["학력무관"] else education or ELIGIBILITY_UNKNOWN,
                "texts": texts(("신청자격", j.get("aplyQlfcCn")), ("결격사유", j.get("disqlfcRsn")),
                               ("우대조건", j.get("prefCn"))),
            },
            how_to_apply=j.get("scrnprcdrMthdExpln"),
        )


LH_STATUS = {"공고중": "open", "접수중": "open", "정정공고중": "open", "접수마감": "closed"}


def lh():
    """D2: 임대주택 공고만, 링크와 마감일만 쓴다."""
    seen = set()
    for n in load_all("lh", "list-", "PAN_ID"):
        if n.get("UPP_AIS_TP_NM") != "임대주택" or n["PAN_ID"] in seen:
            continue
        seen.add(n["PAN_ID"])
        yield policy(
            "lh", n["PAN_ID"],
            title=n.get("PAN_NM"),
            summary=n.get("AIS_TP_CD_NM"),
            categories=["주거"],
            regions=sido_list(n.get("CNP_CD_NM")),
            period={"start": ymd(n.get("PAN_NT_ST_DT")), "end": ymd(n.get("CLSG_DT")),
                    "status": LH_STATUS.get(n.get("PAN_SS"), "unknown")},
            url=n.get("DTL_URL"),
            eligibility={"in_attachment_only": True},
        )


def welfare_categories(themes, title):
    found = {WELFARE_THEME_TO_CATEGORY.get(t, "금융·복지·문화") for t in themes}
    found |= {c for c, words in TITLE_KEYWORD_TO_CATEGORY.items() if any(w in (title or "") for w in words)}
    return sorted(found)


def welfare_central():
    details = {d["servId"]: d for d in load_all("welfare-central", "detail-", "servId")}
    for s in load_all("welfare-central", "list-", "servId"):
        d = details.get(s["servId"], {})
        yield policy(
            "welfare-central", s["servId"],
            title=s.get("servNm"),
            summary=s.get("servDgst"),
            categories=welfare_categories(split_names(s.get("intrsThemaArray")), s.get("servNm")),
            regions=["전국"],
            period={"start": None, "end": None, "status": "always"},
            url=s.get("servDtlLink"),
            eligibility={
                "life_stages": split_names(s.get("lifeArray")) or ELIGIBILITY_UNKNOWN,
                "households": split_names(s.get("trgterIndvdlArray")) or ELIGIBILITY_UNKNOWN,
                "texts": texts(("지원대상", d.get("tgtrDtlCn")), ("선정기준", d.get("slctCritCn"))),
            },
            benefit=d.get("alwServCn"),
            how_to_apply=s.get("onapPsbltYn") == "Y" and "온라인 신청 가능" or None,
        )


def welfare_local():
    details = {d["servId"]: d for d in load_all("welfare-local", "detail-", "servId")}
    for s in load_all("welfare-local", "list-", "servId"):
        d = details.get(s["servId"], {})
        end = ymd(d.get("enfcEndYmd"))
        yield policy(
            "welfare-local", s["servId"],
            title=s.get("servNm"),
            summary=s.get("servDgst"),
            categories=welfare_categories(split_names(s.get("intrsThemaNmArray")), s.get("servNm")),
            regions=sido_list(s.get("ctpvNm")),
            period={"start": ymd(d.get("enfcBgngYmd")), "end": end,
                    "status": "unknown" if not d else ("always" if end is None else "open")},
            url=s.get("servDtlLink"),
            eligibility={
                "life_stages": split_names(s.get("lifeNmArray")) or ELIGIBILITY_UNKNOWN,
                "households": split_names(s.get("trgterIndvdlNmArray")) or ELIGIBILITY_UNKNOWN,
                "texts": texts(("지원대상", d.get("sprtTrgtCn")), ("선정기준", d.get("slctCritCn"))),
            },
            benefit=d.get("alwServCn"),
            how_to_apply=d.get("aplyMtdCn") or s.get("aplyMtdNm"),
        )


# 온통청년 지역코드(zipCd)는 5자리 시군구 코드다. 앞 두 자리로 시도를 정한다.
# 12는 샘플에 29(광주)와 46(전남)이 없고 12만 있어 전남광주통합특별시로 본다(추정).
ZIP_PREFIX_TO_SIDO = {
    "11": ["서울"], "12": ["광주", "전남"], "26": ["부산"], "27": ["대구"], "28": ["인천"], "29": ["광주"],
    "30": ["대전"], "31": ["울산"], "36": ["세종"], "41": ["경기"], "42": ["강원"], "43": ["충북"],
    "44": ["충남"], "45": ["전북"], "46": ["전남"], "47": ["경북"], "48": ["경남"], "50": ["제주"],
    "51": ["강원"], "52": ["전북"],
}
NATIONWIDE_ZIP_COUNT = 200

YOUTH_JOB = {"0013001": "재직자", "0013002": "자영업자", "0013003": "미취업자", "0013004": "프리랜서",
             "0013005": "일용근로자", "0013006": "(예비)창업자", "0013007": "단기근로자",
             "0013008": "영농종사자", "0013009": "기타"}
YOUTH_SCHOOL = {"0049001": "고졸 미만", "0049002": "고교 재학", "0049003": "고졸 예정", "0049004": "고교 졸업",
                "0049005": "대학 재학", "0049006": "대졸 예정", "0049007": "대학 졸업", "0049008": "석·박사",
                "0049009": "기타"}
NO_LIMIT_CODES = {"0013010", "0049010"}


def youth_codes(raw, names):
    """코드 목록을 이름 목록으로. '제한없음' 코드가 있으면 []."""
    codes = [c for c in (raw or "").split(",") if c]
    if not codes:
        return ELIGIBILITY_UNKNOWN
    if NO_LIMIT_CODES & set(codes):
        return []
    return [names.get(c, c) for c in codes]


def youth_regions(raw):
    zips = {z for z in (raw or "").split(",") if z}
    if len(zips) >= NATIONWIDE_ZIP_COUNT:
        return ["전국"]
    return sorted({sido for z in zips for sido in ZIP_PREFIX_TO_SIDO.get(z[:2], [])})


def youth_age(r):
    """최소·최대 나이가 둘 다 0이면 제한 없음. sprtTrgtAgeLmtYn은 값과 어긋나는 경우가 많아 쓰지 않는다."""
    lo, hi = int(r.get("sprtTrgtMinAge") or 0), int(r.get("sprtTrgtMaxAge") or 0)
    return {"min": lo or None, "max": hi or None}


def youth_income(r):
    kind = {"0043001": "none", "0043002": "annual", "0043003": "other"}.get(r.get("earnCndSeCd"))
    if kind is None:
        return ELIGIBILITY_UNKNOWN
    return {"type": kind, "min_10k_won": positive_int(r.get("earnMinAmt")),
            "max_10k_won": positive_int(r.get("earnMaxAmt"))}


def positive_int(raw):
    return int(raw) if (raw or "").isdigit() and int(raw) > 0 else None


def youth_period(r):
    kind = r.get("aplyPrdSeCd")
    if kind == "0057002":
        return {"start": None, "end": None, "status": "always"}
    m = re.match(r"(\d{8})\s*~\s*(\d{8})", r.get("aplyYmd") or "")
    start, end = (ymd(m.group(1)), ymd(m.group(2))) if m else (None, None)
    if kind == "0057003" or (end and end < date.today().isoformat()):
        status = "closed"
    else:
        status = "open" if end else "unknown"
    return {"start": start, "end": end, "status": status}


def youthcenter():
    for r in load_all("youthcenter", "list-", "plcyNo"):
        url = r.get("aplyUrlAddr") or r.get("refUrlAddr1") or r.get("refUrlAddr2") or (
            f"https://www.youthcenter.go.kr/youthPolicy/ythPlcyTotalSearch/ythPlcyDetail/{r['plcyNo']}")
        yield policy(
            "youthcenter", r["plcyNo"],
            title=r.get("plcyNm"),
            summary=r.get("plcyExplnCn"),
            categories=sorted({CATEGORY_NAMES.get(c.strip(), c.strip())
                               for c in (r.get("lclsfNm") or "").split(",") if c.strip()}),
            regions=youth_regions(r.get("zipCd")),
            period=youth_period(r),
            url=url.strip(),
            eligibility={
                "age": youth_age(r),
                "income": youth_income(r),
                "education": youth_codes(r.get("schoolCd"), YOUTH_SCHOOL),
                "job_status": youth_codes(r.get("jobCd"), YOUTH_JOB),
                "texts": texts(("추가신청자격", r.get("addAplyQlfcCndCn")), ("참여제한대상", r.get("ptcpPrpTrgtCn")),
                               ("소득기타", r.get("earnEtcCn"))),
            },
            benefit=r.get("plcySprtCn"),
            how_to_apply=r.get("plcyAplyMthdCn"),
        )


SOURCES = {"youthcenter": youthcenter, "jobalio": jobalio, "lh": lh,
           "welfare-central": welfare_central, "welfare-local": welfare_local}
REQUIRED = ("title", "url")


def filled(value):
    return value not in (None, "", [], ELIGIBILITY_UNKNOWN)


def coverage(rows):
    keys = ["title", "summary", "categories", "regions", "period.end", "url",
            "eligibility.age", "eligibility.income", "eligibility.education", "eligibility.job_status",
            "eligibility.life_stages",
            "eligibility.households", "eligibility.texts", "benefit"]
    counts = Counter()
    for r in rows:
        for k in keys:
            node = r
            for part in k.split("."):
                node = node.get(part) if isinstance(node, dict) else None
            counts[k] += filled(node)
    return {k: counts[k] for k in keys}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()

    all_rows, problems = [], []
    for source, run in SOURCES.items():
        rows = list(run())
        all_rows += rows
        for r in rows:
            missing = [k for k in REQUIRED if not r[k]]
            if missing:
                problems.append(f"{r['id']}: {', '.join(missing)} 없음")
        cov = coverage(rows)
        n = len(rows) or 1
        print(f"## {source}: {len(rows)}건")
        print("   " + " · ".join(f"{k} {cov[k] * 100 // n}%" for k in cov))

    if args.out:
        Path(args.out).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in all_rows), encoding="utf-8")
        print(f"\n{len(all_rows)}건 저장: {args.out}")
    if problems:
        print(f"\n필수 필드 누락 {len(problems)}건")
        for p in problems[:20]:
            print("  " + p)
        return 1
    print(f"\n전체 {len(all_rows)}건, 필수 필드(title, url) 누락 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
