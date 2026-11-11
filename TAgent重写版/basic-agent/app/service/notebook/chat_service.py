"""笔记本聊天（聊天栏，同步回整段对话）和来源聊天（来源详情，SSE）。

上下文规则同原版 build_notebook_context：每个来源的状态字符串里含 "not in" 就跳过、
含 "insights" 带标题+洞察、含 "full content" 带全文；笔记只有 "full content"。
不传配置时所有来源带标题+洞察、所有笔记带前 100 字。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterator

from app.errors.notebook import InvalidInput, NotebookError, NotFound
from app.infra.notebook.llm_client import LLMClient
from app.prompts.notebook.chat import NOTEBOOK_SYSTEM, SESSION_FALLBACK_CONTEXT, SOURCE_SYSTEM
from app.repository.notebook.chats import ChatRepository
from app.repository.notebook.notebooks import NotebookRepository
from app.repository.notebook.notes import NoteRepository
from app.repository.notebook.sources import SourceRepository
from app.service.notebook.ask_service import sse
from app.service.notebook.formatting import message_out, session_out
from app.service.notebook.notebook_service import notebook_id_or_404
from app.service.notebook.source_service import source_id_or_404
from app.util.notebook.ids import normalize

log = logging.getLogger(__name__)

HISTORY_LIMIT = 20
SOURCE_CONTEXT_CHARS = 12000
TOTAL_CONTEXT_CHARS = 80000
_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")


def estimate_tokens(text: str) -> int:
    """粗估 token：中日韩一字约一个，其余约四个字符一个（原版用 tiktoken，这里只拿来显示）。"""
    cjk = len(_CJK.findall(text))
    return cjk + max(0, len(text) - cjk) // 4


def render_context(context: dict[str, Any]) -> str:
    """把前端传来的 {sources: [...], notes: [...]} 拼成给模型看的文字，总长有上限。"""
    blocks: list[str] = []
    for source in context.get("sources") or []:
        if not isinstance(source, dict):
            continue
        lines = [f"[{source.get('id', '')}] {source.get('title') or '未命名来源'}"]
        for insight in source.get("insights") or []:
            if isinstance(insight, dict) and insight.get("content"):
                lines.append(f"## {insight.get('insight_type', '洞察')}\n{insight['content']}")
        if source.get("full_text"):
            lines.append(str(source["full_text"])[:SOURCE_CONTEXT_CHARS])
        blocks.append("\n".join(lines))
    for note in context.get("notes") or []:
        if isinstance(note, dict):
            blocks.append(f"[{note.get('id', '')}] {note.get('title') or '未命名笔记'}\n{note.get('content') or ''}")
    text = "\n\n---\n\n".join(blocks)
    return text[:TOTAL_CONTEXT_CHARS] if text else SESSION_FALLBACK_CONTEXT


def _history(rows: list[dict]) -> list[dict]:
    return [
        {"role": "user" if row["role"] == "human" else "assistant", "content": row["content"]}
        for row in rows[-HISTORY_LIMIT:]
    ]


def session_id_or_404(raw: str) -> str:
    session_id = normalize("chat_session", raw)
    if not session_id:
        raise NotFound("Session not found")
    return session_id


class ChatService:
    def __init__(self, chats: ChatRepository, notebooks: NotebookRepository, sources: SourceRepository,
                 notes: NoteRepository, llm: LLMClient):
        self.chats = chats
        self.notebooks = notebooks
        self.sources = sources
        self.notes = notes
        self.llm = llm

    # ---- 笔记本聊天 ----
    def _notebook(self, raw: str) -> str:
        notebook_id = notebook_id_or_404(raw)
        if not self.notebooks.get(notebook_id):
            raise NotFound("Notebook not found")
        return notebook_id

    def _session(self, raw: str, kind: str) -> dict:
        session = self.chats.get_session(session_id_or_404(raw))
        if not session or session["kind"] != kind:
            raise NotFound("Session not found")
        return session

    def list_sessions(self, raw_notebook: str) -> list[dict]:
        return [session_out(row) for row in self.chats.list_sessions("notebook", self._notebook(raw_notebook))]

    def create_session(self, raw_notebook: str, title: str | None, model_override: str | None) -> dict:
        notebook_id = self._notebook(raw_notebook)
        row = self.chats.create_session(
            kind="notebook", target_id=notebook_id, title=(title or "").strip()[:200] or "新对话",
            model_override=model_override,
        )
        return session_out(row)

    def get_session(self, raw_session: str) -> dict:
        session = self._session(raw_session, "notebook")
        messages = [message_out(row) for row in self.chats.messages(session["id"])]
        return {**session_out(session), "message_count": len(messages), "messages": messages}

    def update_session(self, raw_session: str, fields: dict, *, kind: str = "notebook") -> dict:
        session = self._session(raw_session, kind)
        if "title" in fields:
            if fields["title"] is None:
                fields.pop("title")
            else:
                fields["title"] = str(fields["title"]).strip()[:200] or session["title"]
        return session_out(self.chats.update_session(session["id"], fields) or session)

    def delete_session(self, raw_session: str, *, kind: str = "notebook") -> dict:
        session = self._session(raw_session, kind)
        self.chats.delete_session(session["id"])
        return {"success": True, "message": "Session deleted successfully"}

    def execute(self, raw_session: str, message: str, context: dict[str, Any]) -> dict:
        session = self._session(raw_session, "notebook")
        message = (message or "").strip()
        if not message:
            raise InvalidInput("Message cannot be empty")
        system = NOTEBOOK_SYSTEM.format(context=render_context(context or {}))
        history = _history(self.chats.messages(session["id"]))
        answer = self.llm.complete([{"role": "system", "content": system}, *history, {"role": "user", "content": message}])
        self.chats.append(session["id"], [("human", message), ("ai", answer)])
        return {"session_id": raw_session, "messages": [message_out(row) for row in self.chats.messages(session["id"])]}

    def build_context(self, raw_notebook: str, config: dict[str, Any] | None) -> dict:
        notebook_id = self._notebook(raw_notebook)
        data: dict[str, list] = {"sources": [], "notes": []}
        source_rows = self.sources.list(notebook_id=notebook_id, limit=100000, offset=0, sort_by="updated",
                                        descending=True)
        note_rows = self.notes.list(notebook_id)
        insights = self.sources.insights_for([row["id"] for row in source_rows])

        def source_block(source_id: str, title: str | None, full: bool) -> dict:
            block: dict[str, Any] = {
                "id": source_id, "title": title,
                "insights": [
                    {"id": i["id"], "insight_type": i["insight_type"], "content": i["content"]}
                    for i in insights.get(source_id, [])
                ],
            }
            if full:
                row = self.sources.get(source_id)
                block["full_text"] = (row or {}).get("full_text")
            return block

        if config:
            known_sources = {row["id"]: row for row in source_rows}
            for raw_id, status in (config.get("sources") or {}).items():
                source_id = normalize("source", str(raw_id))
                status = str(status or "")
                if not source_id or source_id not in known_sources or "not in" in status:
                    continue
                if "insights" in status:
                    data["sources"].append(source_block(source_id, known_sources[source_id].get("title"), False))
                elif "full content" in status:
                    data["sources"].append(source_block(source_id, known_sources[source_id].get("title"), True))
            known_notes = {row["id"]: row for row in note_rows}
            for raw_id, status in (config.get("notes") or {}).items():
                note_id = normalize("note", str(raw_id))
                status = str(status or "")
                if not note_id or note_id not in known_notes or "not in" in status:
                    continue
                if "full content" in status:
                    note = known_notes[note_id]
                    data["notes"].append({"id": note_id, "title": note.get("title"), "content": note.get("content")})
        else:
            for row in source_rows:
                data["sources"].append(source_block(row["id"], row.get("title"), False))
            for note in note_rows:
                content = note.get("content")
                data["notes"].append({"id": note["id"], "title": note.get("title"),
                                      "content": content[:100] if content else None})

        total = "".join(str(item) for item in data["sources"]) + "".join(str(item) for item in data["notes"])
        return {"context": data, "token_count": estimate_tokens(total) if total else 0, "char_count": len(total)}

    # ---- 来源聊天 ----
    def _source(self, raw: str) -> dict:
        row = self.sources.get(source_id_or_404(raw))
        if not row:
            raise NotFound("Source not found")
        return row

    def _source_session(self, raw_source: str, raw_session: str) -> tuple[dict, dict]:
        source = self._source(raw_source)
        session = self._session(raw_session, "source")
        if session["target_id"] != source["id"]:
            raise NotFound("Session not found for this source")
        return source, session

    def list_source_sessions(self, raw_source: str) -> list[dict]:
        source = self._source(raw_source)
        return [session_out(row) for row in self.chats.list_sessions("source", source["id"])]

    def create_source_session(self, raw_source: str, title: str | None, model_override: str | None) -> dict:
        source = self._source(raw_source)
        row = self.chats.create_session(
            kind="source", target_id=source["id"], title=(title or "").strip()[:200] or "新对话",
            model_override=model_override,
        )
        return session_out(row)

    def _source_context(self, source: dict) -> tuple[str, dict]:
        insights = self.sources.list_insights(source["id"])
        parts = [f"## {i['insight_type']}\n{i['content']}" for i in insights]
        parts.append((source.get("full_text") or "")[:TOTAL_CONTEXT_CHARS])
        indicators = {"sources": [source["id"]], "insights": [i["id"] for i in insights], "notes": []}
        return "\n\n".join(part for part in parts if part) or SESSION_FALLBACK_CONTEXT, indicators

    def get_source_session(self, raw_source: str, raw_session: str) -> dict:
        source, session = self._source_session(raw_source, raw_session)
        messages = [message_out(row) for row in self.chats.messages(session["id"])]
        _, indicators = self._source_context(source)
        return {**session_out(session), "message_count": len(messages), "messages": messages,
                "context_indicators": indicators if messages else None}

    def update_source_session(self, raw_source: str, raw_session: str, fields: dict) -> dict:
        self._source_session(raw_source, raw_session)
        return self.update_session(raw_session, fields, kind="source")

    def delete_source_session(self, raw_source: str, raw_session: str) -> dict:
        self._source_session(raw_source, raw_session)
        return self.delete_session(raw_session, kind="source")

    def source_message_stream(self, raw_source: str, raw_session: str, message: str) -> Iterator[str]:
        source, session = self._source_session(raw_source, raw_session)
        message = (message or "").strip()
        if not message:
            raise InvalidInput("Message cannot be empty")
        context, indicators = self._source_context(source)
        system = SOURCE_SYSTEM.format(title=source.get("title") or "未命名来源", context=context)
        history = _history(self.chats.messages(session["id"]))

        def generate() -> Iterator[str]:
            yield sse({"type": "user_message", "content": message, "timestamp": None})
            try:
                answer = self.llm.complete(
                    [{"role": "system", "content": system}, *history, {"role": "user", "content": message}]
                )
                added = self.chats.append(session["id"], [("human", message), ("ai", answer)])
                ai_id = added[-1]["id"] if added else None
                yield sse({"type": "ai_message", "content": answer, "id": ai_id, "timestamp": None})
                yield sse({"type": "context_indicators", "data": indicators})
                yield sse({"type": "complete"})
            except NotebookError as exc:
                yield sse({"type": "error", "message": exc.detail})
            except Exception:  # noqa: BLE001
                log.exception("来源聊天出错")
                yield sse({"type": "error", "message": "聊天时出错，请稍后重试"})

        return generate()
