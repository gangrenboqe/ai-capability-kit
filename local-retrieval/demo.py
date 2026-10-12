"""一条命令演示：建索引（连跑两次验证幂等）→ 20 条查询召回 + 耗时。

用法：python demo.py
输出：控制台摘要 + out/eval_report.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from indexer import build_index, load_docs_from_dir  # noqa: E402
from search import search  # noqa: E402


def main() -> int:
    db_path = PROJECT_ROOT / "data" / "retrieval.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()  # 演示从干净库开始；幂等验证靠进程内连跑两次 build_index

    docs = load_docs_from_dir(PROJECT_ROOT / "data" / "sample_docs")
    stats1 = build_index(db_path, docs)
    stats2 = build_index(db_path, docs)  # 第二次：应当 inserted=0, skipped=全部

    doc_meta = json.loads((PROJECT_ROOT / "data" / "eval_queries.json").read_text(encoding="utf-8"))
    queries = doc_meta["queries"]

    rows = []
    recall_top1 = 0
    recall_top3 = 0
    total_ms = 0.0
    max_ms = 0.0
    for q in queries:
        res = search(db_path, q["query"], top_k=3)
        top_ids = [h["doc_id"] for h in res["hits"]]
        hit1 = bool(top_ids) and top_ids[0] == q["expect_doc_id"]
        hit3 = q["expect_doc_id"] in top_ids
        recall_top1 += int(hit1)
        recall_top3 += int(hit3)
        total_ms += res["elapsed_ms"]
        max_ms = max(max_ms, res["elapsed_ms"])
        rows.append(
            {
                "id": q["id"],
                "query": q["query"],
                "expect": q["expect_doc_id"],
                "top3": top_ids,
                "hit1": hit1,
                "hit3": hit3,
                "ms": res["elapsed_ms"],
            }
        )

    n = len(queries)
    lines = [
        "# 本地检索 · 评测报告",
        "",
        f"- 语料：{stats1['total']} 篇（合成示例，无隐私）　索引库：data/retrieval.db",
        f"- 建索引第一次：inserted={stats1['inserted']} updated={stats1['updated']} empty={stats1['empty']}",
        f"- 建索引第二次（幂等验证）：inserted=**{stats2['inserted']}** skipped={stats2['skipped']}（应为 0/{stats1['total']}）",
        f"- 召回（期望文档在 Top3）：**{recall_top3}/{n}**　Top1 命中：{recall_top1}/{n}",
        f"- 单次查询耗时：平均 {total_ms / n:.2f} ms　最大 {max_ms:.2f} ms（实测，非估计）",
        "",
        "| 查询 | 期望文档 | Top3 实际 | Top1 | Top3 | 耗时 ms |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['id']} {row['query']} | {row['expect']} | {' > '.join(row['top3']) or '（无命中）'} "
            f"| {'✔' if row['hit1'] else '✘'} | {'✔' if row['hit3'] else '✘'} | {row['ms']:.2f} |"
        )
    report = "\n".join(lines) + "\n"

    out_dir = PROJECT_ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "eval_report.md").write_text(report, encoding="utf-8")
    print("\n".join(lines[:6]))
    print(f"完整报告已写入 {out_dir / 'eval_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
