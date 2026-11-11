"""纯函数：分层检查、切词、分块、编号、网址检查、抽取、策略解析。"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.errors.notebook import ExtractionFailed, InvalidInput
from app.infra.notebook.extractor import extract_bytes, html_to_text, is_supported_file
from app.infra.notebook.llm_client import strip_thinking
from app.infra.notebook.url_guard import validate_url
from app.rag.notebook.chunking import split_text
from app.rag.notebook.tokenize import index_tokens, match_expression, query_tokens
from app.service.notebook.ask_service import parse_strategy
from app.service.notebook.chat_service import estimate_tokens, render_context
from app.util.notebook.ids import new_id, normalize
from tools.check_architecture import check


def test_architecture_rules_hold():
    problems, count = check()
    assert problems == []
    assert count > 40


def test_index_tokens_cover_chinese_unigrams_and_bigrams():
    tokens = index_tokens("递归函数 Recursion_Depth 42").split()
    assert {"递", "归", "函", "数", "递归", "归函", "函数"} <= set(tokens)
    assert "recursion" in tokens and "depth" in tokens and "42" in tokens


def test_query_tokens_use_bigrams_and_single_char():
    assert query_tokens("函数调用") == ["函数", "数调", "调用"]
    assert query_tokens("树") == ["树"]
    assert query_tokens("Hello, WORLD!") == ["hello", "world"]
    assert query_tokens("！？。") == []
    assert match_expression(["a", "函数"]) == '"a" OR "函数"'


def test_query_tokens_are_capped():
    assert len(query_tokens("字" * 500 + "".join(chr(0x4E00 + i) for i in range(500)))) <= 64


def test_split_text_respects_size_and_keeps_everything():
    text = "\n\n".join(f"第{i}段。" + "内容" * 120 for i in range(10))
    chunks = split_text(text, size=300, overlap=30)
    assert all(len(chunk) <= 300 for chunk in chunks)
    joined = "".join(chunks)
    for i in range(10):
        assert f"第{i}段" in joined
    assert split_text("   ") == []
    assert split_text("短文本") == ["短文本"]


def test_split_text_hard_splits_long_lines():
    chunks = split_text("x" * 2000, size=800, overlap=0)
    assert [len(c) for c in chunks] == [800, 800, 400]


def test_ids_round_trip():
    record = new_id("source")
    assert record.startswith("source:") and len(record) == len("source:") + 20
    assert normalize("source", record) == record
    assert normalize("source", record.split(":")[1]) == record
    assert normalize("source", "note:abc") is None
    assert normalize("source", "source:../etc") is None
    assert normalize("source", "") is None


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x", "http://localhost:5055/api", "http://10.0.0.8/", "http://[::1]/",
    "http://169.254.169.254/latest/meta-data", "ftp://example.com/a", "file:///etc/passwd",
    "http://user:pw@example.com/",
])
def test_validate_url_blocks_private_and_odd_urls(url):
    with pytest.raises(InvalidInput):
        validate_url(url, allow_private=False)


def test_validate_url_allows_private_when_configured():
    assert validate_url("http://127.0.0.1:9/x", allow_private=True) == "http://127.0.0.1:9/x"


def test_html_to_text_drops_scripts_and_keeps_title():
    result = html_to_text(
        "<html><head><title> 标题 </title><style>.a{}</style></head>"
        "<body><script>alert(1)</script><h1>大标题</h1><p>第一段&amp;内容</p><p>第二段</p></body></html>"
    )
    assert result.title == "标题"
    assert "alert" not in result.content and ".a{}" not in result.content
    assert "大标题" in result.content and "第一段&内容" in result.content and "第二段" in result.content


def _docx(paragraphs: list[str]) -> bytes:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def test_extract_docx_and_text_encodings():
    assert extract_bytes(_docx(["第一段", "第二段"]), suffix=".docx").content == "第一段\n第二段"
    assert extract_bytes("中文内容".encode("gb18030"), suffix=".txt").content == "中文内容"
    assert extract_bytes("﻿带BOM".encode("utf-8"), suffix=".md").content == "带BOM"


def test_extract_rejects_unknown_and_broken_files():
    with pytest.raises(ExtractionFailed):
        extract_bytes(b"\x00\x01", suffix=".exe")
    with pytest.raises(ExtractionFailed):
        extract_bytes(b"not a zip", suffix=".docx")
    assert is_supported_file("a.PDF") and not is_supported_file("a.mp3")


def test_strip_thinking():
    assert strip_thinking("<think>想一想</think>\n答案") == "答案"


def test_parse_strategy_falls_back_on_garbage():
    assert parse_strategy("不是 JSON", "问题")["searches"] == [{"term": "问题", "instructions": "问题"}]
    parsed = parse_strategy('前缀 {"reasoning": "r", "searches": [{"term": "a"}, {"term": ""}, {"term": "b"},'
                            ' {"term": "c"}, {"term": "d"}]} 后缀', "q")
    assert [s["term"] for s in parsed["searches"]] == ["a", "b", "c"]


def test_render_context_and_tokens():
    text = render_context({"sources": [{"id": "source:a", "title": "T", "full_text": "正文",
                                        "insights": [{"insight_type": "摘要", "content": "要点"}]}],
                           "notes": [{"id": "note:b", "title": "N", "content": "笔记"}]})
    assert "[source:a] T" in text and "## 摘要\n要点" in text and "[note:b] N\n笔记" in text
    assert render_context({}) == "（用户没有选择任何资料）"
    assert estimate_tokens("中文abcd") == 3
