"""발급받은 API 키가 서비스마다 동작하는지 한 번씩 호출해 확인한다.

실행: 저장소 루트에서 `python3 experiments/api-survey/check_keys.py` (Windows는 `py experiments/api-survey/check_keys.py`)
키는 환경변수나 루트의 `.env`에서 읽는다. 키와 요청 URL은 출력하지 않고, 응답도 저장하지 않는다.
호출 수: 온통청년 1, 잡알리오 1, LH 2(목록 + 상세), 복지로 중앙부처 1, 복지로 지자체 1, Groq 1(모델 목록, 토큰 사용 없음).
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

TIMEOUT = 20


def load_env():
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def fetch(base, params, headers=None):
    url = base + ("?" + urllib.parse.urlencode(params) if params else "")
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            return res.status, res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        return None, f"연결 실패: {e.reason}"


def parse(body):
    try:
        return json.loads(body)
    except ValueError:
        return None


def find_key(data, key):
    if isinstance(data, dict):
        if key in data:
            return data[key]
        data = list(data.values())
    if isinstance(data, list):
        for item in data:
            found = find_key(item, key)
            if found is not None:
                return found
    return None


def find_dict_with(data, key):
    if isinstance(data, dict):
        if key in data:
            return data
        data = list(data.values())
    if isinstance(data, list):
        for item in data:
            found = find_dict_with(item, key)
            if found is not None:
                return found
    return None


def error_text(body):
    """data.go.kr 게이트웨이 오류는 XML이나 평문으로 온다."""
    for tag in ("returnAuthMsg", "errMsg", "resultMsg", "resultMessage"):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", body)
        if m:
            return m.group(1)
    return re.sub(r"\s+", " ", body)[:200]


def find_count(data, body, keys):
    for key in keys:
        found = find_key(data, key) if data is not None else None
        if found is None:
            m = re.search(rf"<{key}>(.*?)</{key}>", body)
            found = m.group(1) if m else None
        if found is not None:
            return key, found
    return None


def report(name, status, body, count_keys):
    """응답 형식(JSON·XML)과 필드 이름은 키로 받아 본 적이 없어 후보를 여럿 둔다."""
    data = parse(body)
    count = find_count(data, body, count_keys)
    ok = status == 200 and count is not None
    if ok:
        print(f"[OK]   {name}: {count[0]}={count[1]}")
    else:
        print(f"[FAIL] {name}: HTTP {status}, {error_text(body)}")
        if status == 200:
            print("       응답 앞부분:", re.sub(r"\s+", " ", body)[:300])
    return ok, data


def main():
    load_env()
    youth_key = os.environ.get("YOUTHCENTER_API_KEY", "")
    data_key = os.environ.get("DATA_GO_KR_SERVICE_KEY", "")
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not youth_key and not data_key and not groq_key:
        print("YOUTHCENTER_API_KEY, DATA_GO_KR_SERVICE_KEY, GROQ_API_KEY가 모두 비어 있다. .env를 확인한다.")
        return 1

    results = []

    if youth_key:
        status, body = fetch(
            "https://www.youthcenter.go.kr/go/ythip/getPlcy",
            {"apiKeyNm": youth_key, "pageNum": 1, "pageSize": 1, "rtnType": "json"},
        )
        results.append(report("온통청년 청년정책", status, body, ["totCount", "totalCount"])[0])
    else:
        print("[SKIP] 온통청년 청년정책: YOUTHCENTER_API_KEY가 비어 있다")

    if data_key:
        results += check_data_go_kr(data_key)
    else:
        print("[SKIP] 공공데이터포털 5개: DATA_GO_KR_SERVICE_KEY가 비어 있다")

    if groq_key:
        results.append(check_groq(groq_key))
    else:
        print("[SKIP] Groq: GROQ_API_KEY가 비어 있다")

    print(f"\n{sum(results)}/{len(results)} 통과")
    return 0 if all(results) else 1


def check_groq(key):
    """모델 목록만 조회한다. 토큰 한도를 쓰지 않는다."""
    status, body = fetch("https://api.groq.com/openai/v1/models", {},
                         {"Authorization": f"Bearer {key}", "User-Agent": "youth-policy-agent/check_keys"})
    data = parse(body) if status == 200 else None
    models = sorted(m.get("id", "") for m in (data or {}).get("data", []))
    if models:
        wanted = [m for m in models if m.startswith(("openai/gpt-oss", "qwen/"))]
        print(f"[OK]   Groq: 모델 {len(models)}개 사용 가능 (비교 후보: {', '.join(wanted) or '없음'})")
        return True
    print(f"[FAIL] Groq: HTTP {status}, {error_text(body)}")
    return False


def check_data_go_kr(data_key):
    results = []

    status, body = fetch(
        "https://apis.data.go.kr/1051000/recruitment/list",
        {"serviceKey": data_key, "pageNo": 1, "numOfRows": 1, "resultType": "json"},
    )
    results.append(report("잡알리오 채용공시 목록", status, body, ["totalCount"])[0])

    today = date.today()
    status, body = fetch(
        "https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1",
        {
            "serviceKey": data_key,
            "PG_SZ": 1,
            "PAGE": 1,
            "PAN_ST_DT": (today - timedelta(days=60)).strftime("%Y%m%d"),
            "PAN_ED_DT": today.strftime("%Y%m%d"),
        },
    )
    ok, lh_list = report("LH 분양임대공고 목록", status, body, ["ALL_CNT"])
    results.append(ok)

    notice = find_dict_with(lh_list, "PAN_ID") if ok else None
    if notice is None:
        print("[SKIP] LH 공고 상세: 목록에서 공고를 얻지 못했다")
        results.append(False)
    else:
        params = {"serviceKey": data_key}
        for key in ("SPL_INF_TP_CD", "CCR_CNNT_SYS_DS_CD", "PAN_ID", "UPP_AIS_TP_CD", "AIS_TP_CD"):
            if notice.get(key):
                params[key] = notice[key]
        status, body = fetch(
            "https://apis.data.go.kr/B552555/lhLeaseNoticeDtlInfo1/getLeaseNoticeDtlInfo1", params
        )
        results.append(report("LH 공고 상세", status, body, ["SS_CODE"])[0])

    status, body = fetch(
        "https://apis.data.go.kr/B554287/NationalWelfareInformationsV001/NationalWelfarelistV001",
        {
            "serviceKey": data_key,
            "callTp": "L",
            "pageNo": 1,
            "numOfRows": 1,
            "srchKeyCode": "001",
        },
    )
    results.append(report("복지로 중앙부처 목록", status, body, ["totalCount"])[0])

    status, body = fetch(
        "https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations/LcgvWelfarelist",
        {"serviceKey": data_key, "pageNo": 1, "numOfRows": 1},
    )
    results.append(report("복지로 지자체 목록", status, body, ["totalCount"])[0])
    return results


if __name__ == "__main__":
    sys.exit(main())
