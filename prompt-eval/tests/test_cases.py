"""用例集体检：25 条齐全、四类覆盖、每条有非空输入与非空断言。"""
import json
import unittest
from pathlib import Path

from scorer import _ASSERTION_KEYS

ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = ROOT / "cases" / "cases.json"


class TestCaseSet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
        cls.cases = data["cases"]

    def test_total_is_25(self):
        self.assertEqual(len(self.cases), 25)

    def test_category_counts(self):
        """SPEC 第三节：正常 ~10 / 边界 ~5 / 异常 ~5 / 对抗 ~5。"""
        counts = {}
        for case in self.cases:
            counts[case["category"]] = counts.get(case["category"], 0) + 1
        self.assertEqual(counts, {"normal": 10, "boundary": 5, "exception": 5, "adversarial": 5})

    def test_ids_unique_and_prefixed(self):
        ids = [case["id"] for case in self.cases]
        self.assertEqual(len(set(ids)), 25)
        for case in self.cases:
            prefix = case["id"][0]
            expected_category = {"N": "normal", "B": "boundary", "X": "exception", "D": "adversarial"}
            self.assertEqual(
                case["category"], expected_category[prefix], f"{case['id']} 前缀与类别不符"
            )

    def test_every_case_has_input_and_assertions(self):
        for case in self.cases:
            self.assertTrue(case["input"].strip(), f"{case['id']} 输入为空")
            expect = case["expect"]
            self.assertTrue(expect, f"{case['id']} 没有任何断言")
            unknown = set(expect) - _ASSERTION_KEYS
            self.assertFalse(unknown, f"{case['id']} 有未知断言字段: {unknown}")

    def test_no_case_is_trivially_always_pass(self):
        """不许挑能过的用例充数：断言不能是恒真（如 not_contains 一个必然没有的词）。"""
        for case in self.cases:
            expect = case["expect"]
            has_positive = any(key in expect for key in ("contains_all", "contains_any", "format", "json_keys", "min_len", "max_len", "tool"))
            self.assertTrue(
                has_positive or expect.get("not_contains"),
                f"{case['id']} 断言为空壳",
            )


if __name__ == "__main__":
    unittest.main()
