"""中文分词：二元切分（bigram）+ 英文/数字整词。

🔴 为什么不用 FTS5 默认分词器：unicode61 按空格/标点切词，中文没有空格，
整句会被当成一个词——搜「测试」匹配不到「这个测试很好」。
所以入库前先自己切：每个长度 ≥2 的汉字连续段切成全部相邻二元组，
单字成段就保留单字；英文/数字取整词并转小写；标点、emoji、空白都是分隔符。

这一条做完，搜「测试」能命中「这个测试很好」（验收标准 1，测试守着）。
"""
from __future__ import annotations

_CJK_MIN = 0x4E00
_CJK_MAX = 0x9FFF


def _is_cjk(ch: str) -> bool:
    return _CJK_MIN <= ord(ch) <= _CJK_MAX


def bigram_tokenize(text: str) -> list[str]:
    """把文本切成索引用词元列表。空串/纯标点 → []（空数据分支）。"""
    if not isinstance(text, str):
        raise TypeError(f"text 必须是 str，收到 {type(text).__name__}")
    tokens: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if _is_cjk(ch):
            j = i
            while j < n and _is_cjk(text[j]):
                j += 1
            run = text[i:j]
            if len(run) == 1:
                tokens.append(run)
            else:
                tokens.extend(run[k:k + 2] for k in range(len(run) - 1))
            i = j
        elif ch.isascii() and ch.isalnum():
            j = i
            while j < n and text[j].isascii() and text[j].isalnum():
                j += 1
            tokens.append(text[i:j].lower())
            i = j
        else:
            i += 1
    return tokens
