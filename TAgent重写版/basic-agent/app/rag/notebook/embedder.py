"""嵌入模型：默认和 tagent 本地知识库同一个 shibing624/text2vec-base-chinese。

- 懒加载：第一次要用时才加载（几秒），加载失败就记下原因，向量检索回 400，
  调用方（tagent）会改用文本检索，和原版「没配嵌入模型」时的行为一样。
- 先只读本机 Hugging Face 缓存（断网也能用），缓存里没有才联网下载——同 tagent 的做法。
- 推理全程串行：tagent 那边实测进程里第一次推理并发会出问题，这里数据量小，串行足够。
"""

from __future__ import annotations

import logging
import threading
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)

BATCH = 32


class Embedder(Protocol):
    name: str

    def available(self) -> bool: ...

    def unavailable_reason(self) -> str: ...

    def embed(self, texts: list[str]) -> np.ndarray: ...


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class DisabledEmbedder:
    """ON_EMBEDDING=off：只用全文检索。"""

    name = ""

    def available(self) -> bool:
        return False

    def unavailable_reason(self) -> str:
        return "嵌入模型已关闭（ON_EMBEDDING=off）"

    def embed(self, texts: list[str]) -> np.ndarray:
        raise RuntimeError(self.unavailable_reason())


class LocalEmbedder:
    def __init__(self, model_name: str):
        self.name = model_name
        self._model = None
        self._error = ""
        self._tried = False
        self._load_lock = threading.Lock()
        self._run_lock = threading.Lock()

    def _load(self):
        with self._load_lock:
            if self._tried:
                return self._model
            self._tried = True
            try:
                from sentence_transformers import SentenceTransformer
            except Exception as exc:  # noqa: BLE001 - 没装依赖也要能起服务
                self._error = f"sentence-transformers 不可用：{exc}"
                log.warning(self._error)
                return None
            try:
                self._model = SentenceTransformer(self.name, local_files_only=True)
                log.info("嵌入模型走本地缓存：%s", self.name)
            except Exception as exc:  # noqa: BLE001
                log.warning("本地缓存里没有嵌入模型（%s），改为联网下载 %s", exc, self.name)
                try:
                    self._model = SentenceTransformer(self.name)
                except Exception as exc2:  # noqa: BLE001
                    self._error = f"嵌入模型加载失败：{exc2}"
                    log.warning(self._error)
                    self._model = None
            return self._model

    def available(self) -> bool:
        return self._load() is not None

    def unavailable_reason(self) -> str:
        self._load()
        return self._error or "嵌入模型不可用"

    def embed(self, texts: list[str]) -> np.ndarray:
        model = self._load()
        if model is None:
            raise RuntimeError(self.unavailable_reason())
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        with self._run_lock:
            vectors = model.encode(
                texts, batch_size=BATCH, normalize_embeddings=True, show_progress_bar=False
            )
        return normalize_rows(vectors)


class SharedEmbedder:
    """和本地知识库共用同一个嵌入模型，进程里只加载一份 text2vec。"""

    def __init__(self, model_name: str):
        self.name = model_name
        self._kb = None
        self._error = ""
        self._load_lock = threading.Lock()
        self._run_lock = threading.Lock()

    def bind(self, knowledge_base) -> None:
        self._kb = knowledge_base

    def _embeddings(self):
        kb = self._kb
        if kb is None:
            self._error = "嵌入模型还没接上本地知识库"
            return None
        with self._load_lock:
            if getattr(kb, "embeddings", None) is None:
                try:
                    from app.rag.knowledge_base import _load_default_embeddings

                    kb.embeddings = _load_default_embeddings()
                except Exception as exc:  # noqa: BLE001
                    self._error = f"嵌入模型加载失败：{exc}"
                    log.warning(self._error)
                    return None
            return kb.embeddings

    def available(self) -> bool:
        try:
            return self._embeddings() is not None
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            return False

    def unavailable_reason(self) -> str:
        self.available()
        return self._error or "嵌入模型不可用"

    def embed(self, texts: list[str]) -> np.ndarray:
        embeddings = self._embeddings()
        if embeddings is None:
            raise RuntimeError(self.unavailable_reason())
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        with self._run_lock:
            vectors = embeddings.embed_documents(list(texts))
        return normalize_rows(np.asarray(vectors, dtype=np.float32))
