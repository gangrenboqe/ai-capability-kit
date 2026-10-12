"""indexer 测试：正常建索引 / 幂等 / 内容变更 / 空数据 / 异常。"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

# 保证从仓库根目录也能跑（CI 就是这么跑的）。
# 少了这两行，这些测试**只有 cd 进项目目录才通过** —— 自测覆盖不到真实用法。
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from indexer import Doc, build_index, load_docs_from_dir

DOCS = [
    Doc(doc_id="a", source="a.txt", content="这个测试很好用"),
    Doc(doc_id="b", source="b.txt", content="数据库要定期备份"),
    Doc(doc_id="c", source="c.txt", content="binary search tree"),
]


class BuildNormalTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "t.db"
        self.addCleanup(self._tmp.cleanup)

    def test_first_build_counts(self):
        stats = build_index(self.db, DOCS)
        self.assertEqual(stats["inserted"], 3)
        self.assertEqual(stats["total"], 3)

    def test_second_build_inserts_zero(self):
        build_index(self.db, DOCS)
        stats2 = build_index(self.db, DOCS)
        self.assertEqual(stats2["inserted"], 0)
        self.assertEqual(stats2["skipped"], 3)
        self.assertEqual(stats2["updated"], 0)

    def test_no_duplicate_fts_rows(self):
        build_index(self.db, DOCS)
        build_index(self.db, DOCS)
        conn = sqlite3.connect(self.db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM fts_index").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 3)

    def test_changed_doc_updated_not_duplicated(self):
        build_index(self.db, DOCS)
        changed = [Doc(doc_id="a", source="a.txt", content="内容完全换了新版本")]
        stats = build_index(self.db, changed)
        self.assertEqual(stats["updated"], 1)
        conn = sqlite3.connect(self.db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM fts_index").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 3)  # 还是 3 行，旧行被替换


class BuildErrorTest(unittest.TestCase):
    def test_load_docs_missing_dir(self):
        with self.assertRaises(NotADirectoryError):
            load_docs_from_dir("Z:/no/such/dir")

    def test_bad_sqlite_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.db"
            bad.write_text("不是数据库", encoding="utf-8")
            with self.assertRaises((sqlite3.DatabaseError, RuntimeError)):
                build_index(bad, DOCS)


class BuildEmptyTest(unittest.TestCase):
    def test_empty_doc_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            stats = build_index(Path(tmp) / "t.db", [])
            self.assertEqual(
                stats, {"inserted": 0, "updated": 0, "skipped": 0, "empty": 0, "total": 0}
            )

    def test_empty_content_doc_recorded_but_not_searchable(self):
        with tempfile.TemporaryDirectory() as tmp:
            stats = build_index(Path(tmp) / "t.db", [Doc(doc_id="e", source="e.txt", content="")])
            self.assertEqual(stats["empty"], 1)
            self.assertEqual(stats["inserted"], 1)
            conn = sqlite3.connect(Path(tmp) / "t.db")
            try:
                count = conn.execute("SELECT COUNT(*) FROM fts_index").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
