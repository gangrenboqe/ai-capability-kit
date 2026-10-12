"""建索引：FTS5 表 + 自己的中文分词写入。

🔴 幂等（验收标准 4）：以 sha256(content) 为准——内容没变 → skipped；
变了 → 更新并重建该文档的 FTS 行；新增 → 插入。重复执行不产生脏数据、不重复插入，
第二次 build_index 的 inserted 必须是 0（测试守着）。

FTS 表结构：fts_index(seg, doc_id UNINDEXED)，seg 存放空格分隔的 bigram 词元；
原文存 docs 表，检索时 JOIN 回来展示。
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from tokenizer import bigram_tokenize


@dataclass
class Doc:
    doc_id: str
    source: str
    content: str


def init_schema(conn: sqlite3.Connection) -> None:
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS docs ("
            "doc_id TEXT PRIMARY KEY, source TEXT, content TEXT, content_hash TEXT)"
        )
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS fts_index USING fts5(seg, doc_id UNINDEXED)"
        )
    except sqlite3.OperationalError as exc:
        raise RuntimeError(f"当前 SQLite 不支持 FTS5，无法建索引: {exc}") from exc


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_index(db_path: str | Path, docs: list[Doc]) -> dict:
    """把文档列表建进索引。返回 {"inserted", "updated", "skipped", "empty", "total"}。"""
    conn = sqlite3.connect(db_path)
    try:
        init_schema(conn)
        stats = {"inserted": 0, "updated": 0, "skipped": 0, "empty": 0, "total": 0}
        for doc in docs:
            stats["total"] += 1
            content = doc.content or ""
            digest = _content_hash(content)
            row = conn.execute(
                "SELECT content_hash FROM docs WHERE doc_id = ?", (doc.doc_id,)
            ).fetchone()
            if row is not None and row[0] == digest:
                stats["skipped"] += 1
                continue
            if row is None:
                conn.execute(
                    "INSERT INTO docs (doc_id, source, content, content_hash) VALUES (?, ?, ?, ?)",
                    (doc.doc_id, doc.source, content, digest),
                )
                stats["inserted"] += 1
            else:
                conn.execute(
                    "UPDATE docs SET source = ?, content = ?, content_hash = ? WHERE doc_id = ?",
                    (doc.source, content, digest, doc.doc_id),
                )
                conn.execute("DELETE FROM fts_index WHERE doc_id = ?", (doc.doc_id,))
                stats["updated"] += 1
            if content.strip():
                seg = " ".join(bigram_tokenize(content))
                conn.execute(
                    "INSERT INTO fts_index (seg, doc_id) VALUES (?, ?)", (seg, doc.doc_id)
                )
            else:
                stats["empty"] += 1
        conn.commit()
        return stats
    finally:
        conn.close()


def load_docs_from_dir(corpus_dir: str | Path) -> list[Doc]:
    """从目录读 .txt/.md 文档。doc_id = 文件名（去扩展名），source = 文件名。"""
    directory = Path(corpus_dir)
    if not directory.is_dir():
        raise NotADirectoryError(f"语料目录不存在: {directory}")
    docs: list[Doc] = []
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in (".txt", ".md") or not path.is_file():
            continue
        docs.append(
            Doc(
                doc_id=path.stem,
                source=path.name,
                content=path.read_text(encoding="utf-8"),
            )
        )
    return docs
