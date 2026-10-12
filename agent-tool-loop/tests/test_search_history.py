"""search_history 工具测试：正常 / 异常 / 空数据 / 特殊字符。"""
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_loop import ToolError  # noqa: E402
from demo import seed_db  # noqa: E402
from tools.search_history import search_history  # noqa: E402


class SearchNormalTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "sessions.db"
        seed_db(self.db)
        self.addCleanup(self._tmp.cleanup)

    def test_keyword_hit(self):
        out = search_history("二元分词", db_path=self.db)
        self.assertEqual(out["count"], 2)
        self.assertIn("二元分词", out["results"][0]["content"])

    def test_limit(self):
        out = search_history("的", limit=3, db_path=self.db)
        self.assertEqual(out["count"], 3)

    def test_result_fields(self):
        out = search_history("二元分词", db_path=self.db)
        row = out["results"][0]
        for key in ("session_id", "role", "content", "created_at"):
            self.assertIn(key, row)

    def test_percent_escaped(self):
        # % 是 LIKE 通配符：搜「100%」必须按字面匹配，不能变成通配
        out = search_history("100%", db_path=self.db)
        self.assertEqual(out["count"], 0)


class SearchErrorTest(unittest.TestCase):
    def test_empty_keyword(self):
        with self.assertRaises(ToolError) as ctx:
            search_history("  ", db_path=":memory:")
        self.assertIn("不能为空", str(ctx.exception))

    def test_limit_out_of_range(self):
        with self.assertRaises(ToolError) as ctx:
            search_history("x", limit=0, db_path=":memory:")
        self.assertIn("1~50", str(ctx.exception))

    def test_limit_too_big(self):
        with self.assertRaises(ToolError) as ctx:
            search_history("x", limit=51, db_path=":memory:")
        self.assertIn("1~50", str(ctx.exception))

    def test_db_missing(self):
        with self.assertRaises(ToolError) as ctx:
            search_history("x", db_path="Z:/definitely/not/here.db")
        self.assertIn("数据库不存在", str(ctx.exception))

    def test_db_not_a_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.db"
            bad.write_text("这不是数据库", encoding="utf-8")
            with self.assertRaises(ToolError) as ctx:
                search_history("x", db_path=bad)
            self.assertIn("查询数据库失败", str(ctx.exception))


class SearchEmptyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "sessions.db"
        seed_db(self.db)
        self.addCleanup(self._tmp.cleanup)

    def test_no_hit_returns_empty(self):
        out = search_history("绝对不存在的关键词xyz", db_path=self.db)
        self.assertEqual(out, {"count": 0, "results": []})

    def test_underscore_is_literal(self):
        # _ 在 LIKE 里是单字通配符，必须按字面匹配
        out = search_history("s_", db_path=self.db)
        self.assertEqual(out["count"], 0)


if __name__ == "__main__":
    unittest.main()
