"""工具装配：把三个真实工具注册进 ToolRegistry。

工具与模块一一对应（SPEC：每个工具一个文件）：
- search_history  → tools/search_history.py  查本地 SQLite 历史会话
- calc            → tools/calc.py            安全算术求值（AST 白名单）
- read_note       → tools/read_note.py       读 notes 目录下的文本文件（拦路径越界）

db_path / notes_root 只在这里绑定（程序侧传入），**不作为模型可设的参数**——
否则模型把 root 改成 C:\ 就是越权。这是安全边界，不是疏漏。
"""
from __future__ import annotations

from pathlib import Path

from agent_loop import Tool, ToolRegistry
from tools.calc import calculate
from tools.read_note import read_note
from tools.search_history import search_history

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_registry(db_path: Path | None = None, notes_root: Path | None = None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="search_history",
            description="按关键词在本地 SQLite 的历史会话里搜索，返回会话ID、角色、内容片段、时间",
            parameters={
                "keyword": {"type": "string", "required": True, "description": "要搜索的关键词，不能为空"},
                "limit": {"type": "integer", "required": False, "description": "最多返回条数，1~50，默认 5"},
            },
            func=lambda keyword, limit=5: search_history(keyword, limit=limit, db_path=db_path),
        )
    )
    registry.register(
        Tool(
            name="calc",
            description="计算一个算术表达式，只支持数字、括号和 + - * / // % **",
            parameters={
                "expression": {"type": "string", "required": True, "description": "算术表达式，如 3*(4+5)"}
            },
            func=calculate,
        )
    )
    registry.register(
        Tool(
            name="read_note",
            description="读取 notes 目录下的一个文本笔记，拒绝绝对路径和路径越界",
            parameters={
                "name": {"type": "string", "required": True, "description": "笔记文件名（相对 notes 目录，如 todo.txt）"}
            },
            func=lambda name: read_note(name, root=notes_root),
        )
    )
    return registry
