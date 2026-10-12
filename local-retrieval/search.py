"""检索接口：返回命中内容 + 得分 + 来源位置。

查询侧同样走 bigram 分词：
- 普通词元 → 带引号的短语（引号由我们拼，用户输入里的特殊字符已被分词器丢弃，
  所以 `" OR 1=1 --` 这类注入写法是安全的，测试守着）
- 单个汉字 → 前缀查询 `测*`，让单字查询也能命中 bigram 词
- 多个词元之间用 OR 连接，排序交给 FTS5 的 bm25（命中越多的文档排越前）

得分口径：FTS5 bm25 值取负后作为 score，**越大越相关**；Top1 = 最相关。
来源位置 = doc_id + 来源文件名 + 命中片段（[] 标出）+ 原文字符偏移。
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from tokenizer import _is_cjk, bigram_tokenize


def build_match_query(query: str) -> str:
    tokens = bigram_tokenize(query)
    parts = []
    for token in tokens:
        if len(token) == 1 and _is_cjk(token):
            parts.append(f'"{token}"*')
        else:
            parts.append(f'"{token}"')
    return " OR ".join(parts)


def search(db_path: str | Path, query: str, top_k: int = 5) -> dict:
    """检索。返回 {"query", "hits": [{doc_id, source, score, fragment, offset}], "elapsed_ms"}。

    空查询 / 纯标点查询 / 无命中 → hits=[]（不是错误）。
    """
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1 or top_k > 50:
        raise ValueError("top_k 必须是 1~50 的整数")
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"索引库不存在: {path}（先运行 python demo.py 建索引）")
    started = time.perf_counter()
    tokens = bigram_tokenize(query)
    hits: list[dict] = []
    if tokens:
        match = build_match_query(query)
        conn = sqlite3.connect(path)
        try:
            rows = conn.execute(
                "SELECT f.doc_id, d.source, d.content, bm25(fts_index) AS rank_score, "
                "snippet(fts_index, 0, '[', ']', '…', 12) AS frag "
                "FROM fts_index f JOIN docs d ON d.doc_id = f.doc_id "
                "WHERE fts_index MATCH ? ORDER BY rank_score, d.doc_id LIMIT ?",
                (match, top_k),
            ).fetchall()
        finally:
            conn.close()
        for doc_id, source, content, rank_score, frag in rows:
            offset = -1
            for token in tokens:
                found = content.find(token)
                if found >= 0 and (offset < 0 or found < offset):
                    offset = found
            hits.append(
                {
                    "doc_id": doc_id,
                    "source": source,
                    "score": round(-rank_score, 4),
                    "fragment": frag,
                    "offset": offset,
                }
            )
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {"query": query, "hits": hits, "elapsed_ms": elapsed_ms}
