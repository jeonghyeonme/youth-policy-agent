"""생필품 가격안 1단계: 참가격 API 데이터를 조금 받아 무엇이 있는지 본다 (Q7).

제안서가 "데이터 분석으로 확인"하기로 한 것을 실측한다: 판매점 수와 업태, 상품 수, 소모품(화장지·종이컵·커피믹스·생수) 존재,
할인·1+1 필드 채움 정도, 상품 하나당 가격이 있는 판매점 수, 최신 조사일.

API: 한국소비자원 생필품 가격 정보 (공공데이터포털 15158701) https://apis.data.go.kr/B551919/ProductPriceInfoService
키: .env의 DATA_GO_KR_SERVICE_KEY (공공데이터포털에서 이 서비스 활용신청 필요). 키는 출력·저장하지 않는다.
호출 수: 처음 실행에 약 30회(판매점 1~수 회, 상품 1~수 회, 기준정보 1회, 조사일 찾기 최대 12회, 가격 최대 24회).
응답은 cache/에 저장하고 같은 요청은 다시 보내지 않는다. 두 번째 실행부터는 호출하지 않는다.

실행: 저장소 루트에서 `python3 experiments/grocery-e2e/collect.py` (Windows는 `py ...`)
요약만 다시 보기: `--report`
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = "https://apis.data.go.kr/B551919/ProductPriceInfoService/"
CACHE = HERE / "cache"
SUMMARY = HERE / "survey.json"

# 질문에 쓸 품목. 상품명에 이 낱말이 들어간 상품을 최대 2개씩 골라 가격을 받는다.
ITEMS = ["우유", "라면", "세제", "커피믹스", "종이컵", "화장지", "생수", "식용유", "계란", "즉석밥", "햇반", "삼겹살"]
CONSUMABLES = ["화장지", "종이컵", "커피믹스", "생수"]


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


class Api:
    def __init__(self, key):
        self.key = key
        self.calls = 0
        self.last_error = None

    def get(self, op, params, key_name="ServiceKey"):
        """XML을 받아 cache/에 저장한다. 같은 요청은 cache에서 읽는다. 키는 cache 이름·내용에 넣지 않는다."""
        ident = json.dumps([op, sorted(params.items())], ensure_ascii=False)
        path = CACHE / f"{op.split('.')[0]}-{hashlib.sha1(ident.encode()).hexdigest()[:12]}.xml"
        if path.exists():
            return path.read_text(encoding="utf-8"), True
        if not self.key:
            raise SystemExit("cache에 없는 요청인데 DATA_GO_KR_SERVICE_KEY가 비어 있다")
        url = BASE + op + "?" + urllib.parse.urlencode({key_name: self.key, **params})
        self.calls += 1
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "grocery-e2e"}), timeout=30) as res:
                body = res.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"  [HTTP {e.code}] {op}: {body[:200]}")
            self.last_error = f"HTTP {e.code}: {body[:200]}"
            return body, False
        except urllib.error.URLError as e:
            raise SystemExit(f"연결 실패: {e.reason}")
        body = body.replace(self.key, "{KEY}")
        auth = re.search(r"<(returnAuthMsg|errMsg)>([^<]+)<", body)
        if auth and "NORMAL" not in auth.group(2):
            print(f"  [API 오류] {op}: {auth.group(2)}")
        self.last_error = None if (body.lstrip().startswith("<") and "SERVICE_KEY" not in body and "Unexpected" not in body) else body[:300]
        if self.last_error is None:
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        return body, False


def items_of(body):
    """응답 XML에서 항목들을 꺼낸다. 필드 이름을 모르므로 자식이 모두 글자뿐인 요소를 항목으로 본다."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return [], {"error": body[:300]}
    head = {el.tag: (el.text or "").strip() for el in root.iter() if el.tag in ("resultCode", "resultMsg", "totalCount", "numOfRows", "pageNo")}
    rows = []
    for el in root.iter():
        kids = list(el)
        if el.tag in ("header", "cmmMsgHeader"):
            continue
        if kids and all(len(k) == 0 for k in kids) and not any(k.tag in head for k in kids):
            rows.append({k.tag: (k.text or "").strip() for k in kids})
    return rows, head


