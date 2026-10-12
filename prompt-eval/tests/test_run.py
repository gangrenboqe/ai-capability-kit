"""run.py 测试：用例加载、四版本实测通过率、回退记录、空用例集报错。"""
import tempfile
import unittest
from pathlib import Path

# 保证从仓库根目录也能跑（CI 就是这么跑的）。
# 少了这两行，这些测试**只有 cd 进项目目录才通过** —— 自测覆盖不到真实用法。
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run import ROOT, evaluate, load_cases, load_prompt, render_compare, render_report
from backend import OfflineSimModel

CASES = load_cases(ROOT / "cases" / "cases.json")

# 实测值（2026-10-11，OfflineSimModel）。用例或模拟器改动会让这里失败——
# 失败是故意的：提醒同步重跑 python run.py --compare 并更新 README。
MEASURED = {"v1": 13, "v2": 23, "v3_draft": 18, "v3": 25}


class TestLoadCases(unittest.TestCase):
    def test_real_case_set_loads_25(self):
        self.assertEqual(len(CASES), 25)

    def test_empty_case_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.json"
            path.write_text('{"cases": []}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_cases(path)


class TestMeasuredRates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        backend = OfflineSimModel()
        cls.summaries = {}
        for stem, passed in MEASURED.items():
            system = load_prompt(ROOT / "prompts" / f"{stem}.md")
            cls.summaries[stem] = evaluate(system, CASES, backend)

    def test_v1_baseline_13(self):
        self.assertEqual(self.summaries["v1"]["passed"], MEASURED["v1"])

    def test_v2_23(self):
        self.assertEqual(self.summaries["v2"]["passed"], MEASURED["v2"])

    def test_v3_draft_regressed_to_18(self):
        self.assertEqual(self.summaries["v3_draft"]["passed"], MEASURED["v3_draft"])

    def test_v3_25(self):
        self.assertEqual(self.summaries["v3"]["passed"], MEASURED["v3"])

    def test_regression_record_is_locked_in(self):
        """SPEC 第五节：v3_draft 必须比 v2 差（变差又改回来的记录，用测试固化）。"""
        self.assertLess(self.summaries["v3_draft"]["passed"], self.summaries["v2"]["passed"])
        self.assertGreater(self.summaries["v3"]["passed"], self.summaries["v3_draft"]["passed"])

    def test_rates_distinguish_versions(self):
        """用例要有区分度：四个版本不能全一样。"""
        rates = {s["passed"] for s in self.summaries.values()}
        self.assertGreater(len(rates), 2)


class TestReports(unittest.TestCase):
    def test_render_report_contains_rate_and_failures(self):
        summary = evaluate(load_prompt(ROOT / "prompts" / "v1.md"), CASES, OfflineSimModel())
        report = render_report("v1", summary, CASES, "OfflineSimModel")
        self.assertIn(f"{summary['passed']}/{summary['total']}", report)
        self.assertIn("✗", report)  # v1 必有失败行

    def test_render_compare_matrix(self):
        reports = {
            stem: evaluate(load_prompt(ROOT / "prompts" / f"{stem}.md"), CASES, OfflineSimModel())
            for stem in MEASURED
        }
        text = render_compare(reports)
        for stem in MEASURED:
            self.assertIn(stem, text)
        self.assertIn("✔", text)
        self.assertIn("✗", text)
        self.assertIn("| N01 |", text)


if __name__ == "__main__":
    unittest.main()
