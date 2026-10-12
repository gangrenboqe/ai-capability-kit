"""调用循环测试：正常链路 / 工具报错回填 / 超轮次兜底 / 空输入。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_loop import (  # noqa: E402
    BackendResponse,
    ModelBackend,
    ScriptedBackend,
    Tool,
    run_loop,
)
from demo import seed_db  # noqa: E402
from tools import build_registry  # noqa: E402


class LoopTestBase(unittest.TestCase):
    """每个用例一份独立临时库，随用例结束自动清理。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "sessions.db"
        seed_db(db)
        self.registry = build_registry(db_path=db)


class LoopNormalTest(LoopTestBase):
    def setUp(self):
        super().setUp()
        self.backend = ScriptedBackend()

    def test_single_tool_rounds(self):
        result = run_loop(self.backend, self.registry, "帮我搜索历史里关于「二元分词」的讨论")
        self.assertEqual(result["round_count"], 2)
        self.assertIn("找到 2 条", result["answer"])
        self.assertEqual(result["stopped"], "")

    def test_multi_tool_chain_uses_result(self):
        result = run_loop(
            self.backend,
            self.registry,
            "帮我搜索历史会话里关于「二元分词」的讨论，然后算一下命中条数乘以 3 等于多少",
        )
        self.assertEqual(result["round_count"], 3)
        self.assertIn("计算结果是 6", result["answer"])
        tools_called = [c["name"] for r in result["rounds"] for c in r["tool_calls"]]
        self.assertEqual(tools_called, ["search_history", "calc"])

    def test_no_tool_direct_answer(self):
        result = run_loop(self.backend, self.registry, "你好")
        self.assertEqual(result["round_count"], 1)
        self.assertIn("不需要工具", result["answer"])

    def test_trace_records_everything(self):
        result = run_loop(self.backend, self.registry, "帮我读一下「todo.txt」")
        trace = result["rounds"][0]
        self.assertEqual(trace["tool_calls"][0]["name"], "read_note")
        self.assertEqual(trace["tool_calls"][0]["arguments"], {"name": "todo.txt"})
        self.assertTrue(trace["tool_results"][0]["ok"])
        self.assertEqual(trace["tool_results"][0]["result"]["name"], "todo.txt")

    def test_system_message_accepted(self):
        result = run_loop(self.backend, self.registry, "你好", system="你是测试助手")
        self.assertEqual(result["round_count"], 1)


class LoopErrorFeedbackTest(LoopTestBase):
    """工具报错必须回填给模型继续回答，而不是整个请求失败。"""

    def setUp(self):
        super().setUp()
        self.backend = ScriptedBackend()

    def test_tool_error_fed_back(self):
        result = run_loop(self.backend, self.registry, "计算 1/0")
        self.assertEqual(result["stopped"], "")
        self.assertIn("返回错误", result["answer"])
        self.assertIn("除数为零", result["answer"])

    def test_unknown_tool_error_fed_back(self):
        class WeirdBackend(ModelBackend):
            def chat(self, messages, tools):
                last = messages[-1]
                if last.get("role") == "tool":
                    payload = json.loads(last["content"])
                    return BackendResponse(f"收到错误：{payload['error']}", [])
                return BackendResponse("", [{"id": "c1", "name": "ghost", "arguments": {}}])

        result = run_loop(WeirdBackend(), self.registry, "随便")
        self.assertIn("未知工具", result["answer"])

    def test_internal_exception_fed_back(self):
        def boom():
            raise RuntimeError("内部炸了")

        self.registry.register(Tool(name="boom", description="", parameters={}, func=boom))

        class BoomBackend(ModelBackend):
            def chat(self, messages, tools):
                last = messages[-1]
                if last.get("role") == "tool":
                    payload = json.loads(last["content"])
                    return BackendResponse(f"兜底：{payload['error']}", [])
                return BackendResponse("", [{"id": "c1", "name": "boom", "arguments": {}}])

        result = run_loop(BoomBackend(), self.registry, "触发")
        self.assertIn("工具内部异常 RuntimeError", result["answer"])
        self.assertIn("内部炸了", result["answer"])


class LoopBoundaryTest(LoopTestBase):
    def test_max_rounds_guard(self):
        class AlwaysTool(ModelBackend):
            def chat(self, messages, tools):
                return BackendResponse("", [{"id": "c", "name": "x", "arguments": {}}])

        result = run_loop(AlwaysTool(), self.registry, "问", max_rounds=3)
        self.assertEqual(result["stopped"], "max_rounds")
        self.assertEqual(result["answer"], "")
        self.assertEqual(result["round_count"], 3)

    def test_empty_user_message_no_tool(self):
        result = run_loop(ScriptedBackend(), self.registry, "")
        self.assertEqual(result["round_count"], 1)
        self.assertIn("不需要工具", result["answer"])


if __name__ == "__main__":
    unittest.main()
