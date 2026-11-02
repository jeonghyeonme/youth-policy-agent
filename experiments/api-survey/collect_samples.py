"""공공 API 응답 샘플을 받아 experiments/api-survey/samples/에 저장한다 (api-survey W2).

실행: 저장소 루트에서 `python3 experiments/api-survey/collect_samples.py` (Windows는 `py ...`)
키는 환경변수나 루트의 `.env`에서 읽는다. 키가 비어 있는 출처는 건너뛴다.
이미 받은 파일은 다시 호출하지 않으므로, 여러 번 실행해도 한도를 다시 쓰지 않는다.
저장 파일에는 원본 응답과 요청값을 남기되, 키와 요청 URL은 남기지 않는다.
"""

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_keys import fetch, find_key, load_env  # noqa: E402

SAMPLES = Path(__file__).resolve().parent / "samples"
DATA_GO_KR = "https://apis.data.go.kr"
YOUTH_PAGE_SIZE = 100
YOUTH_MAX_PAGES = 60


class Collector:
    def __init__(self, key, key_param):
        self.key = key
        self.key_param = key_param
        self.called = 0
        self.cached = 0

    def get(self, source, name, url, params):
        path = SAMPLES / source / f"{safe(name)}.json"
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved["status"] == 200:
                self.cached += 1
                return to_tree(saved["body"])
        status, body = fetch(url, {self.key_param: self.key, **params})
        self.called += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "source": source,
            "endpoint": url,
            "params": params,
            "status": status,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "body": body,
        }
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        if status != 200:
            print(f"  [FAIL] {source}/{name}: HTTP {status}")
            return None
        return to_tree(body)


def safe(name):
    return re.sub(r"[^0-9A-Za-z_.-]", "_", name)


def to_tree(body):
    """JSON이면 그대로, XML이면 dict·list로 바꿔 같은 방식으로 찾게 한다."""
    try:
        return json.loads(body)
    except ValueError:
        pass
    try:
        return xml_to_dict(ET.fromstring(body))
    except ET.ParseError:
        return None


def xml_to_dict(el):
    children = list(el)
    if not children:
        return (el.text or "").strip()
    out = {}
    for child in children:
        value = xml_to_dict(child)
        if child.tag in out:
            if not isinstance(out[child.tag], list):
                out[child.tag] = [out[child.tag]]
            out[child.tag].append(value)
        else:
            out[child.tag] = value
    return out


