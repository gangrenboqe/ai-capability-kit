"""评测用例集与评测运行器测试（含验收标准 2 的复现：选对 20/20）。"""
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval_selection import judge, run_eval  # noqa: E402

CASE_FILE = PROJECT_ROOT / "eval_cases.json"


class CaseFileIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(CASE_FILE.read_text(encoding="utf-8"))
        self.cases = self.doc["cases"]

    def test_has_20_cases(self):
        self.assertEqual(len(self.cases), 20)

    def test_ids_unique(self):
        ids = [c["id"] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)))

    def test_required_fields_present(self):
        for case in self.cases:
            for key in ("id", "input", "expect_tool", "expect_args", "expect_answer_contains"):
                self.assertIn(key, case, f"{case.get('id')} 缺字段 {key}")

    def test_tool_distribution(self):
        tools = [c["expect_tool"] for c in self.cases]
        self.assertEqual(tools.count("search_history"), 7)
        self.assertEqual(tools.count("calc"), 5)
        self.assertEqual(tools.count("read_note"), 6)
        self.assertEqual(tools.count(None), 2)


class JudgeTest(unittest.TestCase):
    def test_pass_case(self):
        case = {"expect_tool": "calc", "expect_args": {"expression": "1+1"}, "expect_answer_contains": ["2"]}
        result = {
            "rounds": [{"tool_calls": [{"name": "calc", "arguments": {"expression": "1+1"}}]}],
            "answer": "计算结果是 2",
        }
        ok, reasons = judge(case, result)
        self.assertTrue(ok, reasons)

    def test_fail_wrong_tool(self):
        case = {"expect_tool": "calc", "expect_args": {}, "expect_answer_contains": []}
        result = {"rounds": [{"tool_calls": [{"name": "read_note", "arguments": {}}]}], "answer": ""}
        ok, reasons = judge(case, result)
        self.assertFalse(ok)
        self.assertTrue(any("首个工具" in r for r in reasons))

    def test_fail_no_tool_when_expected(self):
        case = {"expect_tool": "calc", "expect_args": {}, "expect_answer_contains": []}
        result = {"rounds": [], "answer": ""}
        ok, _ = judge(case, result)
        self.assertFalse(ok)

    def test_fail_tool_called_when_not_expected(self):
        case = {"expect_tool": None, "expect_args": {}, "expect_answer_contains": []}
        result = {"rounds": [{"tool_calls": [{"name": "calc", "arguments": {}}]}], "answer": ""}
        ok, reasons = judge(case, result)
        self.assertFalse(ok)
        self.assertTrue(any("不应调用工具" in r for r in reasons))

    def test_fail_missing_keyword(self):
        case = {"expect_tool": None, "expect_args": {}, "expect_answer_contains": ["关键词"]}
        result = {"rounds": [], "answer": "没有这个词"}
        ok, reasons = judge(case, result)
        self.assertFalse(ok)
        self.assertIn("回答缺少关键词: 关键词", reasons[0])


class EvalRunTest(unittest.TestCase):
    def test_full_eval_20_of_20(self):
        passed, total, rows = run_eval()
        self.assertEqual(total, 20)
        self.assertEqual(passed, 20, [r for r in rows if not r["ok"]])


if __name__ == "__main__":
    unittest.main()
