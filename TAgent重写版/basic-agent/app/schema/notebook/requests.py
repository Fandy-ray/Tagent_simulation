"""请求体：字段、默认值、上下限照原版 api/models.py，前端和 tagent 发来的 JSON 原样能用。

多出来的未知字段一律忽略（原版 pydantic 默认也是忽略）。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Body(BaseModel):
    model_config = ConfigDict(extra="ignore")


class NotebookCreate(_Body):
    name: str
    description: str = ""


class NotebookUpdate(_Body):
    name: str | None = None
    description: str | None = None
    archived: bool | None = None


class NoteCreate(_Body):
    title: str | None = None
    content: str
    note_type: str | None = "human"
    notebook_id: str | None = None


class NoteUpdate(_Body):
    title: str | None = None
    content: str | None = None
    note_type: str | None = None


class SourceJsonCreate(_Body):
    notebook_id: str | None = None
    notebooks: list[str] | None = Field(default=None, max_length=50)
    type: Literal["link", "upload", "text"]
    url: str | None = None
    file_path: str | None = None
    content: str | None = None
    title: str | None = None
    transformations: list[str] = Field(default_factory=list, max_length=50)
    embed: bool = False
    delete_source: bool = False
    async_processing: bool = False

    @model_validator(mode="after")
    def _one_notebook_field(self):
        if self.notebook_id and self.notebooks:
            raise ValueError("notebook_id 和 notebooks 不能同时给")
        return self


class SourceUpdate(_Body):
    title: str | None = None
    topics: list[str] | None = None


class SearchRequest(_Body):
    query: str
    type: Literal["text", "vector"] = "text"
    limit: int = Field(default=100, ge=1, le=1000)
    search_sources: bool = True
    search_notes: bool = True
    minimum_score: float = Field(default=0.2, ge=0, le=1)
    notebook_id: str | None = None
    notebook_ids: list[str] | None = Field(default=None, max_length=50)

    def scope(self) -> list[str] | None:
        ids = list(self.notebook_ids or [])
        if self.notebook_id:
            ids.append(self.notebook_id)
        return ids or None


class AskRequest(_Body):
    question: str
    strategy_model: str | None = None
    answer_model: str | None = None
    final_answer_model: str | None = None
    notebook_id: str | None = None
    notebook_ids: list[str] | None = Field(default=None, max_length=50)

    def scope(self) -> list[str] | None:
        ids = list(self.notebook_ids or [])
        if self.notebook_id:
            ids.append(self.notebook_id)
        return ids or None


class ChatSessionCreate(_Body):
    notebook_id: str
    title: str | None = None
    model_override: str | None = None


class SourceChatSessionCreate(_Body):
    source_id: str | None = None
    title: str | None = None
    model_override: str | None = None


class ChatSessionUpdate(_Body):
    title: str | None = None
    model_override: str | None = None


class ChatExecute(_Body):
    session_id: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
    model_override: str | None = None


class BuildContext(_Body):
    notebook_id: str
    context_config: dict[str, Any] | None = None


class SourceChatMessage(_Body):
    message: str
    model_override: str | None = None


class InsightCreate(_Body):
    transformation_id: str
    model_id: str | None = None


class SaveAsNote(_Body):
    notebook_id: str | None = None


class EmbedRequest(_Body):
    item_id: str
    item_type: Literal["source", "note"]
    async_processing: bool = False
