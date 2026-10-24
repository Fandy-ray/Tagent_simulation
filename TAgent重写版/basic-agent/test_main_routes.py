import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


from app.container import Services
from app.factory import create_app
from app.repository.provider_repository import ModelProviderRegistry


class FakeAgentService:
    def __init__(self):
        self.exam_calls = []
        self.invalidated = []
        self.chat_calls = []
        self.topic_calls = []

    def answer(self, messages, provider, notebook_ids=None, *, mode="qa", retrieval_query=None, tuning=None):
        self.chat_calls.append({"mode": mode, "retrieval_query": retrieval_query})
        return {
            "content": f"answered by {provider.upstream_model}: {messages[-1]['content']}",
            "retrieved_context": "context",
            "step_log": ["retrieved", "answered"],
        }

    def stream_answer(
        self, messages, provider, notebook_ids=None, *, mode="qa", retrieval_query=None, tuning=None,
        on_citations=None,
    ):
        self.chat_calls.append({"mode": mode, "retrieval_query": retrieval_query})
        for token in ["real", " ", provider.upstream_model]:
            yield token

    def propose_topic(self, hint, provider, notebook_ids=None):
        self.topic_calls.append({"hint": hint, "notebook_ids": notebook_ids})
        return {
            "title": f"topic by {provider.upstream_model}",
            "requirements": ["a", "b"],
            "suggested_chars": 1000,
            "grounded": True,
        }

    def generate_quiz(self, provider, notebook_ids=None):
        return {
            "title": "Knowledge quiz",
            "question": f"quiz by {provider.upstream_model}",
            "reference_context": f"reference by {provider.upstream_model}",
            "reference_display": f"display reference by {provider.upstream_model}",
        }

    def review_quiz(self, question, user_answer, provider, reference_context=None):
        return {
            "is_correct": True,
            "score": 90,
            "comment": f"review by {provider.upstream_model}",
            "correct_answer": "answer",
            "reference_context": reference_context or "reference",
            "reference_display": reference_context or "reference",
        }

    def generate_exam(self, topic, provider, notebook_ids=None):
        self.exam_calls.append(("generate", topic, provider.served_model_id))
        return {
            "exam_id": "12345678-1234-5678-1234-567812345678",
            "title": "Dynamic exam",
            "total_points": 100,
            "cloze": [],
            "choice": [],
            "essay": [],
        }

    def review_exam(self, exam_id, answers, provider):
        self.exam_calls.append(("review", exam_id, provider.served_model_id))
        return {
            "exam_id": exam_id,
            "total_score": 0,
            "total_points": 100,
            "sections": {},
            "results": [],
            "overall_comment": "Done",
        }


    def invalidate(self, served_model_id=None):
        self.invalidated.append(served_model_id)


def fake_services(service=None) -> Services:
    """把一个全能替身同时挂到 chat/quiz/exam/essay 四个位置。

    拆分后 controller 各自取自己的 service，测试不必为此拆成三个替身。
    """
    service = service if service is not None else FakeAgentService()
    return Services(
        chat=service,
        quiz=service,
        exam=service,
        essay=service,
        knowledge_base=service,
        client_factory=service,
    )


def provider_payload(model_id, *, enabled=True, auth_mode="bearer"):
    return {
        "name": model_id,
        "served_model_id": model_id,
        "base_url": "http://127.0.0.1:9100/v1",
        "upstream_model": f"upstream-{model_id}",
        "auth_mode": auth_mode,
        "api_key": "secret" if auth_mode == "bearer" else "",
        "enabled": enabled,
    }


class MainRoutesTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix=".test-main-routes-", dir=Path(__file__).resolve().parent
        )
        self.registry = ModelProviderRegistry(Path(self.temp_dir.name) / "providers.json")
        self.registry.create_provider(provider_payload("teacher-default"))
        self.registry.create_provider(provider_payload("teacher-second"))
        self.registry.create_provider(provider_payload("teacher-disabled", enabled=False))
        self.app = create_app(
            {
                "TESTING": True,
                "AGENT_ADMIN_TOKEN": "admin-token",
                "AGENT_INTERNAL_TOKEN": "internal-token",
                "MAX_CONTENT_LENGTH": 1024 * 1024,
            },
            registry=self.registry,
            services=fake_services(),
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_knowledge_status(self):
        status = self.client.get("/knowledge")
        self.assertEqual(status.status_code, 200)
        body = status.get_json()
        self.assertIn(body["source"], {"local", "notebook", "composite"})
        self.assertIn("knowledge_base", body)

    def test_health_and_models_are_stable_with_default_first(self):
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["status"], "ok")

        first = self.client.get("/v1/models").get_json()["data"]
        second = self.client.get("/v1/models").get_json()["data"]
        self.assertEqual([item["id"] for item in first], ["teacher-default", "teacher-second"])
        self.assertEqual(first[0]["created"], second[0]["created"])

    def test_production_app_warms_knowledge_base_before_serving_requests(self):
        """非 TESTING 启动必须预热知识库，且三个 service 共用同一个实例。"""

        class WarmableKnowledgeBase:
            def __init__(self, **_kwargs):
                self.warm_up_calls = 0

            def warm_up(self):
                self.warm_up_calls += 1

        created = []

        def make(**kwargs):
            kb = WarmableKnowledgeBase(**kwargs)
            created.append(kb)
            return kb

        with patch("app.rag.knowledge_base.KnowledgeBase", side_effect=make):
            app = create_app({"TESTING": False}, registry=self.registry)

        services = app.extensions["services"]
        self.assertEqual(len(created), 1, "三个 service 必须共用同一个 KnowledgeBase")
        self.assertEqual(created[0].warm_up_calls, 1)
        self.assertIs(services.knowledge_base, created[0])
        self.assertIs(services.chat.knowledge_base, created[0])
        self.assertIs(services.quiz.knowledge_base, created[0])
        self.assertIs(services.exam.knowledge_base, created[0])

    def test_chat_uses_requested_model_and_last_50_text_messages(self):
        messages = [{"role": "user", "content": f"message-{index}"} for index in range(60)]
        response = self.client.post(
            "/v1/chat/completions",
            json={"model": "teacher-second", "messages": messages},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["model"], "teacher-second")
        self.assertIn("upstream-teacher-second", body["choices"][0]["message"]["content"])

    def test_stream_is_incremental_openai_sse(self):
        response = self.client.post(
            "/v1/chat/completions",
            json={
                "model": "teacher-second",
                "stream": True,
                "messages": [{"role": "user", "content": "hello"}],
            },
            buffered=False,
        )
        chunks = [chunk.decode("utf-8") for chunk in response.response]
        self.assertGreaterEqual(len(chunks), 6)
        self.assertIn('"role": "assistant"', chunks[0])
        self.assertIn('"content": "real"', chunks[1])
        self.assertEqual(chunks[-1], "data: [DONE]\n\n")

    def test_stream_preserves_real_finish_reason(self):
        class LengthLimitedService(FakeAgentService):
            def stream_answer(self, messages, provider, notebook_ids=None, **_options):
                yield "partial", None
                yield "", "length"

        app = create_app(
            {"TESTING": True},
            registry=self.registry,
            services=fake_services(LengthLimitedService()),
        )
        response = app.test_client().post(
            "/v1/chat/completions",
            json={
                "model": "teacher-default",
                "stream": True,
                "messages": [{"role": "user", "content": "hello"}],
            },
            buffered=False,
        )
        frames = [chunk.decode("utf-8") for chunk in response.response]
        self.assertTrue(any('"finish_reason": "length"' in frame for frame in frames))

    def test_stream_failure_midway_tells_the_user_in_chinese(self):
        class BrokenService(FakeAgentService):
            def stream_answer(self, messages, provider, notebook_ids=None, **_options):
                yield "partial", None
                raise RuntimeError("upstream vanished")

        app = create_app({"TESTING": True}, registry=self.registry, services=fake_services(BrokenService()))
        response = app.test_client().post(
            "/v1/chat/completions",
            json={"model": "teacher-default", "stream": True, "messages": [{"role": "user", "content": "hi"}]},
            buffered=False,
        )
        text = "".join(chunk.decode("utf-8") for chunk in response.response)
        self.assertIn("回答中断", text)
        self.assertNotIn("ended unexpectedly", text)

    def test_chat_defaults_to_qa_mode(self):
        self.client.post(
            "/v1/chat/completions",
            json={"model": "teacher-default", "messages": [{"role": "user", "content": "hello"}]},
        )
        calls = self.app.extensions["services"].chat.chat_calls
        self.assertEqual(calls[-1], {"mode": "qa", "retrieval_query": None})

    def test_chat_forwards_paper_mode_and_retrieval_query(self):
        # 前端论文模式一直在发 mode；最后一条消息是几千字的任务 prompt，检索要用短检索词
        for stream in (False, True):
            response = self.client.post(
                "/v1/chat/completions",
                json={
                    "model": "teacher-default",
                    "stream": stream,
                    "mode": "paper",
                    "retrieval_query": "排队论 银行窗口",
                    "messages": [{"role": "user", "content": "很长的论文任务 prompt"}],
                },
                buffered=True,
            )
            self.assertEqual(response.status_code, 200)
            calls = self.app.extensions["services"].chat.chat_calls
            self.assertEqual(calls[-1], {"mode": "paper", "retrieval_query": "排队论 银行窗口"})

    def test_chat_rejects_an_unknown_mode(self):
        response = self.client.post(
            "/v1/chat/completions",
            json={
                "model": "teacher-default",
                "mode": "essay",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "invalid_mode")

    def test_essay_topic_route_passes_hint_and_notebooks(self):
        response = self.client.post(
            "/essay/topic",
            json={"model": "teacher-second", "topic": "银行窗口", "notebook_ids": ["nb-1"]},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["data"]["title"], "topic by upstream-teacher-second")
        calls = self.app.extensions["services"].essay.topic_calls
        self.assertEqual(calls[-1], {"hint": "银行窗口", "notebook_ids": ["nb-1"]})

    def test_essay_topic_hint_uses_the_exam_topic_length_limit(self):
        response = self.client.post(
            "/essay/topic", json={"model": "teacher-default", "topic": "排" * 101}
        )
        self.assertEqual(response.status_code, 422)

    def test_unknown_and_disabled_models_use_openai_error_shape(self):
        for model_id in ["unknown", "teacher-disabled"]:
            response = self.client.post(
                "/v1/chat/completions",
                json={"model": model_id, "messages": [{"role": "user", "content": "hello"}]},
            )
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.get_json()["error"]["code"], "model_not_found")

    def test_exam_routes_use_requested_model(self):
        generated = self.client.post(
            "/quiz/exam/generate",
            json={"topic": "queueing", "model": "teacher-second"},
        )
        self.assertEqual(generated.status_code, 200)
        exam_id = generated.get_json()["data"]["exam_id"]

        reviewed = self.client.post(
            "/quiz/exam/review",
            json={"exam_id": exam_id, "answers": {}, "model": "teacher-second"},
        )
        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(
            self.app.extensions["services"].exam.exam_calls,
            [
                ("generate", "queueing", "teacher-second"),
                ("review", exam_id, "teacher-second"),
            ],
        )

    def test_exam_review_maps_disabled_or_missing_model_to_gone(self):
        for model_id in ("teacher-disabled", "teacher-removed"):
            response = self.client.post(
                "/quiz/exam/review",
                json={
                    "exam_id": "12345678-1234-5678-1234-567812345678",
                    "answers": {},
                    "model": model_id,
                },
            )

            self.assertEqual(response.status_code, 410)
            self.assertEqual(response.get_json()["error"]["code"], "exam_gone")

    def test_internal_exam_route_uses_ephemeral_provider(self):
        response = self.client.post(
            "/internal/quiz/exam/generate",
            headers={"X-Agent-Internal-Token": "internal-token"},
            json={
                "provider": provider_payload("tagent-user:private"),
                "payload": {"topic": "simulation"},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.app.extensions["services"].exam.exam_calls[-1],
            ("generate", "simulation", "tagent-user:private"),
        )

    def test_request_limits_return_4xx(self):
        too_long = "x" * 20001
        response = self.client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": too_long}]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "message_too_long")

        oversized = json.dumps({"messages": [{"role": "user", "content": "x" * 1048576}]})
        response = self.client.post(
            "/v1/chat/completions",
            data=oversized,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.get_json()["error"]["code"], "request_too_large")

    def test_quiz_and_rag_route_by_model(self):
        rag = self.client.post(
            "/rag/query", json={"model": "teacher-second", "user_question": "question"}
        )
        quiz = self.client.post("/quiz/generate", json={"model": "teacher-second"})
        review = self.client.post(
            "/quiz/review",
            json={
                "model": "teacher-second",
                "question": "q",
                "user_answer": "a",
                "reference_context": "visible reference",
            },
        )
        self.assertEqual(rag.get_json()["model"], "teacher-second")
        self.assertIn("upstream-teacher-second", quiz.get_json()["data"]["question"])
        self.assertIn("upstream-teacher-second", quiz.get_json()["data"]["reference_context"])
        self.assertIn("upstream-teacher-second", quiz.get_json()["data"]["reference_display"])
        self.assertIn("upstream-teacher-second", review.get_json()["data"]["comment"])
        self.assertEqual(review.get_json()["data"]["reference_context"], "visible reference")

    def test_admin_contract_masks_key_and_maintains_default(self):
        headers = {"X-Agent-Admin-Token": "admin-token"}
        forbidden = self.client.get("/admin/model-providers")
        self.assertEqual(forbidden.status_code, 403)

        response = self.client.get("/admin/model-providers", headers=headers)
        provider = response.get_json()["providers"][0]
        self.assertTrue(provider["has_api_key"])
        self.assertNotIn("api_key", provider)

        disabled = self.client.put(
            "/admin/model-providers/teacher-default",
            headers=headers,
            json={"enabled": False, "api_key": ""},
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(self.registry.get_default_model_id(), "teacher-second")

    def test_unconfigured_admin_token_returns_503(self):
        app = create_app(
            {"TESTING": True, "AGENT_ADMIN_TOKEN": ""},
            registry=self.registry,
            services=fake_services(),
        )
        response = app.test_client().get("/admin/model-providers")
        self.assertEqual(response.status_code, 503)

    def test_internal_routes_require_service_token(self):
        payload = {
            "provider": provider_payload("private"),
            "payload": {"messages": [{"role": "user", "content": "hello"}]},
        }
        forbidden = self.client.post("/internal/v1/chat/completions", json=payload)
        self.assertEqual(forbidden.status_code, 403)

        allowed = self.client.post(
            "/internal/v1/chat/completions",
            headers={"X-Agent-Internal-Token": "internal-token"},
            json=payload,
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.get_json()["model"], "private")
        self.assertIn("upstream-private", allowed.get_json()["choices"][0]["message"]["content"])

    def test_unconfigured_internal_token_returns_503(self):
        app = create_app(
            {"TESTING": True, "AGENT_INTERNAL_TOKEN": ""},
            registry=self.registry,
            services=fake_services(),
        )
        response = app.test_client().post(
            "/internal/v1/chat/completions",
            json={
                "provider": provider_payload("private"),
                "payload": {"messages": [{"role": "user", "content": "hello"}]},
            },
        )
        self.assertEqual(response.status_code, 503)

    def test_internal_rag_quiz_review_and_cache_invalidation(self):
        headers = {"X-Agent-Internal-Token": "internal-token"}
        provider = provider_payload("private")
        rag = self.client.post(
            "/internal/rag/query",
            headers=headers,
            json={"provider": provider, "payload": {"user_question": "question"}},
        )
        quiz = self.client.post(
            "/internal/quiz/generate",
            headers=headers,
            json={"provider": provider, "payload": {}},
        )
        review = self.client.post(
            "/internal/quiz/review",
            headers=headers,
            json={
                "provider": provider,
                "payload": {"question": "q", "user_answer": "a"},
            },
        )
        self.assertEqual(rag.get_json()["model"], "private")
        self.assertIn("upstream-private", quiz.get_json()["data"]["question"])
        self.assertIn("upstream-private", quiz.get_json()["data"]["reference_context"])
        self.assertIn("upstream-private", quiz.get_json()["data"]["reference_display"])
        self.assertIn("upstream-private", review.get_json()["data"]["comment"])

        invalidated = self.client.post(
            "/internal/cache/invalidate",
            headers=headers,
            json={"model": "private"},
        )
        self.assertEqual(invalidated.status_code, 200)


if __name__ == "__main__":
    unittest.main()
