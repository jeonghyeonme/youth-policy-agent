"""대표 질문 A·B(D2) 조건으로 후보 API를 한 번씩 불러 응답 샘플을 저장한다.

사람이 로컬에서 실행한다. AI 도구는 실행하지 않는다(AGENTS.md "API 키").

    py experiments/context-measurement/fetch_samples.py          # Windows
    python3 experiments/context-measurement/fetch_samples.py     # macOS·Linux

- 키는 저장소 루트의 .env 또는 환경변수에서 읽는다. 키가 없는 API는 건너뛴다.
- 이미 저장된 샘플은 다시 부르지 않는다(트래픽 보호). 다시 받으려면 --force.
- 응답과 실행 기록(samples/fetch_log.md)에 키 값이 남지 않게 지운다.
- 상세 조회는 API마다 질문당 DETAIL_LIMIT건까지만 부른다. 한 번 실행에 최대 약 40회 호출.

끝나면 samples/ 폴더를 커밋해 push한다. fetch_log.md에 각 호출의 HTTP 상태와 실패 이유가 있다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SAMPLES = HERE / "samples"
DETAIL_LIMIT = 5
TIMEOUT = 20

YOUTH_KEY = "YOUTHCENTER_API_KEY"
DATA_KEY = "DATA_GO_KR_SERVICE_KEY"


@dataclass
class Call:
    api: str            # samples/ 아래 폴더 이름
    name: str           # 파일 이름(확장자 제외)
    url: str
    params: dict[str, str]
    key_env: str
    key_param: str
    ext: str = "xml"
    detail: "Detail | None" = None
    note: str = ""      # 문서로 확인 못 한 추정이면 적는다


@dataclass
class Detail:
    """목록 응답에서 ID를 뽑아 상세를 부른다."""
    id_pattern: str
    url: str
    id_param: str
    params: dict[str, str] = field(default_factory=dict)


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        env[name.strip()] = value.strip().strip('"').strip("'")
    return env


def normalize_key(key: str) -> str:
    """공공데이터포털은 인코딩·디코딩 키를 둘 다 준다. 어느 쪽을 넣어도 한 번만 인코딩되게 디코딩 값으로 맞춘다."""
    return urllib.parse.unquote(key) if "%" in key else key


def scrub(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***").replace(urllib.parse.quote(s, safe=""), "***")
    return text


def extract_ids(text: str, pattern: str, limit: int) -> list[str]:
    seen: list[str] = []
    for m in re.finditer(pattern, text):
        if m.group(1) not in seen:
            seen.append(m.group(1))
        if len(seen) == limit:
            break
    return seen


def calls() -> list[Call]:
    today = dt.date.today()
    since = (today - dt.timedelta(days=90)).strftime("%Y.%m.%d")
    until = (today + dt.timedelta(days=60)).strftime("%Y.%m.%d")

    youth_new = "https://www.youthcenter.go.kr/go/ythip/getPlcy"
    jobalio = "https://apis.data.go.kr/1051000/recruitment"
    lh = "https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1"
    natl = "https://apis.data.go.kr/B554287/NationalWelfareInformationsV001"
    local = "https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations"

    natl_detail = Detail(r"<servId>([^<]+)</servId>", f"{natl}/NationalWelfaredetailedV001", "servId", {"callTp": "D"})
    local_detail = Detail(r"<servId>([^<]+)</servId>", f"{local}/LcgvWelfaredetailed", "servId")
    job_detail = Detail(r'"recrutPblntSn"\s*:\s*"?(\d+)', f"{jobalio}/detail", "sn", {"resultType": "json"})

    return [
        # 온통청년: 개편 주소만 쓴다. 옛 주소(/opi/youthPlcyList.do)는 2026-11-08 시간 초과(api-survey.md)
        Call("youthcenter", "A_list", youth_new, {"pageNum": "1", "pageSize": "100", "rtnType": "json", "lclsfNm": "일자리"},
             YOUTH_KEY, "apiKeyNm", ext="json"),
        Call("youthcenter", "B_list", youth_new, {"pageNum": "1", "pageSize": "100", "rtnType": "json", "lclsfNm": "주거"},
             YOUTH_KEY, "apiKeyNm", ext="json"),
        # 온통청년 지역 필터 확인(log/011): zipCd가 요청에서 동작하는지, 5자리·시도 앞자리·여러 개 중 무엇을 받는지.
        # 거르지 못하면 totCount가 A_list와 같은 1,503으로 나온다.
        Call("youthcenter", "probe_zip_11110", youth_new,
             {"pageNum": "1", "pageSize": "100", "rtnType": "json", "lclsfNm": "일자리", "zipCd": "11110"},
             YOUTH_KEY, "apiKeyNm", ext="json", note="지역 필터 확인: 종로구 5자리"),
        Call("youthcenter", "probe_zip_11", youth_new,
             {"pageNum": "1", "pageSize": "100", "rtnType": "json", "lclsfNm": "일자리", "zipCd": "11"},
             YOUTH_KEY, "apiKeyNm", ext="json", note="지역 필터 확인: 서울 앞자리 2자리"),
        Call("youthcenter", "probe_zip_multi", youth_new,
             {"pageNum": "1", "pageSize": "100", "rtnType": "json", "lclsfNm": "일자리", "zipCd": "11110,11680"},
             YOUTH_KEY, "apiKeyNm", ext="json", note="지역 필터 확인: 종로구·강남구 두 개"),
        # Q3 확인(log/015): 정책 키워드·중분류로 요청 단계에서 좁힐 수 있는지. 못 거르면 totCount가 297(종로구·일자리)로 나온다.
        Call("youthcenter", "probe_kywd_subsidy", youth_new,
             {"pageNum": "1", "pageSize": "100", "rtnType": "json", "lclsfNm": "일자리", "zipCd": "11110", "plcyKywdNm": "보조금"},
             YOUTH_KEY, "apiKeyNm", ext="json", note="Q3 확인: 정책 키워드 보조금"),
        Call("youthcenter", "probe_mclsf_job", youth_new,
             {"pageNum": "1", "pageSize": "100", "rtnType": "json", "lclsfNm": "일자리", "zipCd": "11110", "mclsfNm": "취업"},
             YOUTH_KEY, "apiKeyNm", ext="json", note="Q3 확인: 중분류 취업"),
        # 잡알리오: A(취업)
        Call("jobalio", "A_list", f"{jobalio}/list", {"resultType": "json", "numOfRows": "50", "pageNo": "1", "ongoingYn": "Y"},
             DATA_KEY, "serviceKey", ext="json", detail=job_detail, note="상세 경로(/detail)는 추정"),
        # LH: B(주거) — 서울(11), 임대주택(06)
        Call("lh", "B_list", lh, {"PG_SZ": "50", "PAGE": "1", "UPP_AIS_TP_CD": "06", "CNP_CD": "11",
                                  "PAN_NT_ST_DT": since, "CLSG_DT": until},
             DATA_KEY, "ServiceKey", ext="json"),
        # 복지로 중앙부처: 개발계정 하루 100 — 목록 2 + 상세 최대 10
        Call("welfare_national", "A_list", f"{natl}/NationalWelfarelistV001",
             {"callTp": "L", "pageNo": "1", "numOfRows": "100", "srchKeyCode": "003", "age": "26"},
             DATA_KEY, "serviceKey", detail=natl_detail),
        Call("welfare_national", "B_list", f"{natl}/NationalWelfarelistV001",
             {"callTp": "L", "pageNo": "1", "numOfRows": "100", "srchKeyCode": "003", "age": "27", "searchWrd": "월세"},
             DATA_KEY, "serviceKey", detail=natl_detail),
        # 복지로 지자체: 지역은 이름 문자열
        Call("welfare_local", "A_list", f"{local}/LcgvWelfarelist",
             {"pageNo": "1", "numOfRows": "100", "age": "26"},
             DATA_KEY, "serviceKey", detail=local_detail, note="오퍼레이션 경로는 추정"),
        Call("welfare_local", "B_list", f"{local}/LcgvWelfarelist",
             {"pageNo": "1", "numOfRows": "100", "searchWrd": "월세"},
             DATA_KEY, "serviceKey", detail=local_detail, note="오퍼레이션 경로는 추정"),
    ]


def fetch(url: str, params: dict[str, str], key_param: str, key: str) -> tuple[int, str]:
    query = urllib.parse.urlencode({key_param: key, **params})
    req = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "youth-policy-agent-sampler"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            return res.status, res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        return 0, f"연결 실패: {e}"


def looks_like_error(status: int, body: str) -> bool:
    return status != 200 or bool(re.search(r"SERVICE_KEY|ERROR|<returnAuthMsg>|resultCode\"?\s*[:>]\s*\"?(?!00|200|0\b)\d", body[:2000]))


def run_one(api: str, name: str, ext: str, url: str, params: dict[str, str], key_param: str, key: str,
            secrets: list[str], force: bool, log: list[str]) -> str | None:
    path = SAMPLES / api / f"{name}.{ext}"
    if path.exists() and not force:
        log.append(f"| {api}/{name} | 건너뜀(이미 있음) | - | |")
        return path.read_text(encoding="utf-8")
    status, body = fetch(url, params, key_param, key)
    body = scrub(body, secrets)
    if looks_like_error(status, body):
        snippet = re.sub(r"\s+", " ", body[:200]).replace("|", "/")
        log.append(f"| {api}/{name} | 실패 HTTP {status} | - | {snippet} |")
        print(f"  ✗ {api}/{name}: HTTP {status}")
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    log.append(f"| {api}/{name} | 저장 HTTP {status} | {len(body.encode('utf-8')):,} B | |")
    print(f"  ✓ {api}/{name}: {path.relative_to(ROOT)}")
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="이미 저장된 샘플도 다시 받는다")
    args = parser.parse_args(argv)

    env = {**load_env(ROOT / ".env"), **{k: v for k, v in os.environ.items() if k in (YOUTH_KEY, DATA_KEY)}}
    keys = {name: normalize_key(env[name]) for name in (YOUTH_KEY, DATA_KEY) if env.get(name)}
    secrets = list(keys.values())
    if not keys:
        print(f".env에 {YOUTH_KEY} 또는 {DATA_KEY}가 없다. 저장소 루트의 .env를 확인한다.")
        return 1

    log = ["| 호출 | 결과 | 크기 | 비고(실패 시 응답 앞부분) |", "| --- | --- | --- | --- |"]
    for c in calls():
        key = keys.get(c.key_env)
        if not key:
            log.append(f"| {c.api}/{c.name} | 건너뜀({c.key_env} 없음) | - | |")
            print(f"  - {c.api}/{c.name}: {c.key_env} 없음, 건너뜀")
            continue
        body = run_one(c.api, c.name, c.ext, c.url, c.params, c.key_param, key, secrets, args.force, log)
        if c.note:
            log[-1] = log[-1].rstrip("|").rstrip() + f" {c.note} |"
        if body is None or c.detail is None:
            continue
        d = c.detail
        for i, item_id in enumerate(extract_ids(body, d.id_pattern, DETAIL_LIMIT), 1):
            run_one(c.api, f"{c.name.split('_')[0]}_detail_{i}", c.ext, d.url, {**d.params, d.id_param: item_id},
                    c.key_param, key, secrets, args.force, log)

    SAMPLES.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    (SAMPLES / "fetch_log.md").write_text(
        f"# 샘플 수집 기록 ({stamp})\n\n> fetch_samples.py가 썼다. 키 값은 지웠다.\n\n" + "\n".join(log) + "\n",
        encoding="utf-8")
    print(f"\n기록: {(SAMPLES / 'fetch_log.md').relative_to(ROOT)}  — samples/ 폴더를 커밋해 push한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
