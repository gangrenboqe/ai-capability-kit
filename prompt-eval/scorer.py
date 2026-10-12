"""客观打分器：只用可复算的断言，禁止主观评分（SPEC 第四节）。

打分对象是模型的原始输出文本（result["text"]）与工具调用（result["tool_call"]）。
expect 支持的断言（至少一项，否则视为坏用例报 ValueError）：

- contains_all: list[str]            这些子串必须全部出现在输出里
- contains_any: list[str]            至少一个子串出现
- not_contains: list[str]            这些子串一个都不能出现
- format: "json"                     原始输出必须能解析成 JSON 对象
- json_keys: list[str]               JSON 对象必须包含这些键（隐含要求合法 JSON）
- min_len / max_len: int             原始输出字符长度下限/上限（含边界）
- tool: {"name": str, "args": dict}  必须发起该工具调用；args 逐键相等（只比对期望里给出的键）

同一份用例对任何 prompt 版本使用同一套断言（SPEC 技术约束 4）：
打分器不知道「这是哪个版本的回答」，只看输出本身。

零第三方依赖：只用 Python 标准库。Python 3.11 / 3.13 均可运行。
"""
from __future__ import annotations

import json

_ASSERTION_KEYS = {
    "contains_all",
    "contains_any",
    "not_contains",
    "format",
    "json_keys",
    "min_len",
    "max_len",
    "tool",
}


def check_assertions(expect: dict, text: str, tool_call: dict | None) -> list[str]:
    """对单条模型输出打分，返回失败断言的描述列表；空列表 = 通过。"""
    unknown = set(expect) - _ASSERTION_KEYS
    if unknown:
        raise ValueError(f"用例出现未知断言字段: {sorted(unknown)}")
    if not any(key in expect for key in _ASSERTION_KEYS):
        raise ValueError("用例没有任何断言（expect 为空），无法打分")

    failed: list[str] = []

    for sub in expect.get("contains_all", []):
        if sub not in text:
            failed.append(f"缺少关键词: {sub!r}")

    any_list = expect.get("contains_any", [])
    if any_list and not any(sub in text for sub in any_list):
        failed.append(f"缺少任一关键词之一: {any_list}")

    for sub in expect.get("not_contains", []):
        if sub in text:
            failed.append(f"出现了不该出现的内容: {sub!r}")

    need_json = expect.get("format") == "json" or "json_keys" in expect
    parsed: dict | None = None
    if need_json:
        try:
            obj = json.loads(text)
            if not isinstance(obj, dict):
                failed.append("输出不是 JSON 对象")
            else:
                parsed = obj
        except (json.JSONDecodeError, TypeError):
            failed.append("输出不是合法 JSON")
    for key in expect.get("json_keys", []):
        if parsed is not None and key not in parsed:
            failed.append(f"JSON 缺少键: {key!r}")

    min_len = expect.get("min_len")
    max_len = expect.get("max_len")
    if min_len is not None and len(text) < min_len:
        failed.append(f"输出过短: {len(text)} < {min_len}")
    if max_len is not None and len(text) > max_len:
        failed.append(f"输出超长: {len(text)} > {max_len}")

    tool_spec = expect.get("tool")
    if tool_spec is not None:
        if not isinstance(tool_call, dict):
            failed.append("应发起工具调用但没有调用")
        else:
            if tool_call.get("name") != tool_spec.get("name"):
                failed.append(
                    f"工具名不符: 期望 {tool_spec.get('name')!r}，实际 {tool_call.get('name')!r}"
                )
            want_args = tool_spec.get("args", {})
            got_args = tool_call.get("arguments", {})
            for arg_name, want in want_args.items():
                if got_args.get(arg_name) != want:
                    failed.append(
                        f"工具参数 {arg_name} 不符: 期望 {want!r}，实际 {got_args.get(arg_name)!r}"
                    )

    return failed


def score_all(cases: list[dict], results: list[dict]) -> dict:
    """汇总所有用例的打分结果。

    cases: [{"id", "category", "expect", ...}]，results 与之等长对齐：
           [{"text", "tool_call", ...}]。
    返回 {"passed", "total", "rate", "per_case"}，rate 是 0~1 的小数。
    """
    if len(cases) != len(results):
        raise ValueError(f"用例数 {len(cases)} 与结果数 {len(results)} 不一致")
    per_case: list[dict] = []
    passed = 0
    for case, result in zip(cases, results):
        failed = check_assertions(case["expect"], result["text"], result.get("tool_call"))
        ok = not failed
        passed += 1 if ok else 0
        per_case.append({"id": case["id"], "category": case["category"], "passed": ok, "failed": failed})
    total = len(cases)
    return {
        "passed": passed,
        "total": total,
        "rate": passed / total if total else 0.0,
        "per_case": per_case,
    }
