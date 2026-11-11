"""把来源正文切成检索用的块：先按空行分段，段太长再按句子切，句子还太长就硬切。

块长 800 字、重叠 80 字，和 tagent 本地知识库（800 / 50）同一量级，嵌入模型的输入长度也够。
"""

from __future__ import annotations

import re

CHUNK_SIZE = 800
CHUNK_OVERLAP = 80
MAX_CHUNKS = 5000

_PARAGRAPH = re.compile(r"\n\s*\n")
_SENTENCE = re.compile(r"(?<=[。！？!?；;])|(?<=\.)\s+|\n")


def _pieces(text: str, size: int) -> list[str]:
    pieces: list[str] = []
    for paragraph in _PARAGRAPH.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= size:
            pieces.append(paragraph)
            continue
        for sentence in _SENTENCE.split(paragraph):
            sentence = (sentence or "").strip()
            while len(sentence) > size:
                pieces.append(sentence[:size])
                sentence = sentence[size:]
            if sentence:
                pieces.append(sentence)
    return pieces


def split_text(text: str | None, *, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if not text or not text.strip():
        return []
    chunks: list[str] = []
    current = ""
    for piece in _pieces(text, size):
        joiner = "\n\n" if current else ""
        if len(current) + len(joiner) + len(piece) <= size:
            current = current + joiner + piece
            continue
        if current:
            chunks.append(current)
            if len(chunks) >= MAX_CHUNKS:
                return chunks
            tail = current[-overlap:] if overlap else ""
            current = (tail + "\n" + piece) if tail and len(tail) + 1 + len(piece) <= size else piece
        else:
            current = piece
    if current:
        chunks.append(current)
    return chunks[:MAX_CHUNKS]
