import concurrent.futures
import time
import unittest


from langchain_core.documents import Document

from app import config
from app.rag.knowledge_base import (
    KnowledgeBase,
    join_quiz_context,
    join_quiz_display,
    select_quiz_documents,
)
from app.schema.provider import ModelProvider
from app.service import quiz_service as quiz_service_module
from app.service.chat_service import ChatService
from app.service.quiz_service import QuizService
from app.util.markdown_sanitizer import clean_generated_markdown, clean_reference_for_display


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    def __init__(self, model):
        self.model = model

    def invoke(self, messages):
        question = messages[-1]["content"]
        return FakeResponse(f"{self.model}:{question}")

    def stream(self, _messages):
        # 和真实的 ChatOpenAI 一样：流正常结束时最后一块带 finish_reason。
        # 没有它就是流被截断了，服务端会补一句「回答中断」（见 tests/test_chat_mode.py）。
        yield FakeResponse(self.model)
        final = FakeResponse("-stream")
        final.response_metadata = {"finish_reason": "stop"}
        yield final


class FakeClientFactory:
    def get(self, provider, **_kwargs):
        return FakeLLM(provider.upstream_model)

    def invalidate(self, _model_id):
        return None


class FakeExamVectorStore:
    def __init__(self, documents):
        self.documents = documents
        self.calls = []

    def max_marginal_relevance_search_by_vector(self, embedding, *, k, fetch_k, lambda_mult=0.5):
        self.calls.append((embedding, k, fetch_k, lambda_mult))
        return self.documents


class TextEmbeddings:
    """检索词原样「嵌入」成 [文本]，好核对送去检索的是哪一句。"""

    def embed_query(self, text):
        return [text]


class InMemoryKnowledgeBase:
    """检索直接返回可预期的字符串，不建索引。"""

    def retrieve(self, query, notebook_ids=None):
        return f"context-for-{query}", [f"document-for-{query}"]


class QuizKnowledgeBase:
    """出题只该用切块，绝不该触发建向量库。"""

    def ensure_index(self):
        raise AssertionError("quiz generation should not build the vector store")

    def chunks(self, notebook_ids=None):
        return [
            Document(
                page_content="HLA对象用于描述仿真系统中的实体、属性和交互。",
                metadata={"h2": "HLA对象概念"},
            )
        ]


class TimeoutLLM:
    def invoke(self, _messages):
        raise TimeoutError("timed out")


class TimeoutClientFactory:
    def __init__(self):
        self.timeout_seconds = None
        self.max_retries = None

    def get(self, _provider, **kwargs):
        self.timeout_seconds = kwargs.get("timeout_seconds")
        self.max_retries = kwargs.get("max_retries")
        return TimeoutLLM()

    def invalidate(self, _model_id):
        return None


class SlowLLM:
    def invoke(self, _messages):
        time.sleep(0.2)
        return FakeResponse('{"title":"slow","question":"slow"}')


class SlowClientFactory(TimeoutClientFactory):
    def get(self, _provider, **kwargs):
        self.timeout_seconds = kwargs.get("timeout_seconds")
        self.max_retries = kwargs.get("max_retries")
        return SlowLLM()


def provider(model_id):
    return ModelProvider(
        name=model_id,
        served_model_id=model_id,
        base_url="http://127.0.0.1:1/v1",
        upstream_model=f"upstream-{model_id}",
        auth_mode="none",
        api_key="",
        created_at="2026-07-10T00:00:00Z",
        updated_at="2026-07-10T00:00:00Z",
    )


