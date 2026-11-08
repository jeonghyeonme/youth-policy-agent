"""fetch_samples.py의 네트워크 없는 부분만 테스트한다. API를 부르지 않는다."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fetch_samples as fs  # noqa: E402


class FetchHelpersTest(unittest.TestCase):
    def test_env_file_parsing(self):
        path = Path(tempfile.mkdtemp()) / ".env"
        path.write_text('# 주석\nYOUTHCENTER_API_KEY="abc"\n\nDATA_GO_KR_SERVICE_KEY=x%2By\nLLM_API_KEY=\n', encoding="utf-8")
        env = fs.load_env(path)
        self.assertEqual(env["YOUTHCENTER_API_KEY"], "abc")
        self.assertEqual(env["LLM_API_KEY"], "")

    def test_encoded_and_decoded_key_become_same(self):
        self.assertEqual(fs.normalize_key("a%2Bb%3D%3D"), fs.normalize_key("a+b=="))

    def test_scrub_removes_raw_and_encoded_key(self):
        text = "echo a+b== and a%2Bb%3D%3D"
        self.assertEqual(fs.scrub(text, ["a+b=="]), "echo *** and ***")

    def test_extract_ids_dedupes_and_limits(self):
        xml = "<servId>W1</servId><servId>W1</servId><servId>W2</servId><servId>W3</servId>"
        self.assertEqual(fs.extract_ids(xml, r"<servId>([^<]+)</servId>", 2), ["W1", "W2"])

    def test_error_detection(self):
        self.assertTrue(fs.looks_like_error(200, "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"))
        self.assertTrue(fs.looks_like_error(500, "ok"))
        self.assertFalse(fs.looks_like_error(200, "<resultCode>00</resultCode><items/>"))
        self.assertFalse(fs.looks_like_error(200, '{"resultCode":200,"result":[]}'))

    def test_call_budget_stays_small(self):
        lists = fs.calls()
        details = sum(fs.DETAIL_LIMIT for c in lists if c.detail)
        self.assertLessEqual(len(lists) + details, 40)
        national = [c for c in lists if c.api == "welfare_national"]
        self.assertLessEqual(len(national) * (1 + fs.DETAIL_LIMIT), 100 // 5)


if __name__ == "__main__":
    unittest.main()
