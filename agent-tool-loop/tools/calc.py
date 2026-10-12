"""工具：calc —— 安全的算术表达式求值。

用 AST 白名单（数字、+ - * / // % **、一元正负号、括号），**不用 eval**：
表达式里混入名字、函数调用、字符串都会得到明确报错，而不是执行任意代码。
"""
from __future__ import annotations

import ast
import operator

from agent_loop import ToolError

_MAX_LEN = 200
_MAX_EXPONENT = 1000
_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def calculate(expression: str) -> dict:
    """求值。返回 {"expression", "value", "text"}。非法输入 → ToolError。"""
    if not expression.strip():
        raise ToolError("expression 不能为空：请给出算术表达式，如 3*(4+5)")
    expression = expression.strip()
    if len(expression) > _MAX_LEN:
        raise ToolError(f"表达式过长（> {_MAX_LEN} 字符）")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        raise ToolError(
            f"表达式不是合法算式: {expression!r}（{type(exc).__name__}）"
        ) from exc
    value = _eval(tree.body)
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        raise ToolError("计算结果溢出")
    if abs(value) > 1e15:
        raise ToolError("计算结果超出范围（|value| > 1e15）")
    text = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    return {"expression": expression, "value": value, "text": text}


def _eval(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ToolError(f"只支持数字常量，不支持: {node.value!r}")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and isinstance(right, int) and abs(right) > _MAX_EXPONENT:
            raise ToolError(f"指数过大（|指数| > {_MAX_EXPONENT}）")
        try:
            return _BINOPS[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise ToolError("除数为零") from exc
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    raise ToolError(f"表达式包含不支持的语法: {type(node).__name__}")
