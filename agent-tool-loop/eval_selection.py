"""选对工具正确率评测：20 条固定用例跑完整循环，输出「选对 x/20」。

用例集：eval_cases.json（search_history 7 / calc 5 / read_note 6 / 无需工具 2）。
每条判定三件事：
  1. 首个工具调用 = 期望工具（无需工具的用例 = 全程不调工具）
  2. 关键参数与期望一致
  3. 最终回答包含期望关键词（工具报错类用例 = 包含报错信息，验证错误回填）

用法：
  python eval_selection.py                       # 离线（默认），与 out/eval_selection_baseline.json 比对
  python eval_selection.py --update-baseline     # 显式把本次成绩写为新基线（改基线的唯一方式）
  PAI_EVAL_BACKEND=live python eval_selection.py # 真实模型（花真金白银；基线 = out/baseline_live.json）
  PAI_EVAL_QUICK=5 python eval_selection.py      # live 省钱档：只跑前 5 条

🔴 口径：真模型的正确率可能低于离线模拟（离线本来就是「按预期选」）。
   那是真结果不是 bug——它告诉你真模型在哪儿会出错。不许改用例/判据/挑用例。

退出码：0 = 持平或好于基线；1 = 差于基线；2 = 环境错误。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_loop import OpenAICompatBackend, ScriptedBackend, run_loop  # noqa: E402
from demo import seed_db  # noqa: E402
from tools import build_registry  # noqa: E402

OFFLINE_BASELINE = PROJECT_ROOT / "baseline_offline.json"   # 在项目根，可提交（out/ 被 gitignore）
LIVE_BASELINE = PROJECT_ROOT / "baseline_live.json"


def make_backend():
    mode = (os.environ.get("PAI_EVAL_BACKEND") or "offline").strip().lower()
    if mode == "live":
        return OpenAICompatBackend(), "OpenAICompatBackend（真实模型，函数调用）"
    return ScriptedBackend(), "ScriptedBackend（离线确定性规则，非真实 LLM）"


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
    quick = os.environ.get("PAI_EVAL_QUICK")
    if quick:
        cases = cases[: max(1, int(quick))]
    rows: list[dict] = []
    passed = 0
    backend, _ = make_backend()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "sessions.db"
        seed_db(db_path)
        registry = build_registry(db_path=db_path)
        for case in cases:
            result = run_loop(backend, registry, case["input"])
            ok, reasons = judge(case, result)
            passed += int(ok)
            rows.append({"id": case["id"], "input": case["input"], "ok": ok, "reasons": reasons})
    return passed, len(cases), rows


def render_report(passed: int, total: int, rows: list[dict]) -> str:
    _, desc = make_backend()
    lines = [
        "# 选对工具正确率评测报告",
        "",
        f"- 时间：{date.today().isoformat()}",
        f"- 后端：{desc}",
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


def load_baseline(path: Path) -> dict | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("passed", "total"):
        if not isinstance(data.get(key), int):
            raise ValueError(f"基线文件缺少整数字段 {key}: {path}")
    return data


def write_baseline(path: Path, passed: int, total: int) -> None:
    _, desc = make_backend()
    payload = {"passed": passed, "total": total, "backend": desc,
               "updated": date.today().isoformat(),
               "note": "只能用 --update-baseline 显式更新；回归检查绝不写此文件"}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="选对工具正确率评测（离线/真实模型）")
    parser.add_argument("--update-baseline", action="store_true",
                        help="把本次成绩写为新基线（改基线的唯一方式）")
    parser.add_argument("--no-baseline", action="store_true", help="只跑报告，不比对基线")
    args = parser.parse_args()

    mode = (os.environ.get("PAI_EVAL_BACKEND") or "offline").strip().lower()
    baseline_path = LIVE_BASELINE if mode == "live" else OFFLINE_BASELINE
    passed, total, rows = run_eval()
    report = render_report(passed, total, rows)
    out_dir = PROJECT_ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    suffix = "_live" if mode == "live" else ""
    out_path = out_dir / f"eval_selection{suffix}.md"
    out_path.write_text(report, encoding="utf-8")

    code = 0
    if args.update_baseline:
        write_baseline(baseline_path, passed, total)
        print(f"基线已更新: {baseline_path}（{passed}/{total}）")
    elif not args.no_baseline:
        baseline = load_baseline(baseline_path)
        if baseline is None:
            print(f"⚠ 基线不存在（{baseline_path}）。"
                  f"首次建立：python eval_selection.py --update-baseline")
            code = 2
        else:
            if passed < baseline["passed"]:
                regressed = [f"{r['id']}（{'；'.join(r['reasons'])}）" for r in rows if not r["ok"]]
                print(f"差于基线 ❌ 本次 {passed}/{total} < 基线 {baseline['passed']}/{baseline['total']}"
                      f"；回退用例：{'；'.join(regressed)}")
                code = 1
            elif passed > baseline["passed"]:
                print(f"好于基线 📈 本次 {passed}/{total} > 基线 {baseline['passed']}/{baseline['total']}；"
                      f"确认稳定后用 --update-baseline 显式更新")
            else:
                print(f"与基线持平 ✅ {passed}/{total}")

    print(report, end="")
    print(f"报告已写入 {out_path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
