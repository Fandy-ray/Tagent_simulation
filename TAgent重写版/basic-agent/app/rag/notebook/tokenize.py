"""全文检索的切词：英文按单词，中日韩按「单字 + 相邻两字」。

原版 SurrealDB 的分词器是 blank/class/camel/punct + snowball(english)，中文一整句被当成一个词，
所以「函数」搜不到「递归函数的定义」。这里先把文字切好、用空格连起来，再交给 FTS5 的 unicode61
（它只按空格和标点切），中文两字词就能命中，BM25 也照常排序。
"""

from __future__ import annotations

import re

_CJK = "぀-ヿ㐀-䶿一-鿿가-힯豈-﫿"
_RUN = re.compile(f"([{_CJK}]+)|([^\\W_{_CJK}]+)")
_MAX_WORD = 40
_MAX_QUERY_TOKENS = 64


def index_tokens(text: str | None) -> str:
    """入库用：中文单字和两字都存，这样单字查询和两字查询都能命中。"""
    if not text:
        return ""
    out: list[str] = []
    for cjk, word in _RUN.findall(text.lower()):
        if cjk:
            out.extend(cjk)
            out.extend(cjk[i : i + 2] for i in range(len(cjk) - 1))
        elif word:
            out.append(word[:_MAX_WORD])
    return " ".join(out)


def query_tokens(text: str | None) -> list[str]:
    """查询用：中文只取两字（只有一个字才用单字），英文取单词；去重、限量。"""
    if not text:
        return []
    seen: dict[str, None] = {}
    for cjk, word in _RUN.findall(text.lower()):
        if cjk:
            grams = [cjk] if len(cjk) == 1 else [cjk[i : i + 2] for i in range(len(cjk) - 1)]
            for gram in grams:
                seen.setdefault(gram, None)
        elif word:
            seen.setdefault(word[:_MAX_WORD], None)
        if len(seen) >= _MAX_QUERY_TOKENS:
            break
    return list(seen)[:_MAX_QUERY_TOKENS]


def match_expression(tokens: list[str]) -> str:
    """FTS5 的 MATCH 表达式：每个词加引号（词里只有字母数字，不会出现引号），用 OR 连。"""
    return " OR ".join(f'"{token}"' for token in tokens)
