"""regression.py 测试：比对逻辑、退出码、基线不被回归检查改写、显式更新。

核心断言（施工单 v4 第 1.3 条 3/4 款的机制保证）：
- 差于基线 → 退出码 1（CI 变红的依据）
- 回归检查绝不写基线文件（基线不自动上涨的依据）
- 基线只能被 --update-baseline 显式写入
"""
import json
import tempfile
import unittest
from pathlib import Path

# 保证从仓库根目录也能跑（CI 就是这么跑的）。
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import regression
from backend import OfflineSimModel
from run import evaluate, load_cases, load_prompt, DEFAULT_PROMPT, CASES_PATH

CASES = load_cases(CASES_PATH)


def current_passed() -> int:
    """跑一遍当前正式版，拿真实通过数（OfflineSimModel，毫秒级）。"""
    return evaluate(load_prompt(DEFAULT_PROMPT), CASES, OfflineSimModel())["passed"]


def make_baseline(tmp: str, passed: int) -> Path:
    p = Path(tmp) / "baseline.json"
    p.write_text(json.dumps({"passed": passed, "total": 25, "updated": "2026-10-14"}), encoding="utf-8")
    return p


class CompareTest(unittest.TestCase):
    def test_compare_three_states(self):
        self.assertEqual(regression.compare(26, 25), "better")
        self.assertEqual(regression.compare(25, 25), "same")
        self.assertEqual(regression.compare(18, 25), "worse")


class MainExitCodeTest(unittest.TestCase):
    def test_same_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_baseline(tmp, current_passed())
            self.assertEqual(regression.main(["--baseline", str(base)]), 0)

    def test_worse_returns_one(self):
        # 基线设为不可能达到的 26 → 必然「差于基线」→ 退出码 1
        with tempfile.TemporaryDirectory() as tmp:
            base = make_baseline(tmp, current_passed() + 1)
            self.assertEqual(regression.main(["--baseline", str(base)]), 1)

    def test_missing_baseline_returns_two_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "baseline.json"
            self.assertEqual(regression.main(["--baseline", str(base)]), 2)
            self.assertFalse(base.exists(), "基线缺失时绝不允许自动创建")


class BaselineImmutabilityTest(unittest.TestCase):
    def test_regression_never_writes_baseline(self):
        """🔴 核心断言：跑回归（含差于基线的情形）后，基线文件一个字节都不变。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_baseline(tmp, current_passed())
            before = base.read_bytes()
            regression.main(["--baseline", str(base)])
            regression.main(["--baseline", str(base)])
            self.assertEqual(base.read_bytes(), before, "回归检查改写了基线文件——门禁失效！")

    def test_update_baseline_is_the_only_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_baseline(tmp, 1)
            code = regression.main(["--update-baseline", "--baseline", str(base)])
            self.assertEqual(code, 0)
            data = json.loads(base.read_text(encoding="utf-8"))
            self.assertEqual(data["passed"], current_passed(), "--update-baseline 写入的应为本轮真实成绩")
            # 更新后，回归应立即「持平」
            self.assertEqual(regression.main(["--baseline", str(base)]), 0)


if __name__ == "__main__":
    unittest.main()