class RAGConcurrencyTest(unittest.TestCase):
    def setUp(self):
        self.rag = ChatService(InMemoryKnowledgeBase(), FakeClientFactory())
        self.knowledge_base = KnowledgeBase()

    def test_parallel_requests_do_not_cross_provider_or_question_state(self):
        requests = [(provider(f"model-{index % 2}"), f"question-{index}") for index in range(20)]

        def run(item):
            selected, question = item
            result = self.rag.answer([{"role": "user", "content": question}], selected)
            return selected, question, result

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(run, requests))

        for selected, question, result in results:
            self.assertEqual(result["content"], f"{selected.upstream_model}:{question}")
            self.assertEqual(result["retrieved_context"], f"context-for-{question}")

    def test_stream_preserves_upstream_chunk_boundaries(self):
        chunks = list(
            self.rag.stream_answer(
                [{"role": "user", "content": "question"}],
                provider("model-a"),
            )
        )
        self.assertEqual(chunks, [("upstream-model-a", None), ("-stream", None), ("", "stop")])

    def test_exam_topic_sampling_uses_mmr_with_expected_candidate_pool(self):
        documents = [
            Document(page_content=f"topic-result-{index}", metadata={"h1": f"chapter-{index}"})
            for index in range(3)
        ]
        vectorstore = FakeExamVectorStore(documents)
        self.knowledge_base.vectorstore = vectorstore
        self.knowledge_base.embeddings = TextEmbeddings()
        self.knowledge_base._knowledge_chunks = [Document(page_content="fallback", metadata={"h1": "fallback"})]

        context = "\n".join(text for text, _ in self.knowledge_base.sample_exam_pieces("queueing theory"))

        # 先捞候选池，再按来源配额挑回 EXAM_SAMPLE_K*2 个；lambda 偏相关
        self.assertEqual(
            vectorstore.calls,
            [(["queueing theory"], config.EXAM_MMR_FETCH_K, config.EXAM_MMR_FETCH_K, config.EXAM_MMR_LAMBDA)],
        )
        # 候选池必须比要挑的多，配额才有挑的余地（第一版接线就栽在这里）
        self.assertGreater(config.EXAM_MMR_FETCH_K, config.EXAM_SAMPLE_K * 2)
        for index in range(3):
            self.assertIn(f"topic-result-{index}", context)
        self.assertNotIn("fallback", context)

    def test_exam_without_topic_round_robins_across_chapters(self):
        documents = [
            Document(page_content=f"chapter-content-{index}", metadata={"h1": f"chapter-{index}"})
            for index in range(config.EXAM_SAMPLE_K)
        ]
        self.knowledge_base.vectorstore = FakeExamVectorStore([])
        self.knowledge_base._knowledge_chunks = documents

        context = "\n".join(text for text, _ in self.knowledge_base.sample_exam_pieces())

        for index in range(config.EXAM_SAMPLE_K):
            self.assertIn(f"chapter-content-{index}", context)

    def test_reference_display_removes_orphan_numeric_table_rows(self):
        raw = (
            "| 1.0 | 0.608679 | 0.606531 | 0.606531 | -0.214833 | -0.022657 |\n\n"
            "> **说明**：\n\n"
            "| $x_n$ | $y_n$ | 精确解 |\n"
            "| 1.0 | 0.606531 | 0.606531 |"
        )
        cleaned = clean_reference_for_display(raw)
        self.assertNotIn("0.608679", cleaned.splitlines()[0])
        self.assertIn("> **说明**", cleaned)
        self.assertIn("| $x_n$ | $y_n$ | 精确解 |", cleaned)

    def test_reference_display_repairs_field_table_chunk_without_header(self):
        raw = (
            "### 核心表格：Manager.Federate 对象类\n\n"
            "| Lookahead | Time | 时间前瞻量 |\n"
            "| LBTS | Time | 时戳下限 |\n"
            "| MinNextEventTime | Time | 下一个事件的最小时间 |"
        )

        cleaned = clean_reference_for_display(raw)

        self.assertIn(
            "| 属性名 | 类型 | 描述 |\n| --- | --- | --- |\n| Lookahead | Time | 时间前瞻量 |",
            cleaned,
        )

    def test_reference_display_leaves_unrecognized_pipe_rows_unchanged(self):
        raw = "| option-a | enabled |\n| option-b | disabled |"

        cleaned = clean_reference_for_display(raw)

        self.assertEqual(cleaned, raw)

    def test_reference_display_preserves_complete_field_table(self):
        raw = (
            "| 属性名 | 类型 | 描述 |\n"
            "| --- | --- | --- |\n"
            "| Lookahead | Time | 时间前瞻量 |"
        )

        cleaned = clean_reference_for_display(raw)

        self.assertEqual(cleaned, raw)

    def test_reference_display_normalizes_inline_math_and_drops_incomplete_display_math(self):
        raw = (
            "Variables:\n"
            "- $ x $: count\n"
            "- $ \\lambda > 0 $: rate\n\n"
            "$$\n"
            "\\begin{cases}\n"
            "x = 1"
        )

        cleaned = clean_reference_for_display(raw)

        self.assertIn("$x$", cleaned)
        self.assertIn("$\\lambda > 0$", cleaned)
        self.assertNotIn("\\begin{cases}", cleaned)
        self.assertEqual(cleaned.count("$$") % 2, 0)

    def test_generated_markdown_wraps_bare_greek_latex_commands(self):
        raw = "parameter \\lambda and existing $\\eta_a$"

        cleaned = clean_generated_markdown(raw)

        self.assertIn("$\\lambda$", cleaned)
        self.assertIn("$\\eta_a$", cleaned)
        self.assertNotIn("$$\\eta_a$$", cleaned)

    def test_quiz_display_truncation_does_not_leave_broken_math(self):
        document = Document(
            page_content=("Safe paragraph.\n\n$$\n\\begin{cases}\n" + ("x" * 500)),
            metadata={"h2": "Math"},
        )

        display = join_quiz_display([document], max_chars=80)

        self.assertIn("Safe paragraph.", display)
        self.assertNotIn("\\begin{cases}", display)
        self.assertEqual(display.count("$$") % 2, 0)

    def test_quiz_context_is_bounded_for_slow_models(self):
        documents = [
            Document(page_content=f"chunk-{index}-" + ("内容" * 600), metadata={"h1": "章节"})
            for index in range(5)
        ]
        selected = select_quiz_documents(documents)
        context = join_quiz_context(selected)
        display = join_quiz_display(selected)

        self.assertLessEqual(len(selected), 2)
        self.assertLessEqual(len(context), 1800 + len("\n\n---\n\n"))
        self.assertLessEqual(len(display), 2200 + len("\n\n---\n\n"))
        self.assertIn("chunk-", context)

    def test_quiz_generation_falls_back_when_provider_times_out(self):
        client_factory = TimeoutClientFactory()
        rag = QuizService(QuizKnowledgeBase(), client_factory)
        result = rag.generate_quiz(provider("slow-model"))

        self.assertEqual(client_factory.timeout_seconds, quiz_service_module.QUIZ_GENERATION_TIMEOUT_SECONDS)
        self.assertEqual(client_factory.max_retries, 0)
        self.assertIn("HLA对象概念", result["title"])
        self.assertIn("根据参考内容", result["question"])
        self.assertIn("HLA对象", result["reference_context"])
        self.assertIn("HLA对象", result["reference_display"])

    def test_quiz_generation_future_timeout_returns_fallback_without_waiting_for_model(self):
        original_timeout = quiz_service_module.QUIZ_GENERATION_TIMEOUT_SECONDS
        quiz_service_module.QUIZ_GENERATION_TIMEOUT_SECONDS = 0.01
        try:
            client_factory = SlowClientFactory()
            rag = QuizService(QuizKnowledgeBase(), client_factory)
            started = time.monotonic()
            result = rag.generate_quiz(provider("slow-model"))
            elapsed = time.monotonic() - started
        finally:
            quiz_service_module.QUIZ_GENERATION_TIMEOUT_SECONDS = original_timeout

        self.assertLess(elapsed, 0.15)
        self.assertEqual(client_factory.timeout_seconds, 0.01)
        self.assertEqual(client_factory.max_retries, 0)
        self.assertIn("根据参考内容", result["question"])


if __name__ == "__main__":
    unittest.main()
