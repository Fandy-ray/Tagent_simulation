"""装配：配置 → 数据库与仓储 → 嵌入模型 / 模型客户端 → 后台任务 → 各个 service。

测试可以把 embedder、llm 换成假的传进来（见 tests/conftest.py）。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from app.config import NotebookSettings as Settings
from app.infra.notebook.llm_client import LLMClient
from app.rag.notebook.embedder import DisabledEmbedder, Embedder, LocalEmbedder
from app.rag.notebook.vectors import VectorCache
from app.repository.notebook.chats import ChatRepository
from app.repository.notebook.database import Database
from app.repository.notebook.jobs import JobRepository
from app.repository.notebook.notebooks import NotebookRepository
from app.repository.notebook.notes import NoteRepository
from app.repository.notebook.search_index import SearchIndexRepository
from app.repository.notebook.sources import SourceRepository
from app.service.notebook.ask_service import AskService
from app.service.notebook.chat_service import ChatService
from app.service.notebook.indexing import Indexer
from app.service.notebook.insight_service import InsightService
from app.service.notebook.jobs import JobRunner
from app.service.notebook.meta_service import MetaService
from app.service.notebook.note_service import NoteService
from app.service.notebook.notebook_service import NotebookService
from app.service.notebook.search_service import SearchService
from app.service.notebook.source_service import SourceService


@dataclass
class Services:
    settings: Settings
    db: Database
    jobs: JobRunner
    embedder: Embedder
    llm: LLMClient
    notebooks: NotebookService
    notes: NoteService
    sources: SourceService
    insights: InsightService
    search: SearchService
    ask: AskService
    chat: ChatService
    meta: MetaService

    def close(self) -> None:
        self.jobs.close()
        self.db.close()


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_mode == "off":
        return DisabledEmbedder()
    return LocalEmbedder(settings.embedding_model)


def build_services(settings: Settings, *, embedder: Embedder | None = None, llm: LLMClient | None = None,
                   warm_up: bool = True) -> Services:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.db_path)
    notebook_repo = NotebookRepository(db)
    source_repo = SourceRepository(db)
    note_repo = NoteRepository(db)
    chat_repo = ChatRepository(db)
    job_repo = JobRepository(db)
    index_repo = SearchIndexRepository(db)

    embedder = embedder or build_embedder(settings)
    llm = llm or LLMClient(settings.llm_base_url, api_key=settings.llm_api_key, model=settings.llm_model,
                           timeout=settings.llm_timeout)
    jobs = JobRunner(job_repo, workers=settings.job_workers)
    jobs.recover()

    indexer = Indexer(source_repo, note_repo, index_repo, embedder)
    insights = InsightService(source_repo, note_repo, notebook_repo, indexer, jobs, llm)
    search = SearchService(db, notebook_repo, index_repo, embedder, VectorCache())
    services = Services(
        settings=settings,
        db=db,
        jobs=jobs,
        embedder=embedder,
        llm=llm,
        notebooks=NotebookService(notebook_repo, source_repo, settings.upload_dir),
        notes=NoteService(note_repo, notebook_repo, indexer, jobs, llm),
        sources=SourceService(source_repo, notebook_repo, indexer, insights, jobs,
                              upload_dir=settings.upload_dir, allow_private_urls=settings.allow_private_urls),
        insights=insights,
        search=search,
        ask=AskService(search, llm),
        chat=ChatService(chat_repo, notebook_repo, source_repo, note_repo, llm),
        meta=MetaService(db, job_repo, llm, embedder, auth_enabled=bool(settings.password)),
    )
    if warm_up and settings.embedding_mode != "off":
        # 后台先把嵌入模型加载好，第一次检索不用等几秒；加载失败也只是记日志
        threading.Thread(target=embedder.available, name="embedder-warm-up", daemon=True).start()
    return services
