"""演示：一条命令跑通「模型 → 工具 → 结果回填 → 最终回答」的完整调用链。

用法：
  python demo.py            # 自动建库（若无）+ 跑一次双工具演示，调用链写入 out/run_latest.md
  python demo.py --seed     # 只重建示例会话库 data/sessions.db（整库重建，重复执行状态一致）
  python demo.py --question "自定义问题"

数据全部为合成示例（无任何真实隐私）。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_loop import ScriptedBackend, run_loop  # noqa: E402
from tools import build_registry  # noqa: E402

DEFAULT_QUESTION = "帮我搜索历史会话里关于「二元分词」的讨论，然后算一下命中条数乘以 3 等于多少"


def seed_db(db_path: Path, source: Path | None = None) -> dict:
    """把示例会话写入 SQLite。整库重建：重复执行后库内容完全一致（幂等）。"""
    source = source or PROJECT_ROOT / "data" / "sample_sessions.json"
    rows = json.loads(source.read_text(encoding="utf-8"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS sessions")
        conn.execute(
            "CREATE TABLE sessions (session_id TEXT, role TEXT, content TEXT, created_at TEXT)"
        )
        conn.executemany(
            "INSERT INTO sessions VALUES (?, ?, ?, ?)",
            [(r["session_id"], r["role"], r["content"], r["created_at"]) for r in rows],
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    finally:
        conn.close()
    return {"rows": count, "db": str(db_path)}


def render_trace_md(question: str, result: dict, elapsed_ms: float) -> str:
    lines = [
        "# Agent 工具调用循环 · 演示运行记录",
        "",
        f"- 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        "- 后端：ScriptedBackend（离线确定性规则，非真实 LLM）",
        f"- 轮次：{result['round_count']}　耗时：{elapsed_ms:.1f} ms　数据：合成示例，无隐私",
        "",
        f"**用户问题**：{question}",
        "",
    ]
    for r in result["rounds"]:
        lines.append(f"## 第 {r['round']} 轮")
        if r["model_content"]:
            lines.append(f"- 模型说：{r['model_content']}")
        for call in r["tool_calls"]:
            args = json.dumps(call["arguments"], ensure_ascii=False)
            lines.append(f"- 要调工具：{call['name']}　参数：{args}")
        for res in r["tool_results"]:
            if res["ok"]:
                preview = json.dumps(res["result"], ensure_ascii=False)[:200]
                lines.append(f"- 执行 {res['name']} → ok：{preview}")
            else:
                lines.append(f"- 执行 {res['name']} → 报错：{res['error']}")
        lines.append("")
    lines.append("## 最终回答")
    lines.append("")
    lines.append(result["answer"])
    if result.get("stopped"):
        lines.append("")
        lines.append(f"（stopped: {result['stopped']}，未得到最终回答）")
    return "\n".join(lines) + "\n"


def db_ready(db_path: Path) -> bool:
    """库文件存在且 sessions 表可查才算就绪（防止残留的空库文件骗过检查）。"""
    if not db_path.is_file():
        return False
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='sessions'"
            ).fetchone()
        finally:
            conn.close()
        return bool(row and row[0])
    except sqlite3.Error:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent 工具调用循环演示")
    parser.add_argument("--seed", action="store_true", help="只重建示例会话库")
    parser.add_argument("--question", default=DEFAULT_QUESTION, help="自定义问题")
    args = parser.parse_args(argv)

    db_path = PROJECT_ROOT / "data" / "sessions.db"
    if args.seed or not db_ready(db_path):
        stats = seed_db(db_path)
        print(f"已生成示例会话库：{stats['rows']} 条记录 → {stats['db']}")
        if args.seed:
            return 0

    registry = build_registry(db_path=db_path)
    backend = ScriptedBackend()
    start = time.perf_counter()
    result = run_loop(backend, registry, args.question)
    elapsed_ms = (time.perf_counter() - start) * 1000

    report = render_trace_md(args.question, result, elapsed_ms)
    out_dir = PROJECT_ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "run_latest.md"
    out_path.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"调用链已写入 {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
