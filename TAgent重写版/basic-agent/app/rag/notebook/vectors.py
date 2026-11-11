"""向量检索：把所有向量拼成一个矩阵放内存，查询时一次矩阵乘法算余弦。

矩阵按「写入版本号」缓存：仓储每次改动向量都把版本号加一，下次查询发现版本变了才重建。
（单进程写库，版本号放内存就够；多进程部署要换成库里的计数。）
"""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class VectorRow:
    kind: str        # "chunk" | "insight" | "note"
    item_id: str     # 命中后返回的 id：分块→来源 id，洞察→洞察 id，笔记→笔记 id
    parent_id: str   # 来源 id 或笔记 id，用来按笔记本过滤
    text: str


def to_blob(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


class VectorCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._version = -1
        self._rows: list[VectorRow] = []
        self._matrix = np.zeros((0, 0), dtype=np.float32)

    def snapshot(
        self, version: int, loader: Callable[[], list[tuple[VectorRow, bytes]]]
    ) -> tuple[list[VectorRow], np.ndarray]:
        with self._lock:
            if version != self._version:
                loaded = [(row, from_blob(blob)) for row, blob in loader()]
                widths = Counter(vector.shape[0] for _, vector in loaded if vector.shape[0])
                width = widths.most_common(1)[0][0] if widths else 0
                rows: list[VectorRow] = []
                vectors: list[np.ndarray] = []
                for row, vector in loaded:
                    if vector.shape[0] != width:
                        continue  # 换过嵌入模型留下的旧向量：维度对不上就跳过
                    rows.append(row)
                    vectors.append(vector)
                self._rows = rows
                self._matrix = np.vstack(vectors) if vectors else np.zeros((0, 0), dtype=np.float32)
                self._version = version
            return self._rows, self._matrix


def cosine_scores(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """矩阵和查询向量入库前都已归一化，点积就是余弦。维度不一致回空。"""
    if matrix.size == 0 or query.size == 0 or matrix.shape[1] != query.shape[-1]:
        return np.zeros((0,), dtype=np.float32)
    return matrix @ query.reshape(-1)
