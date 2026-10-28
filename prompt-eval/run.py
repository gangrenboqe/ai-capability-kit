"""一条命令跑完 25 条用例，输出通过率（SPEC 交付物 4）。

用法：
  python run.py                          # 默认用 prompts/v3.md 评测
  python run.py --prompt prompts/v1.md   # 评测指定版本
  python run.py --compare                # prompts/ 下所有版本各跑一遍，出对比表

输出同时打印到终端并写入 out/（单版本 → out/eval_<版本名>.md，
对比 → out/compare.md）。打分全部走 scorer.check_assertions，无主观判据。

零第三方依赖：只用 Python 标准库。Python 3.11 / 3.13 均可运行。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from backend import OfflineSimModel, OpenAICompatModel
from scorer import score_all

ROOT = Path(__file__).resolve().parent
DEFAULT_PROMPT = ROOT / "prompts" / "v3.md"
CASES_PATH = ROOT / "cases" / "cases.json"
OUT_DIR = ROOT / "out"

_CATEGORY_NAMES = {"normal": "正常", "boundary": "边界", "exception": "异常", "adversarial": "对抗"}


def make_backend():
    """按环境变量 PAI_EVAL_BACKEND 选后端：offline（默认，保回归确定性）| live（真实模型）。

    live 需要 AGENT_API_KEY / AGENT_BASE_URL / AGENT_MODEL（密钥只走环境变量，不落盘）。
    """
    mode = (os.environ.get("PAI_EVAL_BACKEND") or "offline").strip().lower()
    if mode == "live":
        model = OpenAICompatModel()
        return model, f"OpenAICompatModel（真实模型 {model.model} @ {model.base_url}）"
    return OfflineSimModel(), "OfflineSimModel（离线确定性模拟，非真实 LLM）"


def load_cases(path: Path) -> list[dict]:
    """读用例集。文件缺失 / 不是 JSON / 没有用例 → 明确报错。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases", data) if isinstance(data, dict) else data
    if not cases:
        raise ValueError(f"用例集为空: {path}")
    return cases


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def evaluate(system: str, cases: list[dict], backend: object) -> dict:
    """对一份系统提示跑完所有用例，返回 score_all 的汇总。"""
    results = [backend.chat(system, case["input"]) for case in cases]
    return score_all(cases, results)


def render_report(prompt_name: str, summary: dict, cases: list[dict], backend_desc: str) -> str:
    lines = [
        f"# Prompt 评测报告 · {prompt_name}",
        "",
        f"- 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 后端：{backend_desc}",
        f"- 用例：{summary['total']} 条（"
        + " / ".join(
            f"{name} {sum(1 for c in cases if c['category'] == cat)}"
            for cat, name in _CATEGORY_NAMES.items()
        )
        + "）",
        f"- 通过率：**{summary['passed']}/{summary['total']} = {summary['rate']:.0%}**",
        "",
        "| 用例 | 类别 | 结果 | 失败断言 |",
        "|---|---|---|---|",
    ]
    for case, pc in zip(cases, summary["per_case"]):
        mark = "✔" if pc["passed"] else "✗"
        detail = "；".join(pc["failed"]) if pc["failed"] else ""
        lines.append(f"| {case['id']} | {_CATEGORY_NAMES[case['category']]} | {mark} | {detail} |")
    lines.append("")
    return "\n".join(lines)


def render_compare(all_summaries: dict[str, dict]) -> str:
    lines = [
        "# Prompt 版本对比",
        "",
        f"- 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 后端：{os.environ.get('_PAI_BACKEND_DESC', 'OfflineSimModel（离线确定性模拟，非真实 LLM）')}",
        "- 演进顺序为 v1 → v2 → v3_draft → v3（表格按名称排序，v3_draft 是实测变差后被回退的草稿）",
        "",
        "| 版本 | 通过 | 总数 | 通过率 |",
        "|---|---|---|---|",
    ]
    for name, summary in all_summaries.items():
        lines.append(f"| {name} | {summary['passed']} | {summary['total']} | {summary['rate']:.0%} |")
    lines += ["", "## 逐用例通过矩阵", "", "| 用例 | " + " | ".join(all_summaries) + " |", "|---" * (len(all_summaries) + 1) + "|"]
    ids = [pc["id"] for pc in next(iter(all_summaries.values()))["per_case"]]
    for i, case_id in enumerate(ids):
        marks = [
            "✔" if summary["per_case"][i]["passed"] else "✗"
            for summary in all_summaries.values()
        ]
        lines.append(f"| {case_id} | " + " | ".join(marks) + " |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prompt 评测：跑完用例，输出通过率")
    parser.add_argument("--prompt", type=str, default=None, help="要评测的 prompt 文件（默认 prompts/v3.md）")
    parser.add_argument("--compare", action="store_true", help="prompts/ 下所有版本各跑一遍，出对比表")
    parser.add_argument("--quick", type=int, default=None,
                        help="只跑前 N 条（live 省钱档； offline 回归不用）")
    args = parser.parse_args(argv)

    cases = load_cases(CASES_PATH)
    if args.quick:
        cases = cases[: args.quick]
    OUT_DIR.mkdir(exist_ok=True)
    backend, backend_desc = make_backend()
    os.environ["_PAI_BACKEND_DESC"] = backend_desc

    if args.compare:
        prompt_paths = sorted((ROOT / "prompts").glob("*.md"))
        if not prompt_paths:
            raise ValueError("prompts/ 目录下没有任何 prompt 文件")
        all_summaries: dict[str, dict] = {}
        for path in prompt_paths:
            system = load_prompt(path)
            all_summaries[path.stem] = evaluate(system, cases, backend)
        report = render_compare(all_summaries)
        out_path = OUT_DIR / "compare.md"
    else:
        prompt_path = Path(args.prompt) if args.prompt else DEFAULT_PROMPT
        system = load_prompt(prompt_path)
        summary = evaluate(system, cases, backend)
        report = render_report(prompt_path.stem, summary, cases, backend_desc)
        out_path = OUT_DIR / f"eval_{prompt_path.stem}.md"

    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"报告已写入: {out_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, FileNotFoundError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(2)
