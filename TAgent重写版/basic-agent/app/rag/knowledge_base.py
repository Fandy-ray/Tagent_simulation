"""本地知识库：加载、切块、建索引、检索、采样。

三个 service 共用同一个实例——嵌入模型和 FAISS 索引都很贵，
不能让 ChatService / QuizService / ExamService 各建一份。

线程安全：_vector_lock 只保护建索引这一步；检索本身是只读的。
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import random
import re
import threading
import time
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.config import (
    DEFAULT_KNOWLEDGE_FILE,
    DEFAULT_TEXT_DB_DIR,
    EXAM_CONTEXT_CHAR_LIMIT,
    EXAM_MMR_FETCH_K,
    EXAM_MMR_LAMBDA,
    EXAM_TEXTBOOK_MIN_SHARE,
    EXAM_SAMPLE_K,
)
from app.rag.citations import annotate_book_locations
from app.rag.index_cache import IndexCache, atomic_write, cache_lock, json_bytes, loaded_embedding_revision
from app.rag.query_embedder import QueryEmbedder
from app.rag.query_result_cache import QueryResultCache
from app.rag.references import (
    REFERENCE_CHUNK_FORMAT,
    WINDOW_OVERLAP,
    WINDOW_SIZE,
    reference_documents,
    reference_files,
    retrieval_windows,
)
from app.util.markdown_sanitizer import clean_reference_for_display, truncate_markdown_fragment


log = logging.getLogger(__name__)
EMBEDDING_MODEL = "shibing624/text2vec-base-chinese"
# 教材按标题切节后再按 800 字一块、相邻两块重叠 50 字切（论文同样大小，另见 references.py 的检索窗口）。
# 管理后台「文档」页直接展示这几个常量，别在别处再抄一遍数字
TEXTBOOK_CHUNK_SIZE = 800
TEXTBOOK_CHUNK_OVERLAP = 50
# 答疑每次取几块不重复的材料给模型
QA_RETRIEVE_K = 4
# 切块参数或缓存格式一变就要改这个值：缓存按「教材内容 + 嵌入模型 + 这个值」认，
# 改了才会重建，不然会拿旧切法的索引配新切法的片段
INDEX_CACHE_FORMAT = "faiss-v1-md-headers-800-50-locations"


def _load_default_embeddings():
    """优先只读本机 Hugging Face 缓存，缓存里没有才联网下载。

    以前用 snapshot_download(local_files_only=True) 判断缓存在不在，但它按模型仓库的
    **完整**文件清单核对：这个仓库还带 onnx / openvino 等我们用不到的文件，缓存里没有，
    于是每次都被判「缓存不完整」而改走联网——联网时启动慢（实测 27.7 秒后仍然失败），
    断网时直接失败，本地教材检索跟着不能用。其实 sentence-transformers 要的权重、
    分词器、池化配置都在缓存里，让它自己只读本地，断网也是 3 秒左右加载完。
    """
    from langchain_huggingface import HuggingFaceEmbeddings

    try:
        embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL, model_kwargs={"local_files_only": True}
        )
        log.info("嵌入模型走本地缓存：%s", EMBEDDING_MODEL)
        return _half_precision_on_gpu(embeddings)
    except Exception as exc:
        log.warning("本地缓存里没有可用的嵌入模型（%s），改为联网下载 %s", exc, EMBEDDING_MODEL)
    return _half_precision_on_gpu(HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL))


def _half_precision_on_gpu(embeddings):
    """在显卡上（Apple 的 MPS、NVIDIA 的 CUDA）用半精度算：成批快 25% 左右，结果不变——
    实测 50 个问题的前 4 块和全精度一块不差、顺序也一样，同一句的向量余弦相似度 0.999999。
    CPU 上半精度反而慢（有的算子还不支持），不动。"""
    client = getattr(embeddings, "_client", None)
    device = getattr(getattr(client, "device", None), "type", "")
    if device in ("mps", "cuda"):
        client.half()
        log.info("嵌入模型在 %s 上用半精度", device)
    return embeddings


# 最近这么久里有人检索，就让嵌入模型保持醒着（见 app/rag/query_embedder.py）。只在显卡上做：
# 空算的间隔：实测隔 0.05~1 秒再算一句约 30 毫秒，隔 2 秒以上就到 56 毫秒，1 秒偶尔也会到 74。
# CPU 上（没有独显的 Windows 笔记本等）隔 0.4 秒、2 秒、5 秒再算都是 43~44 毫秒，空算毫无用处，
# 反而上课时一直占着约 7% 的 CPU（4 线程），还和真的检索排一个队
QUERY_KEEP_WARM_SECONDS = 120.0
QUERY_WARM_INTERVAL_SECONDS = 0.4


def _query_embedder_for(embeddings) -> QueryEmbedder:
    """一批检索词怎么一起算。HuggingFace 的嵌入没给查询专用参数时，embed_query 就是单条的 embed_documents，
    可以直接成批，也值得让它保持醒着；在显卡上再补成固定形状（见 _FixedShapeQueries）。
    别的实现（单测里的假嵌入等）不知道两者是否等价，就一条条调 embed_query。"""
    if type(embeddings).__name__ == "HuggingFaceEmbeddings" and not getattr(embeddings, "query_encode_kwargs", None):
        batch = embeddings.embed_documents
        on_gpu = bool(_gpu_device(embeddings))
        if not getattr(embeddings, "encode_kwargs", None) and on_gpu:
            batch = _FixedShapeQueries(embeddings._client)
        return QueryEmbedder(
            batch,
            keep_warm_s=QUERY_KEEP_WARM_SECONDS if on_gpu else 0.0,
            warm_interval_s=QUERY_WARM_INTERVAL_SECONDS,
        )
    return QueryEmbedder(lambda texts: [embeddings.embed_query(text) for text in texts])


def _gpu_device(embeddings) -> str:
    device = getattr(getattr(getattr(embeddings, "_client", None), "device", None), "type", "")
    return device if device in ("mps", "cuda") else ""


class _FixedShapeQueries:
    """在显卡上算检索词：每一批先补成固定的几种形状再算。

    显卡上 PyTorch 每遇到一种新的输入形状（几句 × 多长）都要现编一遍算子，第一次算比之后慢好几倍。
    实测（几句到十几句、长短不一的检索词每 0.3 秒来一批）：P95 212 毫秒；同一组形状再来一遍只要 78 毫秒。
    条数补到 2 的幂、长度补到 16 的倍数之后，形状只剩几十种，启动时先各算一遍（prewarm），之后就都是熟的。
    补的是空句和填充位，均值池化只看真实的字，算出的向量和不补时一模一样（实测最大差 0.0）。
    """

    LENGTH_STEP = 16

    def __init__(self, model):
        import torch

        self._torch = torch
        self._model = model
        self._tokenize = getattr(model, "preprocess", None) or model.tokenize
        self._pad_id = model.tokenizer.pad_token_id or 0
        self._max_length = model.max_seq_length

    def __call__(self, texts: list[str]) -> list[list[float]]:
        count = len(texts)
        size = 1 << (count - 1).bit_length()
        features = self._tokenize(list(texts) + [""] * (size - count))
        length = features["input_ids"].shape[1]
        target = max(length, min(-(-length // self.LENGTH_STEP) * self.LENGTH_STEP, self._max_length))
        prepared = {}
        for key, value in features.items():
            if isinstance(value, self._torch.Tensor):
                if value.dim() == 2 and target > length:
                    fill = self._pad_id if key == "input_ids" else 0
                    value = self._torch.nn.functional.pad(value, (0, target - length), value=fill)
                value = value.to(self._model.device)
            prepared[key] = value
        with self._torch.inference_mode():
            vectors = self._model.forward(prepared)["sentence_embedding"]
        return vectors[:count].float().cpu().tolist()

    def prewarm(self, *, max_batch: int = 16, max_length: int = 64, run=None) -> None:
        """把形状先各算一遍（条数 1、2、4…max_batch × 长度 16、32…max_length）。
        run 给了就每种形状交给它去跑（QueryEmbedder.run_exclusive：不和真的检索同时算）。"""
        size = 1
        while size <= max_batch:
            for length in range(self.LENGTH_STEP, max_length + 1, self.LENGTH_STEP):
                texts = ["排" * (length - 2)] * size  # 加上首尾两个特殊符号正好 length
                if run is None:
                    self(texts)
                else:
                    run(lambda texts=texts: self(texts))
            size *= 2


class KnowledgeBase:
    def __init__(
        self,
        *,
        text_db_dir: str | Path | None = None,
        knowledge_file: str | Path | None = None,
        embeddings=None,
        vectorstore=None,
        index_cache_dir: str | Path | None = None,
        references_dir: str | Path | None = None,
        embedding_revision: str | None = None,
        retrieval_cache_enabled: bool = True,
        retrieval_cache_max_entries: int = 128,
        retrieval_cache_ttl_seconds: int = 60,
    ):
        self.text_db_dir = Path(text_db_dir or DEFAULT_TEXT_DB_DIR)
        # 参考文献目录（《系统仿真学报》等论文抽出的 .md）；None = 只用教材（单测默认如此）
        self.references_dir = Path(references_dir) if references_dir else None
        # 向量索引的磁盘缓存目录；None = 不缓存（单测注入假嵌入时就是这样）
        self.index_cache_dir = Path(index_cache_dir) if index_cache_dir else None
        self.knowledge_file = Path(knowledge_file or DEFAULT_KNOWLEDGE_FILE)
        self.embeddings = embeddings
        # 注入模型的调用方可提供稳定版本；默认只相信已加载模型的实际 commit。
        self.embedding_revision = embedding_revision
        self.vectorstore = vectorstore
        self._knowledge_chunks: list[Document] | None = None
        # 并进索引的参考文献篇数，建好块之后才知道（describe 每次检索都会被调，不能每次去列目录）
        self._reference_count: int | None = None
        # 嵌入模型是否已经单线程推理过一次（见 ensure_index）
        self._query_ready = False
        self._vector_lock = threading.RLock()
        self._source_sha256: str | None = None
        self._retrieval_identity: str | None = None
        self._retrieval_cache = QueryResultCache(
            enabled=retrieval_cache_enabled, max_entries=retrieval_cache_max_entries,
            ttl_seconds=retrieval_cache_ttl_seconds,
        )
        # 检索词的嵌入（同时到的合成一批、算过的记住），跟着嵌入模型走：模型换了就换一个。
        # 建它要加锁：几个线程同时做第一次检索时各建一个的话，「同一时刻只算一批」就管不住了
        self._query_embedder: QueryEmbedder | None = None
        self._query_embedder_model = None
        self._query_embedder_lock = threading.Lock()
        self._query_shapes_prewarmed = False

    def describe(self) -> dict[str, Any]:
        return {
            "kind": "local",
            "file": str(self.knowledge_file),
            "references": self._reference_count,
            "indexed": self.vectorstore is not None,
        }

    def admin_snapshot(self) -> dict[str, Any]:
        """管理后台「文档」页：这个知识库实际在用的配置和状态。只读，不会触发加载模型或建索引。"""
        chunks = self._knowledge_chunks or []
        paper_chunks = sum(1 for chunk in chunks if chunk.metadata.get("source") == "reference")
        identity = self._model_identity() if self.embeddings is not None else None
        index = getattr(self.vectorstore, "index", None)
        return {
            "kind": "local",
            "textbook": {"file": self.knowledge_file.name, "chunks": len(chunks) - paper_chunks},
            "references": {
                "enabled": self.references_dir is not None,
                "papers": self._reference_count,
                "chunks": paper_chunks,
            },
            "embedding": {
                "model": EMBEDDING_MODEL,
                "loaded": self.embeddings is not None,
                "revision": identity["revision"] if identity else None,
            },
            "chunking": {
                "chunk_size": TEXTBOOK_CHUNK_SIZE,
                "chunk_overlap": TEXTBOOK_CHUNK_OVERLAP,
                "reference_window": WINDOW_SIZE,
                "reference_window_overlap": WINDOW_OVERLAP,
            },
            "retrieval": {
                "qa_top_k": QA_RETRIEVE_K,
                "cache": self._retrieval_cache.stats(),
                "query_embeddings": self._query_embedder.stats() if self._query_embedder else None,
            },
            "exam": {
                "sample_k": EXAM_SAMPLE_K,
                "textbook_min_share": EXAM_TEXTBOOK_MIN_SHARE,
                "mmr_lambda": EXAM_MMR_LAMBDA,
                "mmr_fetch_k": EXAM_MMR_FETCH_K,
                "context_char_limit": EXAM_CONTEXT_CHAR_LIMIT,
            },
            "index": {
                "ready": self.vectorstore is not None,
                "vectors": int(index.ntotal) if index is not None else None,
                "disk_cache": self.index_cache_dir is not None,
            },
        }

    def clear_retrieval_cache(self) -> int:
        return self._retrieval_cache.clear()

    def reload(self) -> dict[str, Any]:
        """重新读教材和参考文献，建好（或从缓存读回）索引后整体换上。补下载了论文不用重启后端。

        在旁边用同样的配置另建一份，建好之前现在这份照常服务；换的时候切块、索引、来源指纹、
        检索缓存一起换，正在进行的检索拿着旧对象做完，不会读到建了一半的状态。
        块向量有缓存，只嵌入新出现的块（加一篇论文几秒）。嵌入模型共用，不重新加载。
        """
        shadow = KnowledgeBase(
            text_db_dir=self.text_db_dir,
            knowledge_file=self.knowledge_file,
            embeddings=self.embeddings,
            index_cache_dir=self.index_cache_dir,
            references_dir=self.references_dir,
            embedding_revision=self.embedding_revision,
            retrieval_cache_enabled=self._retrieval_cache.enabled,
            retrieval_cache_max_entries=self._retrieval_cache.max_entries,
            retrieval_cache_ttl_seconds=self._retrieval_cache.ttl_seconds,
        )
        # 嵌入模型是共用的：这边已经做过第一次推理，那边就不必再做（见 ensure_index）
        shadow._query_ready = self._query_ready
        shadow.ensure_index()
        with self._vector_lock:
            self._knowledge_chunks = shadow._knowledge_chunks
            self._reference_count = shadow._reference_count
            self._source_sha256 = shadow._source_sha256
            self._retrieval_identity = None
            self._retrieval_cache = shadow._retrieval_cache
            self.embeddings = shadow.embeddings
            self.vectorstore = shadow.vectorstore
            self._query_ready = True
        return {"chunks": len(self._knowledge_chunks or []), "papers": self._reference_count}

    def warm_up(self) -> None:
        """启动时预热：加载嵌入模型并建好索引，避免首个请求扛这份开销。

        在显卡上再把检索词的形状各算一遍（见 _FixedShapeQueries）：最常见的（≤16 句、≤64 字）当场算，
        约 1 秒；大一些的（≤32 句、≤96 字）放到后台一种一种地算，约 2 秒，不拖慢启动，也不和真的检索抢。
        只做一次：组合知识库在这个来源出错恢复时会再调 warm_up（那时已经在答疑了），不必也不该再算一遍；
        每种形状都走嵌入器的队列（run_exclusive），不会和真的检索同时上显卡。
        """
        self.ensure_index()
        embedder = self._current_query_embedder()
        prewarm = getattr(embedder.batch_function, "prewarm", None)
        with self._query_embedder_lock:
            if prewarm is None or self._query_shapes_prewarmed:
                return
            self._query_shapes_prewarmed = True
        started = time.perf_counter()
        prewarm(run=embedder.run_exclusive)
        log.info("检索词嵌入的常见形状预热完：%.1f 秒", time.perf_counter() - started)
        threading.Thread(
            target=prewarm,
            kwargs={"max_batch": 32, "max_length": 96, "run": embedder.run_exclusive},
            name="query-shape-prewarm",
            daemon=True,
        ).start()

    def search(self, query: str, *, k: int = 3, notebook_ids: list[str] | None = None) -> list[Document]:
        """相似度检索。判卷时给解答题补充知识片段用。"""
        self.ensure_index()
        return self._distinct_search(query, k)

    def quiz_documents(self, *, max_documents: int = 2) -> list[Document]:
        return select_quiz_documents(self.chunks(), max_documents=max_documents)

    def retrieve(self, query: str, notebook_ids: list[str] | None = None):
        self.ensure_index()
        documents = self._distinct_search(query, QA_RETRIEVE_K)
        context = "\n\n---\n\n".join(document.page_content for document in documents)
        return context, documents
    def _distinct_search(self, query: str, k: int) -> list[Document]:
        """取 k 块不重复的。一块论文最多切出十来个检索窗口，靠前的窗口挤在两三块上时多取几轮，免得少给。"""
        if self._retrieval_identity is None:
            # 内存缓存不会跨实例；未知模型版本可用，但不能复用到磁盘或其他实例。
            self._retrieval_identity = hashlib.sha256(json_bytes({
                "corpus": self._source_sha256, "model": self._model_identity(),
                "retrieval": "distinct-parent-v1", "chunks": f"{INDEX_CACHE_FORMAT}/{REFERENCE_CHUNK_FORMAT}",
            })).hexdigest()
        return self._retrieval_cache.get_or_load(
            query, identity=self._retrieval_identity, k=k, load=lambda: self._uncached_distinct_search(query, k),
        )

    def _current_query_embedder(self) -> QueryEmbedder:
        with self._query_embedder_lock:
            embeddings = self.embeddings
            embedder = self._query_embedder
            if embedder is None or self._query_embedder_model is not embeddings:
                embedder = _query_embedder_for(embeddings)
                self._query_embedder, self._query_embedder_model = embedder, embeddings
                self._query_shapes_prewarmed = False
            return embedder

    def _embed_query(self, text: str) -> list[float]:
        return self._current_query_embedder().embed(text)

    def _uncached_distinct_search(self, query: str, k: int) -> list[Document]:
        fetch = k * _FETCH_FACTOR
        vector = self._embed_query(query)
        while True:
            documents = self.vectorstore.similarity_search_by_vector(vector, k=fetch)
            picked = _distinct(documents, k)
            if len(picked) >= k or len(documents) < fetch:
                return picked
            fetch *= 2

    def ensure_index(self) -> list[Document]:
        if self._knowledge_chunks is not None and self.vectorstore is not None and self._query_ready:
            return self._knowledge_chunks
        with self._vector_lock:
            self.chunks()
            if self.vectorstore is None:
                if self.embeddings is None:
                    self.embeddings = _load_default_embeddings()
                self.vectorstore = self._load_or_build_index()
            if not self._query_ready:
                # 进程里**第一次**推理必须单线程做完：16 路检索同时成为第一次推理，
                # 实测 3 次里 2 次段错误（进程直接没了）、1 次卡死（CPU 空转 700%）；先单独推理一次，
                # 之后 16 路同时只要 0.3 秒（2026-10-03）。以前预热总要嵌入整本教材，顺带做了这一步；
                # 有了索引缓存以后预热只读盘、不推理，第一次推理就落到了学生的第一个问题上。
                # 在锁里做：预热之前就到的检索都在这里排队，等这一次做完。
                if self.embeddings is not None:
                    self.embeddings.embed_query("预热")
                self._query_ready = True
            return self._knowledge_chunks

    # ---------------------------------------------------------------- 索引缓存
    #
    # 以前每次启动都把整本教材重新嵌入一遍建 FAISS 索引：本机实测预热 23 秒，其中 20 秒在这一步
    # （2026-10-02）。教材不常变，建好的索引存到应用数据目录里，下次启动直接读回来。
    # 放应用数据目录而不是项目目录，理由同学习记录库：项目在 iCloud 同步的桌面上。

    def _index_cache_path(self) -> Path | None:
        cache = self._index_cache()
        return cache.directory if cache else None

    def _model_identity(self) -> dict | None:
        revision = self.embedding_revision or loaded_embedding_revision(self.embeddings)
        if not revision:
            return None
        return {
            "model": EMBEDDING_MODEL,
            "revision": revision,
            "precision": "float32",
            "encode_kwargs": getattr(self.embeddings, "encode_kwargs", {}) or {},
        }

    def _index_cache(self) -> IndexCache | None:
        identity = self._model_identity()
        if self.index_cache_dir is None or identity is None:
            return None
        self.chunks()
        return IndexCache(
            self.index_cache_dir, source_sha256=self._source_sha256,
            model_identity=identity, chunk_format=f"{INDEX_CACHE_FORMAT}/{REFERENCE_CHUNK_FORMAT}",
        )

    def _load_or_build_index(self):
        from langchain_community.vectorstores import FAISS

        # 教材一块一条；论文一块拆成几个检索窗口，向量按窗口算，存的仍是整块（见 references.WINDOW_SIZE）
        entries = [
            (window, chunk)
            for chunk in self._knowledge_chunks
            for window in (
                retrieval_windows(chunk) if chunk.metadata.get("source") == "reference" else [chunk.page_content]
            )
        ]
        documents = [Document(page_content=chunk.page_content, metadata={k: v for k, v in chunk.metadata.items() if k != "body"}) for _, chunk in entries]

        def build():
            vectors = self._embed_reusing_memo([window for window, _ in entries])
            return FAISS.from_embeddings(
                [(doc.page_content, vector) for doc, vector in zip(documents, vectors)],
                self.embeddings, metadatas=[doc.metadata for doc in documents],
            )

        cache = self._index_cache()
        if cache is None:
            if self.index_cache_dir is not None:
                log.warning("嵌入模型实际版本不可确认，禁用跨启动的磁盘缓存。")
            return build()
        with cache_lock(cache.directory) as writable:
            if writable:
                stored = cache.load(self.embeddings, documents)
                if stored is not None:
                    return stored
            store = build()
            if writable:
                cache.save(store)
            return store

    # ---------------------------------------------------------------- 逐块的向量缓存
    #
    # 上面的索引缓存按「教材 + 全部论文」整体认：加一篇论文、改一行教材，整份就作废，
    # 以前要把 2400 多块全部重新嵌入（本机 61~69 秒，嵌入速度和线程数、Apple GPU 都几乎无关）。
    # 这里另存一份「每块文字 → 向量」，重建时只嵌入新出现的块：加一篇论文只算它自己那二十来块。

    def _vector_memo_path(self) -> Path | None:
        identity = self._model_identity()
        if self.index_cache_dir is None or identity is None:
            return None
        model = hashlib.sha256(json_bytes(identity)).hexdigest()
        return self.index_cache_dir / "safe-v3" / f".chunk-vectors-{model}.npz"

    def _embed_reusing_memo(self, texts: list[str]) -> list[list[float]]:
        memo_path = self._vector_memo_path()
        if memo_path is not None:
            with cache_lock(memo_path.parent / f".memo-lock-{memo_path.stem}") as writable:
                return self._embed_with_memo(texts, memo_path if writable else None)
        return self._embed_with_memo(texts, None)

    def _embed_with_memo(self, texts: list[str], memo_path: Path | None) -> list[list[float]]:
        import numpy as np

        keys = [hashlib.sha256(text.encode("utf-8")).hexdigest() for text in texts]
        known: dict[str, Any] = {}
        if memo_path is not None and memo_path.exists():
            try:
                with np.load(memo_path, allow_pickle=False) as data:
                    memo_keys, matrix = data["keys"].tolist(), data["vectors"]
                    if (json.loads(str(data["identity"].item())) != self._model_identity()
                        or matrix.ndim != 2 or matrix.dtype != np.float32
                        or len(memo_keys) != len(matrix) or len(set(memo_keys)) != len(memo_keys)
                        or not all(isinstance(key, str) and re.fullmatch(r"[0-9a-f]{64}", key) for key in memo_keys)
                        or not np.isfinite(matrix).all()
                        or str(data["mapping_sha256"].item()) != hashlib.sha256(json_bytes(memo_keys) + matrix.tobytes()).hexdigest()):
                        raise ValueError("Invalid vector memo")
                    known = dict(zip(memo_keys, matrix))
            except Exception as exc:  # noqa: BLE001 —— 坏了就当没有，全部重新嵌入
                log.warning("块向量缓存读不了，全部重新嵌入：%s", exc)
                known = {}

        todo: dict[str, str] = {}  # 同样的文字只嵌入一次（教材里有十几块完全相同）
        for key, text in zip(keys, texts):
            if key not in known and key not in todo:
                todo[key] = text
        if todo:
            fresh = self.embeddings.embed_documents(list(todo.values()))
            if len(fresh) != len(todo):
                raise ValueError("The embedding model returned an incomplete batch.")
            for key, vector in zip(todo, fresh):
                known[key] = np.asarray(vector, dtype=np.float32)
        log.info("向量：复用 %d 块，新嵌入 %d 块", len(set(keys)) - len(todo), len(todo))

        if memo_path is not None:
            self._save_vector_memo(memo_path, {key: known[key] for key in dict.fromkeys(keys)}, self._model_identity())
        return [np.asarray(known[key], dtype=np.float32).tolist() for key in keys]

    @staticmethod
    def _save_vector_memo(path: Path, vectors: dict[str, Any], identity: dict) -> None:
        """当前版本只留用到的块，原子更新；其他模型版本的文件不删除。"""
        import numpy as np

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            matrix = np.stack(list(vectors.values())).astype(np.float32)
            buffer = io.BytesIO()
            np.savez(buffer, keys=np.array(list(vectors)), vectors=matrix,
                     identity=json_bytes(identity).decode("utf-8"),
                     mapping_sha256=hashlib.sha256(json_bytes(list(vectors)) + matrix.tobytes()).hexdigest())
            atomic_write(path, buffer.getvalue())
        except Exception as exc:  # noqa: BLE001 —— 存不下只是下次还要重新嵌入
            log.warning("块向量缓存没存上：%s", exc)

    def chunks(self, notebook_ids: list[str] | None = None) -> list[Document]:
        if self._knowledge_chunks is not None:
            return self._knowledge_chunks
        with self._vector_lock:
            if self._knowledge_chunks is None:
                chunks = self._build_text_database(self.knowledge_file)
                papers = reference_documents(self.references_dir)
                self._reference_count = len({paper.metadata["file"] for paper in papers})
                if papers:
                    log.info("参考文献 %d 篇（%d 块）并入本地知识库", self._reference_count, len(papers))
                self._knowledge_chunks = chunks + papers
                digest = hashlib.sha256()
                digest.update(INDEX_CACHE_FORMAT.encode())
                digest.update(REFERENCE_CHUNK_FORMAT.encode())
                digest.update(self.knowledge_file.read_bytes())
                for path in reference_files(self.references_dir):
                    digest.update(b"\0" + path.name.encode("utf-8") + b"\0")
                    digest.update(path.read_bytes())
                self._source_sha256 = digest.hexdigest()
            return self._knowledge_chunks
    @staticmethod
    def _build_text_database(path: Path) -> list[Document]:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise RuntimeError("The local knowledge document is empty.")
        header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")]
        )
        sections = header_splitter.split_text(content)
        splitter = RecursiveCharacterTextSplitter(chunk_size=TEXTBOOK_CHUNK_SIZE, chunk_overlap=TEXTBOOK_CHUNK_OVERLAP)
        chunks = splitter.split_documents(sections)
        if not chunks:
            raise RuntimeError("The local knowledge document produced no searchable chunks.")
        # 答疑返回出处时要说是第几章第几页（app/rag/citations.py）
        annotate_book_locations(content, chunks)
        return chunks
    def sample_exam_pieces(
        self, topic: str | None = None, notebook_ids: list[str] | None = None
    ) -> list[tuple[str, str]]:
        """出卷取材：挑出的片段，以及每段来自哪里（textbook 教材 / reference 论文）。

        整卷的填空、选择只从非论文片段里分（app/agent/graphs/exam.py），所以来源要留着。
        """
        chunks = self.ensure_index()
        if topic:
            # 先捞一个**比最终要用的多**的候选池，再按来源配额挑回 EXAM_SAMPLE_K*2。
            # 候选数和挑的数量一样大时，配额就没有可挑的余地，等于没配额——
            # 这正是第一版接线踩的坑（单元测试测的是纯函数，照样全绿）。
            #
            # 多挑一倍备用的理由不变：论文的几个检索窗口会指向同一块，
            # 下面按内容去重时会少，才往后补。
            # lambda_mult 偏相关（默认 0.5 对短主题太散）。
            candidates = self.vectorstore.max_marginal_relevance_search_by_vector(
                self._embed_query(topic),
                k=EXAM_MMR_FETCH_K,
                fetch_k=EXAM_MMR_FETCH_K,
                lambda_mult=EXAM_MMR_LAMBDA,
            )
            documents = balance_by_source(
                candidates,
                EXAM_SAMPLE_K * 2,
                min_primary_share=EXAM_TEXTBOOK_MIN_SHARE,
            )
        else:
            groups: dict[tuple[Any, Any, Any], list[Document]] = {}
            for document in chunks:
                key = tuple(document.metadata.get(name) for name in ("h1", "h2", "h3"))
                groups.setdefault(key, []).append(document)
            if len(groups) <= 1:
                pool = list(chunks)
                random.shuffle(pool)
                documents = pool[: EXAM_SAMPLE_K * 2]
            else:
                buckets = [list(group) for group in groups.values()]
                random.shuffle(buckets)
                for bucket in buckets:
                    random.shuffle(bucket)
                documents = []
                while len(documents) < EXAM_SAMPLE_K:
                    progressed = False
                    for bucket in buckets:
                        if bucket:
                            documents.append(bucket.pop())
                            progressed = True
                            if len(documents) >= EXAM_SAMPLE_K:
                                break
                    if not progressed:
                        break

        seen: set[str] = set()
        pieces: list[tuple[str, str]] = []
        total = 0
        for document in documents:
            fingerprint = re.sub(r"\s+", "", document.page_content)[:120]
            if not fingerprint or fingerprint in seen:
                continue
            seen.add(fingerprint)
            remaining = EXAM_CONTEXT_CHAR_LIMIT - total
            if remaining <= 0:
                break
            content = document.page_content.strip()[:remaining]
            if content:
                pieces.append((content, str(document.metadata.get("source") or "")))
                total += len(content)
            if len(pieces) >= EXAM_SAMPLE_K:
                break
        return pieces


# ---- 出卷取材：按来源配额 ----
#
# 索引里教材只有几十块，论文按 200 字的检索窗口切，一篇就上百个窗口。
# 不控比例时，「排队论」这种短主题的候选池会被只沾边的论文片段占满，
# 出出来的题就全是「主路常数 m 值为多少」这类论文细节，而学生只读过教材。
PRIMARY_SOURCE = "textbook"


def balance_by_source(
    documents: list[Document],
    k: int,
    *,
    primary: str = PRIMARY_SOURCE,
    min_primary_share: float = 0.6,
) -> list[Document]:
    """按来源配额挑 k 块：教材至少占 min_primary_share，其余给论文/笔记本。

    三条都要守住：

    - **教材不够就让论文补满**。宁可比例失衡，也不能因为教材命中少就少给材料——
      少给材料等于少出题，比出偏题更糟。
    - **同一来源内部保持相关度顺序**。
    - **两类要交错着出**，不能先教材后论文、也不能照原始相关度排。
      调用方拿到结果之后还要再截一刀（EXAM_SAMPLE_K 块、EXAM_CONTEXT_CHAR_LIMIT 字），
      不交错的话被截掉的恰好是配额刚挑进来的那一类——第一版就是这么空转的：
      教材在候选池里排得靠后，配额挑中了，结果全被 EXAM_SAMPLE_K 截没了。
      交错之后任意前缀都大致满足配额，对下游怎么截都免疫。
    """
    if k <= 0 or not documents:
        return []

    primary_pool = [d for d in documents if d.metadata.get("source") == primary]
    other_pool = [d for d in documents if d.metadata.get("source") != primary]

    want_primary = min(len(primary_pool), math.ceil(k * min_primary_share - 1e-9))
    want_other = min(len(other_pool), k - want_primary)
    # 一边不够就让另一边补满
    want_primary = min(len(primary_pool), k - want_other)

    # 教材放在均匀分布的槽位上：第 j 块落在 floor(j * k / want_primary)
    slots = {(j * k) // want_primary for j in range(want_primary)} if want_primary else set()

    picked: list[Document] = []
    primary_iter, other_iter = iter(primary_pool), iter(other_pool)
    taken_primary = taken_other = 0
    for position in range(k):
        want_here = position in slots and taken_primary < want_primary
        if want_here or taken_other >= want_other:
            document = next(primary_iter, None)
            if document is not None:
                picked.append(document)
                taken_primary += 1
                continue
        document = next(other_iter, None)
        if document is not None:
            picked.append(document)
            taken_other += 1
    return picked


# 论文一块有好几个检索窗口：先多取几倍，再按「同一块只算一次」去重
_FETCH_FACTOR = 4


def _distinct(documents: list[Document], k: int) -> list[Document]:
    seen: set[str] = set()
    picked: list[Document] = []
    for document in documents:
        key = document.metadata.get("parent") or document.page_content
        if key in seen:
            continue
        seen.add(key)
        picked.append(document)
        if len(picked) >= k:
            break
    return picked


def display_document(document: Document) -> str:
    headings = [
        str(document.metadata.get(key, "")).strip()
        for key in ("h1", "h2", "h3")
        if document.metadata.get(key)
    ]
    heading = " / ".join(headings)
    content = clean_reference_for_display(document.page_content)
    return f"### {heading}\n\n{content}" if heading else content
def select_quiz_documents(chunks: list[Document], *, max_documents: int = 2) -> list[Document]:
    if not chunks:
        raise RuntimeError("The local knowledge document produced no searchable chunks.")
    return random.sample(chunks, min(max_documents, len(chunks)))
def join_quiz_context(documents: list[Document], *, max_chars: int = 1800) -> str:
    return _join_limited_sections(
        [clean_reference_for_display(document.page_content) for document in documents],
        max_chars=max_chars,
    )
def join_quiz_display(documents: list[Document], *, max_chars: int = 2200) -> str:
    return _join_limited_sections([display_document(document) for document in documents], max_chars=max_chars)
def _join_limited_sections(sections: list[str], *, max_chars: int) -> str:
    selected = []
    remaining = max_chars
    for section in sections:
        cleaned = section.strip()
        if not cleaned or remaining <= 0:
            continue
        if len(cleaned) > remaining:
            cleaned = truncate_markdown_fragment(cleaned, remaining)
        if not cleaned:
            continue
        selected.append(cleaned)
        remaining -= len(cleaned)
        if remaining > 0:
            remaining -= len("\n\n---\n\n")
    return "\n\n---\n\n".join(selected)
def first_heading(documents: list[Document]) -> str:
    for document in documents:
        for key in ("h3", "h2", "h1"):
            value = str(document.metadata.get(key, "")).strip()
            if value:
                return value
    return ""
