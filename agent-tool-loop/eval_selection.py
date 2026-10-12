"""选对工具正确率评测：20 条固定用例跑完整循环，输出「选对 x/20」。

用例集：eval_cases.json（search_history 7 / calc 5 / read_note 6 / 无需工具 2）。
每条判定三件事：
  1. 首个工具调用 = 期望工具（无需工具的用例 = 全程不调工具）
  2. 关键参数与期望一致
  3. 最终回答包含期望关键词（工具报错类用例 = 包含报错信息，验证错误回填）

用法：python eval_selection.py
后端：ScriptedBackend（离线确定性规则）。真实 LLM 后端见 agent_loop.OpenAICompatBackend，
本机无密钥未实测——这个区别在 README 有明确说明。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_loop import ScriptedBackend, run_loop  # noqa: E402
from demo import seed_db  # noqa: E402
from tools import build_registry  # noqa: E402


def judge(case: dict, result: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    calls = [c for r in result["rounds"] for c in r["tool_calls"]]
    expect_tool = case.get("expect_tool")
    if expect_tool is None:
        if calls:
            reasons.append(f"不应调用工具，却调用了 {[c['name'] for c in calls]}")
    else:
        if not calls:
            reasons.append("期望调用工具，但没有调用")
        elif calls[0]["name"] != expect_tool:
            reasons.append(f"首个工具 {calls[0]['name']} != 期望 {expect_tool}")
        else:
            for key, value in (case.get("expect_args") or {}).items():
                actual = calls[0]["arguments"].get(key)
                if actual != value:
                    reasons.append(f"参数 {key}={actual!r} != 期望 {value!r}")
    for keyword in case.get("expect_answer_contains") or []:
        if keyword not in result["answer"]:
            reasons.append(f"回答缺少关键词: {keyword}")
    return (not reasons), reasons


def run_eval(case_file: Path | None = None) -> tuple[int, int, list[dict]]:
    case_file = case_file or PROJECT_ROOT / "eval_cases.json"
    doc = json.loads(case_file.read_text(encoding="utf-8"))
    cases = doc["cases"]
    rows: list[dict] = []
    passed = 0
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "sessions.db"
        seed_db(db_path)
        registry = build_registry(db_path=db_path)
        backend = ScriptedBackend()
        for case in cases:
            result = run_loop(backend, registry, case["input"])
            ok, reasons = judge(case, result)
            passed += int(ok)
            rows.append({"id": case["id"], "input": case["input"], "ok": ok, "reasons": reasons})
    return passed, len(cases), rows


def render_report(passed: int, total: int, rows: list[dict]) -> str:
    lines = [
        "# 选对工具正确率评测报告",
        "",
        "- 后端：ScriptedBackend（离线确定性规则，非真实 LLM）",
        f"- 结果：**选对 {passed}/{total}**",
        "",
        "| 用例 | 输入 | 结果 | 失败原因 |",
        "|---|---|---|---|",
    ]
    for row in rows:
        mark = "PASS" if row["ok"] else "FAIL"
        reason = "；".join(row["reasons"]) or "-"
        lines.append(f"| {row['id']} | {row['input'][:30]} | {mark} | {reason} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    passed, total, rows = run_eval()
    report = render_report(passed, total, rows)
    out_dir = PROJECT_ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "eval_selection.md"
    out_path.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"报告已写入 {out_path}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
