"""tokenizer 测试：分词正确性 / 异常 / 空数据 / 特殊字符。"""
import unittest

# 保证从仓库根目录也能跑（CI 就是这么跑的）。
# 少了这两行，这些测试**只有 cd 进项目目录才通过** —— 自测覆盖不到真实用法。
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tokenizer import bigram_tokenize


class TokenizerNormalTest(unittest.TestCase):
    def test_chinese_bigram(self):
        # SPEC 验收 1 的底层保证：这个切法让「测试」能命中「这个测试很好」
        self.assertEqual(bigram_tokenize("这个测试很好"), ["这个", "个测", "测试", "试很", "很好"])

    def test_single_cjk_char_kept(self):
        self.assertEqual(bigram_tokenize("测"), ["测"])

    def test_english_lowercased_whole_word(self):
        self.assertEqual(bigram_tokenize("Hello FTS5"), ["hello", "fts5"])

    def test_mixed_cn_en(self):
        self.assertEqual(bigram_tokenize("用FTS5建索引"), ["用", "fts5", "建索", "索引"])

    def test_digits_whole_word(self):
        self.assertEqual(bigram_tokenize("25 条用例"), ["25", "条用", "用例"])


class TokenizerErrorTest(unittest.TestCase):
    def test_non_string_rejected(self):
        with self.assertRaises(TypeError):
            bigram_tokenize(123)  # type: ignore[arg-type]

    def test_none_rejected(self):
        with self.assertRaises(TypeError):
            bigram_tokenize(None)  # type: ignore[arg-type]


class TokenizerEmptyTest(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(bigram_tokenize(""), [])

    def test_punctuation_only(self):
        self.assertEqual(bigram_tokenize("。，！？?!."), [])

    def test_emoji_only(self):
        self.assertEqual(bigram_tokenize("😀🎉👍"), [])

    def test_whitespace_only(self):
        self.assertEqual(bigram_tokenize("  \n\t "), [])


if __name__ == "__main__":
    unittest.main()
