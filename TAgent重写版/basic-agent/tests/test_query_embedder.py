"""检索词嵌入的凑批与缓存（app/rag/query_embedder.py）。全用假的「一批文本 → 一批向量」函数，不加载模型。"""

from __future__ import annotations

import threading
import time

import pytest

from app.rag.query_embedder import QueryEmbedder


class Recorder:
    """记下每一批算了哪些文本；gate 没放行之前第一批卡住，好让后到的排队。"""

    def __init__(self, *, block_first=False):
        self.batches: list[list[str]] = []
        self.gate = threading.Event()
        if not block_first:
            self.gate.set()
        self.entered = threading.Event()

    def __call__(self, texts):
        self.batches.append(list(texts))
        self.entered.set()
        self.gate.wait(5)
        return [[float(len(text)), float(sum(map(ord, text)) % 97)] for text in texts]


def expected(text):
    return [float(len(text)), float(sum(map(ord, text)) % 97)]


def run_concurrently(embedder, texts):
    results: dict[int, list[float]] = {}

    def call(index, text):
        results[index] = embedder.embed(text)

    threads = [threading.Thread(target=call, args=(index, text)) for index, text in enumerate(texts)]
    for thread in threads:
        thread.start()
    return threads, results


def test_a_lone_query_is_embedded_right_away_on_its_own():
    recorder = Recorder()
    embedder = QueryEmbedder(recorder)
    started = time.perf_counter()
    assert embedder.embed("排队论") == expected("排队论")
    assert recorder.batches == [["排队论"]]
    assert time.perf_counter() - started < 0.05, "没有并发时不该为了凑批等别人"


def test_queries_that_arrive_while_one_is_being_embedded_go_in_one_batch():
    recorder = Recorder(block_first=True)
    embedder = QueryEmbedder(recorder)
    first, first_results = run_concurrently(embedder, ["第一问"])
    assert recorder.entered.wait(2)
    texts = [f"问题{n}" for n in range(12)]
    others, results = run_concurrently(embedder, texts)
    time.sleep(0.05)  # 让它们都排进来
    recorder.gate.set()
    for thread in [*first, *others]:
        thread.join(5)

    assert recorder.batches[0] == ["第一问"]
    assert len(recorder.batches) == 2 and sorted(recorder.batches[1]) == sorted(texts)
    assert first_results[0] == expected("第一问")
    assert all(results[index] == expected(text) for index, text in enumerate(texts))


def test_the_same_query_arriving_together_is_embedded_once():
    recorder = Recorder(block_first=True)
    embedder = QueryEmbedder(recorder)
    first, _ = run_concurrently(embedder, ["占位"])
    assert recorder.entered.wait(2)
    threads, results = run_concurrently(embedder, ["什么是泊松过程？"] * 8)
    time.sleep(0.05)
    recorder.gate.set()
    for thread in [*first, *threads]:
        thread.join(5)

    assert recorder.batches[1] == ["什么是泊松过程？"]
    assert all(vector == expected("什么是泊松过程？") for vector in results.values()) and len(results) == 8


def test_a_batch_never_exceeds_the_limit():
    recorder = Recorder(block_first=True)
    embedder = QueryEmbedder(recorder, max_batch=5)
    first, _ = run_concurrently(embedder, ["占位"])
    assert recorder.entered.wait(2)
    threads, results = run_concurrently(embedder, [f"q{n}" for n in range(12)])
    time.sleep(0.05)
    recorder.gate.set()
    for thread in [*first, *threads]:
        thread.join(5)

    assert all(len(batch) <= 5 for batch in recorder.batches)
    assert sum(len(batch) for batch in recorder.batches) == 13 and len(results) == 12


def test_a_query_seen_before_comes_from_the_cache():
    recorder = Recorder()
    embedder = QueryEmbedder(recorder)
    embedder.embed("排队论")
    embedder.embed("排队论")
    assert recorder.batches == [["排队论"]]
    assert embedder.stats()["cached"] == 1


def test_the_cache_forgets_the_least_recently_used():
    recorder = Recorder()
    embedder = QueryEmbedder(recorder, cache_size=2)
    embedder.embed("a")
    embedder.embed("b")
    embedder.embed("a")  # a 刚用过
    embedder.embed("c")  # 挤掉 b
    embedder.embed("a")
    embedder.embed("b")
    assert recorder.batches == [["a"], ["b"], ["c"], ["b"]]


