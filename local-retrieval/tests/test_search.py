"""search 测试：SPEC 验收 1 的真实命中 / 排序 / 空库 / 特殊字符 / 异常。"""
import tempfile
import unittest
from pathlib import Path

# 保证从仓库根目录也能跑（CI 就是这么跑的）。
# 少了这两行，这些测试**只有 cd 进项目目录才通过** —— 自测覆盖不到真实用法。
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from indexer import Doc, build_index
from search import search

DOCS = [
    Doc(doc_id="d_test", source="t.txt", content="这个测试很好，大家都满意。"),
    Doc(doc_id="d_bigram", source="b.txt", content="中文分词用二元切分，查询就能命中。"),
    Doc(doc_id="d_db", source="d.txt", content="数据库要定期备份，防止丢数据。"),
    Doc(doc_id="d_en", source="e.txt", content="python standard library only"),
]


def make_db(tmp: str) -> Path:
    db = Path(tmp) / "t.db"
    build_index(db, DOCS)
    return db


class SearchNormalTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = make_db(self._tmp.name)

    def test_spec_acceptance_1(self):
        """SPEC 验收 1：搜「测试」必须命中「这个测试很好」。"""
        res = search(self.db, "测试")
        ids = [h["doc_id"] for h in res["hits"]]
        self.assertIn("d_test", ids)

    def test_single_char_prefix_query(self):
        res = search(self.db, "测")
        self.assertTrue(any(h["doc_id"] == "d_test" for h in res["hits"]))

    def test_ranking_top1_most_relevant(self):
        res = search(self.db, "数据库备份")
        self.assertEqual(res["hits"][0]["doc_id"], "d_db")

    def test_hit_has_content_score_position(self):
        res = search(self.db, "测试")
        top = res["hits"][0]
        for key in ("doc_id", "source", "score", "fragment", "offset"):
            self.assertIn(key, top)
        self.assertGreater(top["score"], 0)
        self.assertGreaterEqual(top["offset"], 0)

    def test_english_query(self):
        res = search(self.db, "standard library")
        self.assertTrue(any(h["doc_id"] == "d_en" for h in res["hits"]))

    def test_top_k_respected(self):
        res = search(self.db, "测试", top_k=1)
        self.assertLessEqual(len(res["hits"]), 1)


class SearchErrorTest(unittest.TestCase):
    def test_missing_db_file(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            search("Z:/no/such.db", "测试")
        self.assertIn("索引库不存在", str(ctx.exception))

    def test_top_k_out_of_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = make_db(tmp)
            with self.assertRaises(ValueError):
                search(db, "测试", top_k=0)
            with self.assertRaises(ValueError):
                search(db, "测试", top_k=99)


class SearchEmptyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = make_db(self._tmp.name)

    def test_no_hit_returns_empty(self):
        res = search(self.db, "绝对查不到的词xyzq")
        self.assertEqual(res["hits"], [])

    def test_punctuation_only_query(self):
        res = search(self.db, "。，！？")
        self.assertEqual(res["hits"], [])

    def test_empty_string_query(self):
        res = search(self.db, "")
        self.assertEqual(res["hits"], [])

    def test_fts_syntax_injection_is_safe(self):
        # 特殊字符走分词器被丢弃，不会变成 FTS5 语法
        res = search(self.db, '"测试" OR 1=1 --')
        ids = [h["doc_id"] for h in res["hits"]]
        self.assertIn("d_test", ids)
        self.assertNotIn("d_db", ids)

    def test_empty_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "empty.db"
            build_index(db, [])
            res = search(db, "测试")
            self.assertEqual(res["hits"], [])


if __name__ == "__main__":
    unittest.main()
