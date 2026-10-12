"""工具：read_note —— 读取白名单目录下的文本文件（拦截路径越界）。

安全边界：
- 只能读 root（默认项目 notes/ 目录，可用环境变量 READ_NOTE_ROOT 覆盖）下的相对路径
- 绝对路径、包含 .. 的上跳、解析后逃出 root 的路径 → 一律明确报错
- root 由程序侧绑定，**不作为模型可设的参数**
"""
from __future__ import annotations

import os
from pathlib import Path

from agent_loop import ToolError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = PROJECT_ROOT / "notes"
_MAX_BYTES = 64 * 1024


def read_note(name: str, root: Path | None = None) -> dict:
    """读文件。返回 {"name", "content", "chars", "lines"}。越权/不存在 → ToolError。"""
    if not name.strip():
        raise ToolError("name 不能为空：请给出 notes 目录下的文件名，如 todo.txt")
    name = name.strip()
    base = Path(root or os.environ.get("READ_NOTE_ROOT") or DEFAULT_ROOT).resolve()
    candidate = Path(name)
    if candidate.is_absolute() or candidate.drive or name.startswith(("/", "\\")):
        raise ToolError(f"拒绝绝对路径: {name}（只能读 notes 目录下的相对路径）")
    if ".." in candidate.parts:
        raise ToolError(f"路径越界: {name}（不允许 .. 上跳）")
    target = (base / candidate).resolve()
    if not target.is_relative_to(base):
        raise ToolError(f"路径越界: {name}（只能读取 {base} 目录下的文件）")
    if not target.exists():
        raise ToolError(f"文件不存在: {name}")
    if target.is_dir():
        raise ToolError(f"{name} 是目录，不是文件")
    if target.stat().st_size > _MAX_BYTES:
        raise ToolError(f"文件过大（> 64KB）: {name}")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError(f"文件不是 UTF-8 文本: {name}") from exc
    return {
        "name": name,
        "content": content,
        "chars": len(content),
        "lines": len(content.splitlines()),
    }