def records(tree, id_key):
    """응답 어디에 있든 id_key를 가진 dict를 모두 모은다."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if id_key in node:
                found.append(node)
                return
            node = list(node.values())
        if isinstance(node, list):
            for item in node:
                walk(item)

    walk(tree)
    return found


def jobalio(c):
    base = f"{DATA_GO_KR}/1051000/recruitment"
    items = []
    for page in (1, 2):
        tree = c.get("jobalio", f"list-p{page}", f"{base}/list",
                     {"pageNo": page, "numOfRows": 100, "ongoingYn": "Y", "resultType": "json"})
        items += records(tree, "recrutPblntSn")
    for item in items[:5]:
        sn = str(item["recrutPblntSn"])
        c.get("jobalio", f"detail-{sn}", f"{base}/detail", {"sn": sn, "resultType": "json"})
    return f"진행 중 공고 목록 {len(items)}건"


def lh(c):
    today = date.today()
    period = {"PAN_ST_DT": (today - timedelta(days=60)).strftime("%Y%m%d"),
              "PAN_ED_DT": today.strftime("%Y%m%d")}
    notices = []
    for page in (1, 2, 3):
        tree = c.get("lh", f"list-{period['PAN_ED_DT']}-p{page}",
                     f"{DATA_GO_KR}/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1",
                     {"PG_SZ": 100, "PAGE": page, **period})
        batch = records(tree, "PAN_ID")
        notices += batch
        if len(batch) < 100:
            break
    rental = [n for n in notices if "임대" in str(n.get("UPP_AIS_TP_NM", ""))]
    for n in (rental or notices)[:5]:
        params = {k: n[k] for k in ("SPL_INF_TP_CD", "CCR_CNNT_SYS_DS_CD", "PAN_ID",
                                    "UPP_AIS_TP_CD", "AIS_TP_CD") if n.get(k)}
        c.get("lh", f"detail-{n['PAN_ID']}",
              f"{DATA_GO_KR}/B552555/lhLeaseNoticeDtlInfo1/getLeaseNoticeDtlInfo1", params)
    return f"최근 60일 공고 {len(notices)}건 (임대 {len(rental)}건)"


def welfare_central(c):
    """하루 한도 100. 목록 1회와 상세 20건만 부른다."""
    base = f"{DATA_GO_KR}/B554287/NationalWelfareInformationsV001"
    tree = c.get("welfare-central", "list-all", f"{base}/NationalWelfarelistV001",
                 {"callTp": "L", "pageNo": 1, "numOfRows": 500, "srchKeyCode": "001"})
    services = records(tree, "servId")
    youth = [s for s in services if "청년" in str(s.get("lifeArray", ""))]
    for s in (youth + [s for s in services if s not in youth])[:20]:
        c.get("welfare-central", f"detail-{s['servId']}", f"{base}/NationalWelfaredetailedV001",
              {"callTp": "D", "servId": s["servId"]})
    return f"전체 {len(services)}건, 생애주기에 청년 포함 {len(youth)}건"


def welfare_local(c):
    base = f"{DATA_GO_KR}/B554287/LocalGovernmentWelfareInformations"
    services = []
    for page in (1, 2):
        tree = c.get("welfare-local", f"list-p{page}", f"{base}/LcgvWelfarelist",
                     {"pageNo": page, "numOfRows": 100})
        services += records(tree, "servId")
    youth = [s for s in services if "청년" in str(s.get("lifeNmArray", ""))]
    for s in (youth + [s for s in services if s not in youth])[:10]:
        c.get("welfare-local", f"detail-{s['servId']}", f"{base}/LcgvWelfaredetailed",
              {"servId": s["servId"]})
    return f"목록 {len(services)}건 중 생애주기에 청년 포함 {len(youth)}건"


def youthcenter(c):
    """전체 수집. 페이지가 비거나 pageSize보다 적게 오면 멈춘다."""
    total, reported = 0, None
    for page in range(1, YOUTH_MAX_PAGES + 1):
        tree = c.get("youthcenter", f"list-p{page:03d}",
                     "https://www.youthcenter.go.kr/go/ythip/getPlcy",
                     {"pageNum": page, "pageSize": YOUTH_PAGE_SIZE, "rtnType": "json"})
        reported = reported or find_key(tree, "totCount")
        batch = records(tree, "plcyNo")
        total += len(batch)
        if len(batch) < YOUTH_PAGE_SIZE:
            break
    return f"정책 {total}건 받음 (응답의 전체 건수 {reported})"


def main():
    load_env()
    data_key = os.environ.get("DATA_GO_KR_SERVICE_KEY", "")
    youth_key = os.environ.get("YOUTHCENTER_API_KEY", "")
    jobs = []
    if data_key:
        for source, run in (("잡알리오", jobalio), ("LH", lh),
                            ("복지로 중앙부처", welfare_central), ("복지로 지자체", welfare_local)):
            jobs.append((source, run, Collector(data_key, "serviceKey")))
    else:
        print("[SKIP] 공공데이터포털 4개 출처: DATA_GO_KR_SERVICE_KEY가 비어 있다")
    if youth_key:
        jobs.append(("온통청년", youthcenter, Collector(youth_key, "apiKeyNm")))
    else:
        print("[SKIP] 온통청년: YOUTHCENTER_API_KEY가 비어 있다")

    for source, run, c in jobs:
        print(f"{source}...")
        summary = run(c)
        print(f"  {summary} · 이번 호출 {c.called}회, 저장본 재사용 {c.cached}회")
    print(f"\n저장 위치: {SAMPLES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
