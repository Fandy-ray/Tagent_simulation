"""杂项只读接口：配置、口令状态、设置、模型清单、任务状态。

模型和设置原版都能在界面上改；新版改成环境变量配置，这里只回只读的值，
够界面上的模型下拉框、添加来源对话框显示就行。
"""

from __future__ import annotations

from app.errors.notebook import NotFound
from app.infra.notebook.llm_client import LLMClient
from app.rag.notebook.embedder import Embedder
from app.repository.notebook.database import Database
from app.repository.notebook.jobs import JobRepository
from app.util.notebook.ids import normalize
from app.util.notebook.timefmt import fmt

VERSION = "1.15.0-lite"
LANGUAGE_MODEL_ID = "model:language"
EMBEDDING_MODEL_ID = "model:embedding"
_CREATED = "2026-11-11 00:00:00+00:00"

SETTINGS = {
    "default_content_processing_engine_doc": "auto",
    "default_content_processing_engine_url": "auto",
    "default_embedding_option": "ask",
    "auto_delete_files": "yes",
    "docling_ocr": False,
    "docling_formulas": False,
    "docling_vision": False,
    "youtube_preferred_languages": [],
}


class MetaService:
    def __init__(self, db: Database, jobs: JobRepository, llm: LLMClient, embedder: Embedder, *, auth_enabled: bool):
        self.db = db
        self.jobs = jobs
        self.llm = llm
        self.embedder = embedder
        self.auth_enabled = auth_enabled

    @property
    def embedding_enabled(self) -> bool:
        return bool(self.embedder.name)  # 关掉嵌入时用的 DisabledEmbedder 没有名字

    def config(self) -> dict:
        return {
            "version": VERSION,
            "latestVersion": None,
            "hasUpdate": False,
            "dbStatus": "online" if self.db.ping() else "offline",
        }

    def auth_status(self) -> dict:
        if self.auth_enabled:
            return {"auth_enabled": True, "message": "Authentication is required"}
        return {"auth_enabled": False, "message": "Authentication is disabled"}

    def settings(self) -> dict:
        return dict(SETTINGS)

    def models(self, model_type: str | None = None) -> list[dict]:
        items = [{
            "id": LANGUAGE_MODEL_ID, "name": self.llm.display_name, "provider": "openai-compatible",
            "type": "language", "credential": None, "created": _CREATED, "updated": _CREATED,
        }]
        if self.embedding_enabled:
            items.append({
                "id": EMBEDDING_MODEL_ID, "name": self.embedder.name, "provider": "sentence-transformers",
                "type": "embedding", "credential": None, "created": _CREATED, "updated": _CREATED,
            })
        if model_type:
            items = [item for item in items if item["type"] == model_type]
        return items

    def model(self, raw_id: str) -> dict:
        for item in self.models():
            if item["id"] == raw_id:
                return item
        raise NotFound("Model not found")

    def model_defaults(self) -> dict:
        return {
            "default_chat_model": LANGUAGE_MODEL_ID,
            "default_transformation_model": LANGUAGE_MODEL_ID,
            "large_context_model": LANGUAGE_MODEL_ID,
            "default_tools_model": LANGUAGE_MODEL_ID,
            "default_embedding_model": EMBEDDING_MODEL_ID if self.embedding_enabled else None,
            "default_text_to_speech_model": None,
            "default_speech_to_text_model": None,
        }

    def job(self, raw_id: str) -> dict:
        job_id = normalize("command", raw_id)
        job = self.jobs.get(job_id) if job_id else None
        if not job:
            raise NotFound("Command not found")
        return {
            "job_id": job["id"],
            "status": job["status"],
            "result": job.get("result"),
            "error_message": job.get("error"),
            "created": fmt(job.get("created")),
            "updated": fmt(job.get("updated")),
            "progress": None,
        }
