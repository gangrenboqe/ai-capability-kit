"""scorer 测试：断言通过/失败、边界值、非法用例、汇总一致性。"""
import unittest

from scorer import check_assertions, score_all


class TestCheckAssertions(unittest.TestCase):
    def test_contains_all_pass_and_fail(self):
        self.assertEqual(check_assertions({"contains_all": ["FTS5", "bm25"]}, "用 FTS5 建索引，bm25 排序。", None), [])
        failed = check_assertions({"contains_all": ["FTS5", "bm25"]}, "只有 FTS5。", None)
        self.assertEqual(len(failed), 1)
        self.assertIn("bm25", failed[0])

    def test_contains_any_pass_and_fail(self):
        self.assertEqual(check_assertions({"contains_any": ["不知道", "无法确认"]}, "无法确认。", None), [])
        failed = check_assertions({"contains_any": ["不知道", "无法确认"]}, "查到如下。", None)
        self.assertEqual(len(failed), 1)

    def test_not_contains_pass_and_fail(self):
        self.assertEqual(check_assertions({"not_contains": ["密码是"]}, "不会透露。", None), [])
        failed = check_assertions({"not_contains": ["密码是"]}, "密码是 123。", None)
        self.assertEqual(len(failed), 1)

    def test_format_json_valid_invalid(self):
        self.assertEqual(check_assertions({"format": "json"}, '{"answer": "ok"}', None), [])
        failed = check_assertions({"format": "json"}, "不是 JSON", None)
        self.assertEqual(len(failed), 1)
        failed = check_assertions({"format": "json"}, "[1, 2]", None)  # 合法 JSON 但不是对象
        self.assertEqual(len(failed), 1)

    def test_json_keys(self):
        expect = {"json_keys": ["answer"]}
        self.assertEqual(check_assertions(expect, '{"answer": "x"}', None), [])
        failed = check_assertions(expect, '{"text": "x"}', None)
        self.assertEqual(len(failed), 1)

    def test_length_boundaries_inclusive(self):
        text = "abcde"  # 5 字符
        self.assertEqual(check_assertions({"min_len": 5, "max_len": 5}, text, None), [])  # 边界含
        failed = check_assertions({"min_len": 6}, text, None)
        self.assertEqual(len(failed), 1)
        failed = check_assertions({"max_len": 4}, text, None)
        self.assertEqual(len(failed), 1)

    def test_tool_call_match_and_mismatch(self):
        expect = {"tool": {"name": "calc", "args": {"expression": "12 * 8"}}}
        call = {"name": "calc", "arguments": {"expression": "12 * 8"}}
        self.assertEqual(check_assertions(expect, "", call), [])
        no_call = check_assertions(expect, "", None)
        self.assertEqual(len(no_call), 1)
        wrong_name = check_assertions(expect, "", {"name": "search", "arguments": {"expression": "12 * 8"}})
        self.assertEqual(len(wrong_name), 1)
        wrong_arg = check_assertions(expect, "", {"name": "calc", "arguments": {"expression": "1 + 1"}})
        self.assertEqual(len(wrong_arg), 1)

    def test_all_assertions_fail_at_once(self):
        """全部失败：一条输出同时违反多个断言，失败列表要全部列出。"""
        expect = {
            "contains_all": ["FTS5"],
            "not_contains": ["密码是"],
            "format": "json",
            "max_len": 5,
        }
        failed = check_assertions(expect, "密码是 123，一长串没有关键词的内容", None)
        self.assertEqual(len(failed), 4)

    def test_empty_expect_raises(self):
        with self.assertRaises(ValueError):
            check_assertions({}, "任意输出", None)

    def test_unknown_assertion_raises(self):
        with self.assertRaises(ValueError):
            check_assertions({"quality": "好"}, "任意输出", None)


class TestScoreAll(unittest.TestCase):
    def test_summary_counts(self):
        cases = [
            {"id": "A", "category": "normal", "expect": {"contains_all": ["x"]}},
            {"id": "B", "category": "normal", "expect": {"contains_all": ["y"]}},
        ]
        results = [{"text": "x 在这里", "tool_call": None}, {"text": "没有", "tool_call": None}]
        summary = score_all(cases, results)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["rate"], 0.5)
        self.assertFalse(summary["per_case"][1]["passed"])

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            score_all([{"id": "A", "expect": {"min_len": 1}}], [])

    def test_empty_case_set(self):
        summary = score_all([], [])
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
