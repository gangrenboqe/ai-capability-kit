"""v4 自动回归入口：跑当前正式版提示词，与基线比对，输出「好 / 持平 / 差」。

用法：
  python regression.py                    # 跑 prompts/v3.md 全部用例，与 baseline.json 比对
  python regression.py --update-baseline  # 显式把本次成绩写为新基线（改基线的唯一方式）

退出码：
  0 = 持平或好于基线
  1 = 差于基线（CI 门禁靠它变红）
  2 = 基线缺失 / 环境错误

🔴 门禁设计（成败关键）：本脚本在比对时**绝不写基线文件**——
基线只能通过 --update-baseline 显式更新。否则每次跑完自动把基线抬上去，
「差于基线就变红」的门禁就失效了。

零第三方依赖：只用 Python 标准库。Python 3.11 / 3.13 均可运行。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from backend import OfflineSimModel
from run import CASES_PATH, DEFAULT_PROMPT, evaluate, load_cases, load_prompt

ROOT = Path(__file__).resolve().parent
DEFAULT_BASELINE = ROOT / "baseline.json"
BACKEND_DESC = "OfflineSimModel（离线确定性模拟，非真实 LLM）"


def compare(current: int, baseline: int) -> str:
    """纯函数：本次通过数 vs 基线通过数 → "better" / "same" / "worse"。"""
    if current > baseline:
        return "better"
    if current == baseline:
        return "same"
    return "worse"


def load_baseline(path: Path) -> dict:
    """读基线。缺失 / 不是 JSON / 缺关键字段 → 明确报错，绝不静默新建。"""
    if not path.exists():
        raise FileNotFoundError(
            f"基线文件不存在: {path}\n"
            "基线只能用 `python regression.py --update-baseline` 显式建立，"
            "回归检查不会自动创建（防止基线被悄悄抬走）。"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("passed", "total"):
        if not isinstance(data.get(key), int):
            raise ValueError(f"基线文件缺少整数字段 {key}: {path}")
    return data


def write_baseline(path: Path, summary: dict) -> None:
    """显式更新基线。只有 --update-baseline 会走到这里。"""
    payload = {
        "passed": summary["passed"],
        "total": summary["total"],
        "backend": BACKEND_DESC,
        "updated": date.today().isoformat(),
        "note": "只能用 python regression.py --update-baseline 显式更新；回归检查绝不写此文件",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_current() -> dict:
    """跑当前正式版（prompts/v3.md）全部用例，返回汇总。"""
    cases = load_cases(CASES_PATH)
    system = load_prompt(DEFAULT_PROMPT)
    return evaluate(system, cases, OfflineSimModel())


def render_verdict(current: dict, baseline: dict, cases: list[dict]) -> tuple[str, str]:
    """返回 (结论文本, 退出码)。差于基线时列出回退用例。"""
    current_n, baseline_n = current["passed"], baseline["passed"]
    verdict = compare(current_n, baseline_n)
    head = (
        f"本次成绩：{current_n}/{current['total']}\n"
        f"基线成绩：{baseline_n}/{baseline.get('total', '?')}（{baseline.get('updated', '未知日期')} 更新）\n"
    )
    if verdict == "same":
        return head + "与基线比对：**持平** ✅", "0"
    if verdict == "better":
        return (
            head
            + "与基线比对：**好于基线** 📈\n"
            + "注意：基线不会自动上涨。确认这次提升稳定后，用 "
            "`python regression.py --update-baseline` 显式更新基线。"
        ), "0"
    # worse：找出回退用例，给出可行动的信息
    regressed = [
        f"{pc['id']}（{'；'.join(pc['failed'])}）"
        for pc in current["per_case"]
        if not pc["passed"]
    ]
    detail = "；".join(regressed) if regressed else "（无逐用例明细）"
    return (
        head
        + f"与基线比对：**差于基线** ❌（少通过 {baseline_n - current_n} 条）\n"
        + f"未通过的用例：{detail}\n"
        + "处理：先弄清变差的原因（提示词改动？用例改动？），修回来，"
        "或经人工确认后用 --update-baseline 接受新基线。"
    ), "1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="prompt-eval 自动回归：与基线比对，差于基线则退出码 1")
    parser.add_argument("--update-baseline", action="store_true",
                        help="把本次成绩写为新基线（改基线的唯一方式）")
    parser.add_argument("--baseline", type=str, default=None,
                        help="基线文件路径（默认项目根 baseline.json；测试用）")
    args = parser.parse_args(argv)

    try:
        baseline_path = Path(args.baseline) if args.baseline else DEFAULT_BASELINE
        current = run_current()

        if args.update_baseline:
            write_baseline(baseline_path, current)
            print(
                f"基线已更新: {baseline_path}\n"
                f"新基线：{current['passed']}/{current['total']}（{date.today().isoformat()}）"
            )
            return 0

        baseline = load_baseline(baseline_path)
        text, code = render_verdict(current, baseline, load_cases(CASES_PATH))
        print(text)
        return int(code)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
