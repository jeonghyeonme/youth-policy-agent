"""measure.py 테스트. 실제 API 응답 대신 손으로 만든 작은 샘플을 쓴다.

    python3 -m unittest experiments/context-measurement/test_measure.py
"""

import contextlib
import io
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
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(measure.main([str(path)]), 1)
        self.assertIn("servicekey", err.getvalue())

    def test_detail_document_is_one_record_not_its_small_sublist(self):
        xml = ("<wantedDtl><servNm>청년 월세 지원</servNm><slctCritCn>" + "무주택 " * 50 + "</slctCritCn>"
               "<inqplCtadrList><servSeDetailNm>a</servSeDetailNm></inqplCtadrList>"
               "<inqplCtadrList><servSeDetailNm>b</servSeDetailNm></inqplCtadrList></wantedDtl>")
        m = measure.measure(self.write("d.xml", xml), None)
        self.assertEqual(m.records, 1)
        self.assertGreater(m.compact.chars, 250)

    def test_single_json_document_does_not_grow_when_flattened(self):
        doc = {"resultCode": 200, "result": {"title": "공고", "aplyQlfcCn": "자격 " * 30,
                                              "steps": [{"name": "서류"}, {"name": "면접"}], "files": []}}
        m = measure.measure(self.write("j.json", json.dumps(doc, ensure_ascii=False)), None)
        self.assertEqual(m.records, 1)
        self.assertLessEqual(m.compact.chars, m.raw.chars)

    def test_blank_padded_values_count_as_empty(self):
        rec = measure.records_from_json({"list": [{"a": "        ", "b": "x"}, {"a": "", "b": "y"}]})
        self.assertEqual(measure.compact(rec), '[{"b":"x"},{"b":"y"}]')

    def test_token_columns_use_given_counter(self):
        m = measure.measure(self.write("a.json", json.dumps(JSON_SAMPLE, ensure_ascii=False)), ["plcyNm"])
        table = measure.to_markdown([m], count_tokens=lambda s: 7)
        self.assertIn("| 7 | 3 |", table)

    def test_keep_file_ignores_comments_and_blanks(self):
        path = self.write("keep.txt", "plcyNm  # 정책명\n\n# 주석\naddAplyQlfcCndCn\n")
        self.assertEqual(measure.read_keep(path), ["plcyNm", "addAplyQlfcCndCn"])


if __name__ == "__main__":
    unittest.main()