def test_a_failure_reaches_every_query_in_that_batch_and_is_not_cached():
    calls = []

    def flaky(texts):
        calls.append(list(texts))
        if len(calls) == 1:
            raise RuntimeError("模型还没加载好")
        return [[1.0] for _ in texts]

    embedder = QueryEmbedder(flaky)
    with pytest.raises(RuntimeError, match="没加载好"):
        embedder.embed("排队论")
    assert embedder.embed("排队论") == [1.0]
    assert len(calls) == 2


def test_a_wrong_number_of_vectors_is_an_error():
    embedder = QueryEmbedder(lambda texts: [])
    with pytest.raises(RuntimeError, match="0 个向量"):
        embedder.embed("排队论")


def test_many_threads_all_get_their_own_answers():
    recorder = Recorder()
    embedder = QueryEmbedder(recorder, max_batch=8)
    texts = [f"第{n}个问题" for n in range(200)]
    threads, results = run_concurrently(embedder, texts)
    for thread in threads:
        thread.join(10)
    assert len(results) == 200
    assert all(results[index] == expected(text) for index, text in enumerate(texts))
    assert sum(len(batch) for batch in recorder.batches) == 200


def test_queries_arriving_together_are_gathered_into_one_batch():
    """一下子同时到的（全班同时点发送）：领头的先等一小会儿，大家一批算，而不是第一个自己先算一批。"""
    recorder = Recorder()
    embedder = QueryEmbedder(recorder, gather_s=0.05)
    threads, results = run_concurrently(embedder, [f"同时{n}" for n in range(10)])
    for thread in threads:
        thread.join(5)
    assert len(recorder.batches) == 1 and len(recorder.batches[0]) == 10 and len(results) == 10


def test_the_model_is_kept_warm_while_people_are_asking_and_left_alone_after():
    recorder = Recorder()
    now = [0.0]
    embedder = QueryEmbedder(recorder, keep_warm_s=0.3, warm_interval_s=0.05, gather_s=0, clock=lambda: now[0])
    embedder.embed("排队论")
    time.sleep(0.2)
    warmed = embedder.stats()["warmups"]
    assert warmed >= 2 and all(batch == ["预热"] for batch in recorder.batches[1:])

    now[0] = 10.0  # 很久没人问了
    time.sleep(0.15)
    settled = embedder.stats()["warmups"]
    time.sleep(0.15)
    assert embedder.stats()["warmups"] == settled, "没人问了就不该再空算"
    assert not embedder._warmer.is_alive()

    embedder.embed("泊松过程")  # 又有人问：重新开始保持
    time.sleep(0.15)
    assert embedder.stats()["warmups"] > settled


def test_keeping_warm_never_runs_alongside_a_real_query():
    running = []
    overlaps = []
    lock = threading.Lock()

    def embed_batch(texts):
        with lock:
            if running:
                overlaps.append(texts)
            running.append(1)
        time.sleep(0.01)
        with lock:
            running.pop()
        return [[1.0] for _ in texts]

    embedder = QueryEmbedder(embed_batch, keep_warm_s=5, warm_interval_s=0.005, gather_s=0)
    threads, results = run_concurrently(embedder, [f"q{n}" for n in range(40)])
    for thread in threads:
        thread.join(5)
    time.sleep(0.05)
    assert overlaps == [] and len(results) == 40 and embedder.stats()["warmups"] > 0


def test_no_warming_thread_unless_asked_for():
    embedder = QueryEmbedder(Recorder())
    embedder.embed("排队论")
    assert embedder._warmer is None


def test_a_real_query_waits_for_a_warm_up_already_running():
    warm_started, release = threading.Event(), threading.Event()
    order = []

    def embed_batch(texts):
        if texts == ["预热"]:
            order.append("warm-start")
            warm_started.set()
            release.wait(2)
            order.append("warm-end")
        else:
            order.append("real")
        return [[1.0] for _ in texts]

    embedder = QueryEmbedder(embed_batch, keep_warm_s=5, warm_interval_s=0.01, gather_s=0)
    embedder.embed("第一问")
    assert warm_started.wait(2)
    second = threading.Thread(target=lambda: embedder.embed("第二问"))
    second.start()
    time.sleep(0.05)
    assert order.count("real") == 1, "空算还没完，真的检索不该同时算"
    release.set()
    second.join(2)
    assert order.index("warm-end") < len(order) - 1 - order[::-1].index("real")


