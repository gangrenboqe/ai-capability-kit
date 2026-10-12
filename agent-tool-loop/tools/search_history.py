"""工具：search_history —— 按关键词查本地 SQLite 里的历史会话。

表结构（由 demo.seed_db 生成）：sessions(session_id, role, content, created_at)。
LIKE 特殊字符（% _ \）做转义，搜「100%」不会变成通配。
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from agent_loop import ToolError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "sessions.db"

_LIKE_ESCAPES = str.maketrans({"\\": "\\\\", "%": "\\%", "_": "\\_"})


def search_history(keyword: str, limit: int = 5, db_path: str | Path | None = None) -> dict:
    """搜索历史会话。返回 {"count", "results": [{session_id, role, content, created_at}]}。

    空命中不是错误：返回 count=0、results=[]（空数据分支）。
    """
    if not keyword.strip():
        raise ToolError("keyword 不能为空：请给出要搜索的关键词")
    keyword = keyword.strip()
    if not (1 <= limit <= 50):
        raise ToolError("limit 必须是 1~50 的整数")
    path = Path(db_path or os.environ.get("AGENT_TOOLLOOP_DB") or DEFAULT_DB)
    if not path.is_file():
        raise ToolError(f"数据库不存在: {path}（先运行 python demo.py --seed 生成示例库）")
    escaped = keyword.translate(_LIKE_ESCAPES)
    try:
        conn = sqlite3.connect(path)
        try:
            rows = conn.execute(
                "SELECT session_id, role, content, created_at FROM sessions "
                "WHERE content LIKE ? ESCAPE '\\' ORDER BY created_at, rowid LIMIT ?",
                (f"%{escaped}%", limit),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise ToolError(f"查询数据库失败: {exc}") from exc
    results = [
        {"session_id": row[0], "role": row[1], "content": row[2][:120], "created_at": row[3]}
        for row in rows
    ]
    return {"count": len(results), "results": results}