def fetch_all(api, op, params, key_name="ServiceKey"):
    """페이지가 있으면 끝까지 받는다(최대 10쪽)."""
    rows, heads = [], []
    for page in range(1, 11):
        body, _ = api.get(op, {**params, "numOfRows": 1000, "pageNo": page}, key_name)
        got, head = items_of(body)
        heads.append(head)
        rows.extend(got)
        total = int(head.get("totalCount") or 0)
        if not got or not total or len(rows) >= total:
            break
    return rows, heads


def fridays_back(n):
    d = date.today()
    d -= timedelta(days=(d.weekday() - 4) % 7)
    return [(d - timedelta(weeks=i)).strftime("%Y%m%d") for i in range(n)]


def name_of(row):
    for k in ("goodName", "goodNm", "productName"):
        if row.get(k):
            return row[k]
    texts = [v for v in row.values() if re.search(r"[가-힣]", v or "")]
    return max(texts, key=len) if texts else ""


def fill_rate(rows, field):
    if not rows:
        return None
    return round(sum(bool((r.get(field) or "").strip()) and r.get(field) not in ("N", "0") for r in rows) / len(rows), 3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="저장된 요약만 다시 본다")
    args = parser.parse_args()
    if args.report:
        print(SUMMARY.read_text(encoding="utf-8"))
        return 0
    load_env()
    api = Api(os.environ.get("DATA_GO_KR_SERVICE_KEY", ""))
    out = {}

    stores, sh = fetch_all(api, "getStoreInfoSvc.do", {})
    products, ph = fetch_all(api, "getProductInfoSvc.do", {})
    std, _ = fetch_all(api, "getStandardInfoSvc.do", {"classCode": "AR"})
    if not stores and not products:
        print("판매점과 상품이 모두 0건이다. 데이터를 받지 못한 것으로 보고 요약 파일을 쓰지 않는다.")
        print("공공데이터포털에서 '한국소비자원_생필품 가격 정보'(15158701) 활용신청이 승인됐는지 확인한다.")
        if api.last_error:
            print(f"마지막 응답 앞부분(키는 지움): {api.last_error}")
        return 1
    out["판매점"] = {"건수": len(stores), "응답머리": sh[0] if sh else {}, "필드": sorted(stores[0]) if stores else [],
                  "예시": stores[:2]}
    out["상품"] = {"건수": len(products), "응답머리": ph[0] if ph else {}, "필드": sorted(products[0]) if products else [],
                 "예시": products[:2]}
    out["기준정보_AR"] = {"건수": len(std), "예시": std[:3]}
    for f in (sorted(stores[0]) if stores else []):
        vals = Counter(r.get(f, "") for r in stores)
        if 1 < len(vals) <= 30:
            out["판매점"].setdefault("값 분포(30종 이하 필드)", {})[f] = vals.most_common()
    out["소모품"] = {w: [name_of(p) for p in products if w in name_of(p)][:5] for w in CONSUMABLES}
    picks = {w: [p for p in products if w in name_of(p)][:2] for w in ITEMS}
    out["품목별 상품"] = {w: [name_of(p) for p in ps] for w, ps in picks.items()}

    gid_key = next((k for k in (products[0] if products else {}) if k.lower() in ("goodid", "good_id")), None)
    sample = next((p for ps in picks.values() for p in ps), None)
    day, price_op = None, None
    if gid_key and sample:
        for d in fridays_back(6):
            for op in ("getProductPriceInfoSvc.do", "getProductPriceInfoSvc"):
                rows, _ = fetch_all(api, op, {"goodInspectDay": d, "goodId": sample[gid_key]}, "serviceKey")
                if rows:
                    day, price_op = d, op
                    break
            if day:
                break
    out["최신 조사일"] = day
    prices = []
    if day:
        for w, ps in picks.items():
            for p in ps:
                rows, _ = fetch_all(api, price_op, {"goodInspectDay": day, "goodId": p[gid_key]}, "serviceKey")
                prices.extend({**r, "_item": w, "_name": name_of(p)} for r in rows)
    out["가격"] = {"건수": len(prices), "필드": sorted(prices[0]) if prices else [], "예시": prices[:3]}
    if prices:
        fields = [f for f in prices[0] if not f.startswith("_")]
        out["가격"]["필드 채움률"] = {f: fill_rate(prices, f) for f in fields}
        out["가격"]["상품당 판매점 수"] = Counter(r["_name"] for r in prices).most_common()
    out["이번 실행 API 호출"] = api.calls
    SUMMARY.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])
    print(f"\n이번 실행 API 호출 {api.calls}회. 요약은 {SUMMARY.relative_to(ROOT)}에 저장했다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
