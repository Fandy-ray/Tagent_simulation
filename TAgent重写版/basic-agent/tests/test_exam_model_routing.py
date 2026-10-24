
import pytest

from app.infra import llm_json
from app.service.exam_service import ExamService
from app.schema.exam import (
    CHOICE_COUNT_RANGE,
    CLOZE_COUNT_RANGE,
    ESSAY_COUNT_RANGE,
    DraftChoiceQuestion,
    DraftClozeQuestion,
    DraftEssayQuestion,
    GeneratedExamDraft,
)
from app.errors.exam_errors import ModelMismatchError
from app.repository.exam_cache import ExamCache, LLMGate
from app.schema.provider import ModelProvider


def provider(model_id: str) -> ModelProvider:
    return ModelProvider(
        name=model_id,
        served_model_id=model_id,
        base_url="https://example.invalid/v1",
        upstream_model=f"upstream-{model_id}",
        auth_mode="bearer",
        api_key="test-key",
        temperature=0.1,
        created_at="2026-07-18T00:00:00Z",
        updated_at="2026-07-18T00:00:00Z",
    )


def draft() -> GeneratedExamDraft:
    return GeneratedExamDraft(
        title="动态模型试卷",
        cloze=[
            DraftClozeQuestion(cue=f"c{i}", text=f"句子 {i} ____", accept=["答案"], points=3)
            for i in range(CLOZE_COUNT_RANGE[0])
        ],
        choice=[
            DraftChoiceQuestion(
                question=f"选择题 {i}",
                options=["甲", "乙", "丙", "丁"],
                correct_index=0,
                points=5,
            )
            for i in range(CHOICE_COUNT_RANGE[0])
        ],
        essay=[
            DraftEssayQuestion(
                question=f"论述题 {i}",
                reference_answer="参考答案",
                rubric="评分要点",
                points=18,
            )
            for i in range(ESSAY_COUNT_RANGE[0])
        ],
    )


class FakeClient:
    def bind(self, **_kwargs):
        return self


class RecordingFactory:
    def __init__(self):
        self.calls = []

    def get(self, selected, **kwargs):
        self.calls.append((selected.served_model_id, kwargs))
        return FakeClient()


class FakeKnowledgeBase:
    """只提供 ExamService 真正用到的那一个方法，不碰嵌入模型。"""

    def sample_exam_pieces(self, topic=None, notebook_ids=None):
        return [("教材内容", "textbook")]


def simulator() -> ExamService:
    # 拆分后可以走真正的构造函数，不必再 object.__new__ 绕过 __init__
    return ExamService(
        FakeKnowledgeBase(),
        RecordingFactory(),
        exam_cache=ExamCache(),
        llm_gate=LLMGate(max_concurrent=2),
    )


def test_exam_generation_uses_selected_provider_and_locks_model(monkeypatch):
    sim = simulator()
    monkeypatch.setattr(llm_json, "call_json_llm", lambda *_args, **_kwargs: draft())

    public_exam = sim.generate_exam("主题", provider("model-a"))

    assert public_exam.title == "动态模型试卷"
    assert sim.client_factory.calls[0][0] == "model-a"
    stored = sim.exam_cache.get_copy(public_exam.exam_id)
    assert stored.served_model_id == "model-a"
    assert not hasattr(stored, "api_key")


def test_exam_review_rejects_a_different_model_before_grading(monkeypatch):
    sim = simulator()
    monkeypatch.setattr(llm_json, "call_json_llm", lambda *_args, **_kwargs: draft())
    public_exam = sim.generate_exam(None, provider("model-a"))

    with pytest.raises(ModelMismatchError) as exc_info:
        sim.review_exam(public_exam.exam_id, {}, provider("model-b"))

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "exam_model_mismatch"
