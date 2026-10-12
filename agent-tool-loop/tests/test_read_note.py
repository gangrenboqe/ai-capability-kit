"""read_note 工具测试：正常 / 异常（含越权路径）/ 空数据。"""
import tempfile
import unittest
from pathlib import Path

from agent_loop import ToolError
from tools.read_note import read_note

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ReadNoteNormalTest(unittest.TestCase):
    def test_read_project_note(self):
        out = read_note("todo.txt")
        self.assertEqual(out["name"], "todo.txt")
        self.assertGreater(out["chars"], 0)
        self.assertGreaterEqual(out["lines"], 1)

    def test_read_subdir_name(self):
        out = read_note("todo.txt", root=PROJECT_ROOT / "notes")
        self.assertIn("二元分词", out["content"])

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "empty.txt").write_text("", encoding="utf-8")
            out = read_note("empty.txt", root=root)
            self.assertEqual(out["chars"], 0)
            self.assertEqual(out["lines"], 0)


class ReadNoteErrorTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "ok.txt").write_text("内容", encoding="utf-8")
        secret = Path(self._tmp.name).parent / "secret_outside.txt"
        secret.write_text("机密", encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def test_parent_traversal_rejected(self):
        with self.assertRaises(ToolError) as ctx:
            read_note("../secret_outside.txt", root=self.root)
        self.assertIn("越界", str(ctx.exception))

    def test_absolute_path_rejected(self):
        with self.assertRaises(ToolError) as ctx:
            read_note(str(Path(self.root) / "ok.txt"), root=self.root)
        self.assertIn("绝对路径", str(ctx.exception))

    def test_nested_traversal_rejected(self):
        with self.assertRaises(ToolError) as ctx:
            read_note("a/b/../../../x.txt", root=self.root)
        self.assertIn("越界", str(ctx.exception))

    def test_missing_file(self):
        with self.assertRaises(ToolError) as ctx:
            read_note("missing.txt", root=self.root)
        self.assertIn("文件不存在", str(ctx.exception))

    def test_directory_as_name(self):
        with self.assertRaises(ToolError) as ctx:
            read_note(".", root=self.root)
        self.assertIn("目录", str(ctx.exception))

    def test_non_utf8_rejected(self):
        target = self.root / "bad.txt"
        target.write_bytes(b"\xff\xfe\x00bad")
        with self.assertRaises(ToolError) as ctx:
            read_note("bad.txt", root=self.root)
        self.assertIn("UTF-8", str(ctx.exception))

    def test_file_too_large(self):
        target = self.root / "big.txt"
        target.write_text("字" * (64 * 1024 + 1), encoding="utf-8")
        with self.assertRaises(ToolError) as ctx:
            read_note("big.txt", root=self.root)
        self.assertIn("过大", str(ctx.exception))

    def test_empty_name(self):
        with self.assertRaises(ToolError) as ctx:
            read_note("  ", root=self.root)
        self.assertIn("不能为空", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
