"""eval_selection 的关键路径测试（43-batch 补测）。

eval_selection.py 是 README「工具选对 20/20」结论的生产者，此前没有直测——
它若悄悄坏掉（judge 判反 / 基线文件格式松动），评测结论会错而流程不报错。
这里只测纯函数：judge / load_baseline / write_baseline / render_report / make_backend（offline），
不跑完整评测循环（那是 run_eval 的事，live 后端也不在此测）。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval_selection import (  # noqa: E402
    ScriptedBackend,
    judge,
    load_baseline,
    make_backend,
    render_report,
    write_baseline,
)


def make_case(**over) -> dict:
    case = {
        "id": "T01",
        "input": "算一下 3+4",
        "expect_tool": "calc",
        "expect_args": {"expression": "3+4"},
        "expect_answer_contains": ["7"],
    }
    case.update(over)
    return case


def make_result(**over) -> dict:
    result = {
        "rounds": [
            {"tool_calls": [{"name": "calc", "arguments": {"expression": "3+4"}}]}
        ],
        "answer": "结果是 7",
    }
    result.update(over)
    return result


class MakeBackendTest(unittest.TestCase):
    def test_offline_is_default(self):
        """没设环境变量时必须落在离线确定性后端——回归基线的前提。"""
        os.environ.pop("PAI_EVAL_BACKEND", None)
        backend, desc = make_backend()
        self.assertIsInstance(backend, ScriptedBackend)
        self.assertIn("离线", desc)

    def test_offline_explicit(self):
        os.environ["PAI_EVAL_BACKEND"] = "OFFLINE"  # 大小写不敏感
        try:
            backend, _ = make_backend()
            self.assertIsInstance(backend, ScriptedBackend)
        finally:
            os.environ.pop("PAI_EVAL_BACKEND", None)


class JudgeTest(unittest.TestCase):
    def test_pass_when_tool_args_answer_all_match(self):
        ok, reasons = judge(make_case(), make_result())
        self.assertTrue(ok)
        self.assertEqual(reasons, [])

    def test_fail_when_wrong_tool(self):
        result = make_result(rounds=[{"tool_calls": [{"name": "read_note", "arguments": {}}]}])
        ok, reasons = judge(make_case(), result)
        self.assertFalse(ok)
        self.assertTrue(any("首个工具" in r for r in reasons))

    def test_fail_when_no_tool_called(self):
        result = make_result(rounds=[{"tool_calls": []}])
        ok, reasons = judge(make_case(), result)
        self.assertFalse(ok)
        self.assertTrue(any("没有调用" in r for r in reasons))

    def test_fail_when_tool_called_but_none_expected(self):
        case = make_case(expect_tool=None, expect_args=None)
        ok, reasons = judge(case, make_result())
        self.assertFalse(ok)
        self.assertTrue(any("不应调用工具" in r for r in reasons))

    def test_fail_when_answer_missing_keyword(self):
        result = make_result(answer="结果是八")   # 不能含期望关键词「7」
        ok, reasons = judge(make_case(), result)
        self.assertFalse(ok)
        self.assertTrue(any("缺少关键词" in r for r in reasons))

    def test_fail_when_args_mismatch(self):
        result = make_result(rounds=[{"tool_calls": [
            {"name": "calc", "arguments": {"expression": "3*4"}}]}])
        ok, reasons = judge(make_case(), result)
        self.assertFalse(ok)
        self.assertTrue(any("参数 expression" in r for r in reasons))


class BaselineTest(unittest.TestCase):
    def test_missing_baseline_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_baseline(Path(tmp) / "nope.json"))

    def test_invalid_baseline_raises(self):
        """基线文件缺整数字段必须炸出来，不能静默当成 0/0 比下去。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "baseline.json"
            p.write_text(json.dumps({"passed": "20", "total": 20}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_baseline(p)

    def test_write_then_load_roundtrip(self):
        os.environ.pop("PAI_EVAL_BACKEND", None)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "baseline.json"
            write_baseline(p, 20, 20)
            data = load_baseline(p)
            self.assertEqual(data["passed"], 20)
            self.assertEqual(data["total"], 20)
            self.assertIn("离线", data["backend"])


class RenderReportTest(unittest.TestCase):
    def test_report_has_pass_and_fail_rows(self):
        os.environ.pop("PAI_EVAL_BACKEND", None)
        rows = [
            {"id": "T01", "input": "算一下 3+4", "ok": True, "reasons": []},
            {"id": "T02", "input": "读一下备忘录", "ok": False, "reasons": ["首个工具 calc != 期望 read_note"]},
        ]
        report = render_report(1, 2, rows)
        self.assertIn("选对 1/2", report)
        self.assertIn("PASS", report)
        self.assertIn("FAIL", report)
        self.assertIn("首个工具", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
