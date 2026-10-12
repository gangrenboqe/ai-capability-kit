"""ToolRegistry / Tool 参数校验测试：正常 / 异常 / 空数据。"""
import unittest

from agent_loop import Tool, ToolError, ToolRegistry


def make_tool(name: str = "t") -> Tool:
    return Tool(
        name=name,
        description="",
        parameters={
            "keyword": {"type": "string", "required": True},
            "limit": {"type": "integer", "required": False},
        },
        func=lambda keyword, limit=5: {"keyword": keyword, "limit": limit},
    )


class RegistryNormalTest(unittest.TestCase):
    def test_register_and_execute(self):
        registry = ToolRegistry()
        registry.register(make_tool())
        out = registry.execute("t", {"keyword": "abc", "limit": 3})
        self.assertEqual(out, {"keyword": "abc", "limit": 3})

    def test_optional_param_default(self):
        registry = ToolRegistry()
        registry.register(make_tool())
        out = registry.execute("t", {"keyword": "abc"})
        self.assertEqual(out["limit"], 5)

    def test_spec_list_shape(self):
        registry = ToolRegistry()
        registry.register(make_tool())
        specs = registry.spec_list()
        self.assertEqual(len(specs), 1)
        fn = specs[0]["function"]
        self.assertEqual(fn["name"], "t")
        self.assertEqual(fn["parameters"]["required"], ["keyword"])

    def test_none_treated_as_missing_optional(self):
        registry = ToolRegistry()
        registry.register(make_tool())
        out = registry.execute("t", {"keyword": "abc", "limit": None})
        self.assertEqual(out["limit"], 5)


class RegistryErrorTest(unittest.TestCase):
    def test_unknown_tool(self):
        registry = ToolRegistry()
        with self.assertRaises(ToolError) as ctx:
            registry.execute("nope", {})
        self.assertIn("未知工具", str(ctx.exception))

    def test_missing_required_param(self):
        registry = ToolRegistry()
        registry.register(make_tool())
        with self.assertRaises(ToolError) as ctx:
            registry.execute("t", {"limit": 3})
        self.assertIn("缺少必填参数: keyword", str(ctx.exception))

    def test_wrong_type(self):
        registry = ToolRegistry()
        registry.register(make_tool())
        with self.assertRaises(ToolError) as ctx:
            registry.execute("t", {"keyword": "abc", "limit": "3"})
        self.assertIn("类型应为 integer", str(ctx.exception))

    def test_bool_is_not_integer(self):
        registry = ToolRegistry()
        registry.register(make_tool())
        with self.assertRaises(ToolError):
            registry.execute("t", {"keyword": "abc", "limit": True})

    def test_non_dict_arguments(self):
        registry = ToolRegistry()
        registry.register(make_tool())
        with self.assertRaises(ToolError):
            registry.execute("t", ["keyword"])  # type: ignore[arg-type]

    def test_duplicate_register(self):
        registry = ToolRegistry()
        registry.register(make_tool())
        with self.assertRaises(ValueError):
            registry.register(make_tool())

    def test_unknown_param_type_decl(self):
        tool = Tool(
            name="w",
            description="",
            parameters={"x": {"type": "list"}},
            func=lambda x: {},
        )
        registry = ToolRegistry()
        registry.register(tool)
        with self.assertRaises(ToolError) as ctx:
            registry.execute("w", {"x": [1]})
        self.assertIn("未知类型", str(ctx.exception))


class RegistryEmptyTest(unittest.TestCase):
    def test_empty_registry_spec_list(self):
        self.assertEqual(ToolRegistry().spec_list(), [])

    def test_empty_registry_execute_lists_no_tools(self):
        with self.assertRaises(ToolError) as ctx:
            ToolRegistry().execute("x", {})
        self.assertIn("可用: 无", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