def test_exclusive_work_waits_for_the_batch_in_progress_and_holds_queries_back():
    recorder = Recorder(block_first=True)
    embedder = QueryEmbedder(recorder, gather_s=0)
    first, _ = run_concurrently(embedder, ["第一问"])
    assert recorder.entered.wait(2)
    order = []
    worker = threading.Thread(target=lambda: embedder.run_exclusive(lambda: order.append("预热")))
    worker.start()
    time.sleep(0.05)
    assert order == [], "正在算的那批没完，独占的活不该开始"
    recorder.gate.set()
    worker.join(2)
    for thread in first:
        thread.join(2)
    assert order == ["预热"] and recorder.batches == [["第一问"]]
    assert embedder.embed("之后的检索") == expected("之后的检索")


# ====================== 知识库里的嵌入器：只建一个、形状预热只做一次 ======================
def _small_kb(tmp_path):
    from app.rag.knowledge_base import KnowledgeBase
    from langchain_core.embeddings import Embeddings

    class Hash(Embeddings):
        def embed_documents(self, texts):
            return [self.embed_query(t) for t in texts]

        def embed_query(self, text):
            return [float((sum(map(ord, text)) * (i + 3)) % 97) / 97.0 for i in range(8)]

    book = tmp_path / "book.md"
    book.write_text("# 排队论\n\n到达率与服务率。\n", encoding="utf-8")
    return KnowledgeBase(knowledge_file=book, embeddings=Hash(), index_cache_dir=tmp_path / "cache",
                         embedding_revision="test-embedding-v1")


def test_concurrent_first_queries_share_one_embedder(tmp_path, monkeypatch):
    from app.rag import knowledge_base as module

    kb = _small_kb(tmp_path)
    real = module._query_embedder_for

    def slow(embeddings):
        time.sleep(0.05)  # 把「各建一个」的窗口拉大
        return real(embeddings)

    monkeypatch.setattr(module, "_query_embedder_for", slow)
    seen = []
    threads = [threading.Thread(target=lambda: seen.append(kb._current_query_embedder())) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert len(seen) == 8 and len({id(embedder) for embedder in seen}) == 1


def _hf_embeddings(device_type):
    """类名和 HuggingFaceEmbeddings 一样的假嵌入，只带 _query_embedder_for 要看的那几样"""

    class Device:
        type = device_type

    class Client:
        device = Device()

    class HuggingFaceEmbeddings:
        encode_kwargs: dict = {}
        query_encode_kwargs: dict = {}
        _client = Client()

        def embed_documents(self, texts):
            return [[1.0] for _ in texts]

    return HuggingFaceEmbeddings()


def test_the_model_is_kept_warm_on_a_gpu_only(monkeypatch):
    from app.rag import knowledge_base as module

    # 在 CPU 上隔多久再算都一样快，空算只是白占 CPU
    assert module._query_embedder_for(_hf_embeddings("cpu")).keep_warm_s == 0
    monkeypatch.setattr(module, "_FixedShapeQueries", lambda client: (lambda texts: [[1.0] for _ in texts]))
    for device in ("mps", "cuda"):
        assert module._query_embedder_for(_hf_embeddings(device)).keep_warm_s == module.QUERY_KEEP_WARM_SECONDS


def test_shape_prewarm_runs_once_and_through_the_queue(tmp_path, monkeypatch):
    from app.rag import knowledge_base as module

    calls = []

    class Shapes:
        def __call__(self, texts):
            return [[1.0] for _ in texts]

        def prewarm(self, *, max_batch=16, max_length=64, run=None):
            calls.append((max_batch, run is not None))

    monkeypatch.setattr(module, "_query_embedder_for", lambda embeddings: QueryEmbedder(Shapes()))
    kb = _small_kb(tmp_path)
    kb.warm_up()
    kb.warm_up()  # 组合知识库里这个来源出错恢复时会再调一次
    time.sleep(0.1)  # 等后台那一轮
    assert sorted(calls) == [(16, True), (32, True)]
