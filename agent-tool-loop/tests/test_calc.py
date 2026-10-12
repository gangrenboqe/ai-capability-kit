"""calc 工具测试：正常 / 异常 / 空数据。"""
import unittest

from agent_loop import ToolError
from tools.calc import calculate


class CalcNormalTest(unittest.TestCase):
    def test_integer_arithmetic(self):
        self.assertEqual(calculate("1+2*3")["value"], 7)

    def test_parentheses_and_power(self):
        self.assertEqual(calculate("3*(4+5)")["value"], 27)
        self.assertEqual(calculate("2**10")["value"], 1024)

    def test_float_and_floor_div_and_mod(self):
        self.assertAlmostEqual(calculate("12 / 5")["value"], 2.4)
        self.assertEqual(calculate("12 // 5")["value"], 2)
        self.assertEqual(calculate("100 % 7")["value"], 2)

    def test_unary_minus(self):
        self.assertEqual(calculate("-5 + 3")["value"], -2)

    def test_result_fields(self):
        out = calculate("3*(4+5)")
        self.assertEqual(out["expression"], "3*(4+5)")
        self.assertEqual(out["text"], "27")


class CalcErrorTest(unittest.TestCase):
    def assert_tool_error(self, expression: str, keyword: str):
        with self.assertRaises(ToolError) as ctx:
            calculate(expression)
        self.assertIn(keyword, str(ctx.exception))

    def test_syntax_error(self):
        self.assert_tool_error("1+", "不是合法算式")

    def test_letters_rejected(self):
        self.assert_tool_error("abc+1", "不支持的语法")

    def test_bool_constant_rejected(self):
        self.assert_tool_error("True+1", "只支持数字常量")

    def test_function_call_rejected(self):
        self.assert_tool_error("__import__('os')", "不支持的语法")

    def test_division_by_zero(self):
        self.assert_tool_error("1/0", "除数为零")
        self.assert_tool_error("1//0", "除数为零")
        self.assert_tool_error("1%0", "除数为零")

    def test_exponent_too_large(self):
        self.assert_tool_error("9**99999", "指数过大")
        self.assert_tool_error("2**2**999", "指数过大")

    def test_overflow(self):
        self.assert_tool_error("1e308*10", "溢出")
        self.assert_tool_error("10**100", "超出范围")

    def test_too_long(self):
        self.assert_tool_error("1+" * 200, "表达式过长")


class CalcEmptyTest(unittest.TestCase):
    def test_empty_string(self):
        with self.assertRaises(ToolError) as ctx:
            calculate("   ")
        self.assertIn("不能为空", str(ctx.exception))

    def test_whitespace_only_via_registry(self):
        from agent_loop import Tool, ToolRegistry

        registry = ToolRegistry()
        registry.register(
            Tool(
                name="calc",
                description="",
                parameters={"expression": {"type": "string", "required": True}},
                func=calculate,
            )
        )
        with self.assertRaises(ToolError):
            registry.execute("calc", {"expression": " "})


if __name__ == "__main__":
    unittest.main()
