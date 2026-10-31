"""依赖装配。

工厂函数而不是 DI 框架：只有几个单例，上框架是负收益。
唯一的职责是"谁依赖谁"这件事写在一处，别散落在 create_app 里。

三个 service 共用同一个 KnowledgeBase 和同一个 ModelClientFactory：
嵌入模型 + FAISS 索引很贵，HTTP 连接池也需要统一失效，各建一份会出错。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import (
    ANSWER_GATE_MAX_WAITING,
    ANSWER_GATE_WAIT_SECONDS,
    LLM_GATE_MAX_WAITING,
    LLM_GATE_MIN_RUN_SECONDS,
    LLM_GATE_WAIT_SECONDS,
    AgentConfig,
)
from app.repository.provider_repository import load_model_registry


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Services:
    """一次请求可能用到的全部业务服务，外加它们共享的两个重资源。"""

    chat: "object"
    quiz: "object"
    exam: "object"
    essay: "object"
    knowledge_base: "object"
    client_factory: "object"
    # 学习记录库。None = 没开或没建成：记录直接跳过，答疑、批改照常。
    store: "object | None" = None

    def warm_up(self) -> None:
        """预热知识库。三个 service 共用它，热一次就够。

        预热失败不再把进程拉死：否则国内镜像 SSL 一断、或 OpenNotebook
        没开，basic-agent 会在 create_app 里直接退出，/health 永远探不到。
        检索/出题会在来源可用后于首次请求再试。
        """
        try:
            self.knowledge_base.warm_up()
        except Exception as exc:
            log.error("知识库预热失败，HTTP 服务仍会启动：%s", exc)

    def invalidate_provider(self, served_model_id: str | None) -> None:
        """provider 配置变了，丢掉缓存的上游客户端。"""
        self.client_factory.invalidate(served_model_id)

    def close(self) -> None:
        self.client_factory.close()
        if self.store is not None:
            self.store.close()


def build_registry(settings: AgentConfig):
    return load_model_registry(settings.model_providers_path)


def build_learning_store(settings: AgentConfig):
    """建学习记录库。建不成（目录不可写、磁盘满、文件损坏）只记日志、返回 None：

    记录是附加功能，不能因为它让整个服务起不来——和知识库预热失败不拉死进程是同一条。
    """
    if not settings.learning_store_enabled:
        log.info("学习记录库已关闭（LEARNING_STORE=0）")
        return None

    from app.config import (
        LEARNING_BACKUP_CHECK_SECONDS,
        LEARNING_BACKUP_EVERY_SECONDS,
        LEARNING_BUSY_TIMEOUT_MS,
    )
    from app.repository.learning_store import LearningStore

    path = settings.resolved_learning_db_path()
    try:
        store = LearningStore(
            path,
            busy_timeout_ms=LEARNING_BUSY_TIMEOUT_MS,
            backup_keep=settings.learning_backup_keep,
        )
        store.start_daily_backup(
            every_s=LEARNING_BACKUP_EVERY_SECONDS, check_s=LEARNING_BACKUP_CHECK_SECONDS
        )
    except Exception as exc:
        log.error("学习记录库打不开，本次运行不记录学习数据（服务照常）：%s —— %s", path, exc)
        return None
    log.info("学习记录库：%s（第 %s 版表结构）", path, store.schema_version)
    return store


def build_services(
    settings: AgentConfig, *, warm_up: bool = True, learning_store: bool = True
) -> Services:
    # 延迟 import：这几个模块会拉起 langchain/langgraph，
    # 只想构造 app 做单测时不该付这个代价。
    from app.errors.api_errors import AgentAPIError
    from app.infra.model_client_factory import ModelClientFactory
    from app.repository.exam_cache import ExamCache, LLMGate
    from app.repository.exam_persistence import ExamPersistence
    from app.service.chat_service import ChatService
    from app.service.essay_service import EssayService
    from app.service.exam_service import ExamService
    from app.service.quiz_service import QuizService

    knowledge_base = build_knowledge_base(settings)
    client_factory = ModelClientFactory()
    # 闸门**必须**由出卷判卷与论文批改共用：它计的是"这台机器同时压着多少次
    # 上游调用"，各建一份就等于把容量悄悄翻倍，限流也就名存实亡了。
    llm_gate = LLMGate(
        max_concurrent=settings.exam_max_concurrent_llm,
        wait_seconds=LLM_GATE_WAIT_SECONDS,
        max_waiting=LLM_GATE_MAX_WAITING,
        min_run_seconds=LLM_GATE_MIN_RUN_SECONDS,
    )
    store = build_learning_store(settings) if learning_store else None
    # 私有卷也落一份进学习记录库：重启后学生还能交卷（库没开就只在内存，和以前一样）
    exam_cache = ExamCache(persistence=ExamPersistence(store) if store is not None else None)

    # 答疑单独一道闸门（不和出卷判卷抢名额）：同时检索、生成的最多 answer_max_concurrent 个，其余在门口排队
    answer_gate = LLMGate(
        max_concurrent=settings.answer_max_concurrent,
        wait_seconds=ANSWER_GATE_WAIT_SECONDS,
        max_waiting=ANSWER_GATE_MAX_WAITING,
        busy_error=lambda message: AgentAPIError(message, 429, "answer_busy"),
        what="提问",
    )

    services = Services(
        chat=ChatService(knowledge_base, client_factory, answer_gate=answer_gate),
        quiz=QuizService(knowledge_base, client_factory),
        exam=ExamService(knowledge_base, client_factory, llm_gate=llm_gate, exam_cache=exam_cache),
        essay=EssayService(
            knowledge_base=knowledge_base,
            client_factory=client_factory,
            llm_gate=llm_gate,
        ),
        knowledge_base=knowledge_base,
        client_factory=client_factory,
        store=store,
    )
    if warm_up:
        services.warm_up()
    return services


def build_knowledge_base(settings: AgentConfig):
    """按配置装配知识来源。默认仍是本地教材，避免没开 OpenNotebook 时启动失败。"""
    from app.rag.knowledge_base import KnowledgeBase

    local = KnowledgeBase(
        text_db_dir=settings.text_db_dir,
        knowledge_file=settings.knowledge_file,
        index_cache_dir=settings.vector_cache_dir,
        references_dir=settings.references_dir,
        retrieval_cache_enabled=settings.retrieval_cache_enabled,
        retrieval_cache_max_entries=settings.retrieval_cache_max_entries,
        retrieval_cache_ttl_seconds=settings.retrieval_cache_ttl_seconds,
    )
    if settings.knowledge_source == "local":
        return local

    from app.rag.opennotebook_kb import OpenNotebookKnowledgeBase

    # notebook_url 已由 config.normalize_notebook_url 换算成接口基址（默认 5055）。
    log.info(
        "知识来源 = %s，OpenNotebook 接口基址 = %s",
        settings.knowledge_source,
        settings.notebook_url,
    )
    notebook = OpenNotebookKnowledgeBase(
        base_url=settings.notebook_url,
        token=settings.notebook_token,
    )
    if settings.knowledge_source == "notebook":
        return notebook

    from app.rag.composite_kb import CompositeKnowledgeBase

    return CompositeKnowledgeBase(local, notebook)
