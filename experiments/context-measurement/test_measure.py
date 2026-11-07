"""measure.py 테스트. 실제 API 응답 대신 손으로 만든 작은 샘플을 쓴다.

    python3 -m unittest experiments/context-measurement/test_measure.py
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import measure  # noqa: E402

JSON_SAMPLE = {
    "resultCode": 200,
    "result": {
        "pagging": {"totCount": 2},
        "youthPolicyList": [
            {"plcyNm": "청년 월세 지원", "addAplyQlfcCndCn": "무주택자", "etc": None},
            {"plcyNm": "청년 도약계좌", "addAplyQlfcCndCn": "", "etc": "x"},
        ],
    },
}

XML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>00</resultCode></header>
<body><items>
<item><title>행복주택 공고</title><region>서울</region></item>
<item><title>청년매입임대</title><region>부산</region></item>
<item><title>국민임대</title><region></region></item>
</items><totalCount>3</totalCount></body></response>"""


class MeasureTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_json_finds_policy_list_and_drops_empty_values(self):
        m = measure.measure(self.write("a.json", json.dumps(JSON_SAMPLE, ensure_ascii=False)), None)
        self.assertEqual(m.records, 2)
        self.assertLess(m.compact.chars, m.raw.chars)

    def test_xml_finds_repeated_items(self):
        m = measure.measure(self.write("a.xml", XML_SAMPLE), None)
        self.assertEqual(m.records, 3)

    def test_keep_shrinks_to_listed_fields(self):
        path = self.write("a.json", json.dumps(JSON_SAMPLE, ensure_ascii=False))
        m = measure.measure(path, ["plcyNm"])
        expected = json.dumps([{"plcyNm": "청년 월세 지원"}, {"plcyNm": "청년 도약계좌"}],
                              ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(m.kept.chars, len(expected))

    def test_refuses_sample_containing_key_param(self):
        path = self.write("leak.json", '{"url": "https://x/?serviceKey=abc", "items": []}')
        with self.assertRaises(ValueError):
            measure.measure(path, None)
        self.assertEqual(measure.main([str(path)]), 1)

    def test_keep_file_ignores_comments_and_blanks(self):
        path = self.write("keep.txt", "plcyNm  # 정책명\n\n# 주석\naddAplyQlfcCndCn\n")
        self.assertEqual(measure.read_keep(path), ["plcyNm", "addAplyQlfcCndCn"])


if __name__ == "__main__":
    unittest.main()
