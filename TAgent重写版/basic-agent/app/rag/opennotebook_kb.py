"""OpenNotebook 知识库适配器。

只实现 service 会调用的几个方法：retrieve / search / chunks / sample_exam_pieces。
建向量索引是 OpenNotebook 自己的事，这里不落 FAISS。
"""

from __future__ import annotations

import ipaddress
import random
import threading
from typing import Any
from urllib.parse import urlsplit

import httpx
from langchain_core.documents import Document

from app.config import EXAM_CONTEXT_CHAR_LIMIT, EXAM_SAMPLE_K
from app.rag.knowledge_base import select_quiz_documents


class OpenNotebookError(RuntimeError):
    """调用 OpenNotebook 失败。"""


class OpenNotebookUnreachable(OpenNotebookError):
    """根本没连上 / 没等到回应（连接被拒、超时、断开）—— 不是它回了一个错误。

    分开是因为处理不同：它回了 400（比如没配嵌入模型），换文本检索再问一次有意义；
    连不上或卡住时再问一次只是再白等一个超时（实测卡住时一个问题要等 32 秒，就是这么来的）。
    """


# 健康检查只想知道「在不在」，不必等满检索用的 15 秒
PING_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


def _is_local_address(url: str) -> bool:
    """本机或局域网地址：这种地址绝不能交给代理。

    httpx 默认读系统代理：环境变量里没设代理时，macOS 上会去读「系统设置 → 网络 → 代理」。
    开着 Clash 之类的电脑，连 http://localhost:5055 也被送进代理，代理回 502——
    OpenNotebook 明明开着，健康检查却一直失败，笔记本检索整个用不上（2026-10-03 实测）。
    """
    host = (urlsplit(url).hostname or "").strip("[]").lower()
    if host in {"localhost", ""} or host.endswith(".local") or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


class OpenNotebookKnowledgeBase:
    def __init__(
        self,
        *,
        base_url: str,
        token: str = "",
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ):
        if not base_url:
            raise ValueError("OpenNotebook base_url is required.")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._client = client
        self._owns_client = client is None
        self._chunks: list[Document] | None = None
        self._lock = threading.RLock()

    def describe(self) -> dict[str, Any]:
        return {"kind": "notebook", "url": self.base_url}

    def warm_up(self) -> None:
        self.ping()

    def ensure_index(self) -> list[Document]:
        return self.chunks()

    def quiz_documents(self, *, max_documents: int = 2) -> list[Document]:
        return select_quiz_documents(self.chunks(), max_documents=max_documents)

    def ping(self) -> bool:
        last_error: Exception | None = None
        for path in ("/api/notebooks", "/api/config", "/health", "/api/health"):
            try:
                response = self._request("GET", path, timeout=PING_TIMEOUT)
                if response.status_code >= 400:
                    continue
                content_type = (response.headers.get("content-type") or "").lower()
                if "json" in content_type or response.text[:1] in "{[":
                    return True
            except OpenNotebookUnreachable as exc:
                # 连不上就是连不上，换个路径也一样：别把四条路径的超时挨个等一遍
                # （卡住的 OpenNotebook 会让 basic-agent 启动多等一分钟）
                raise OpenNotebookError(f"OpenNotebook 不可达：{exc}") from exc
            except Exception as exc:
                last_error = exc
        if last_error:
            raise OpenNotebookError(f"OpenNotebook 不可达：{last_error}") from last_error
        raise OpenNotebookError("OpenNotebook 健康检查失败。")

    def retrieve(self, query: str, notebook_ids: list[str] | None = None):
        documents = self._search_documents(query, limit=4, notebook_ids=notebook_ids)
        context = "\n\n---\n\n".join(document.page_content for document in documents)
        return context, documents

    def search(self, query: str, *, k: int = 3, notebook_ids: list[str] | None = None) -> list[Document]:
        return self._search_documents(query, limit=k, notebook_ids=notebook_ids)

    def chunks(self, notebook_ids: list[str] | None = None) -> list[Document]:
        scoped = _normalize_ids(notebook_ids)
        if scoped:
            documents = self._list_documents(notebook_ids=scoped)
            if not documents:
                raise OpenNotebookError("选中的笔记本没有可出题的笔记或来源。")
            return documents
        if self._chunks is not None:
            return self._chunks
        with self._lock:
            if self._chunks is None:
                documents = self._list_documents()
                if not documents:
                    raise OpenNotebookError("OpenNotebook 没有可出题的笔记或来源。")
                self._chunks = documents
            return self._chunks

    def sample_exam_pieces(
        self, topic: str | None = None, notebook_ids: list[str] | None = None
    ) -> list[tuple[str, str]]:
        """出卷取材的片段和来源。笔记本里的都是学生自己的材料，来源一律记 opennotebook。"""
        if topic:
            documents = self._search_documents(topic, limit=EXAM_SAMPLE_K, notebook_ids=notebook_ids)
        else:
            pool = list(self.chunks(notebook_ids=notebook_ids))
            random.shuffle(pool)
            documents = pool[:EXAM_SAMPLE_K]
        pieces: list[tuple[str, str]] = []
        total = 0
        for document in documents:
            remaining = EXAM_CONTEXT_CHAR_LIMIT - total
            if remaining <= 0:
                break
            content = document.page_content.strip()[:remaining]
            if content:
                pieces.append((content, "opennotebook"))
                total += len(content)
        return pieces

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _client_or_create(self) -> httpx.Client:
        if self._client is None:
            headers = {"Accept": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
                headers["X-Password"] = self.token
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                # 本机 / 局域网的 OpenNotebook 直连，不走系统代理（见 _is_local_address）
                trust_env=not _is_local_address(self.base_url),
                # 握手单独限时：地址不通时几秒就知道，不用等满整段读超时
                timeout=httpx.Timeout(self.timeout, connect=min(3.0, self.timeout)),
            )
        return self._client

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._client_or_create().request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise OpenNotebookUnreachable(f"调用 OpenNotebook {path} 失败：{exc}") from exc
        return response

    def _json(self, method: str, path: str, **kwargs) -> Any:
        response = self._request(method, path, **kwargs)
        if response.status_code >= 400:
            detail = response.text.strip()[:300] or response.reason_phrase
            raise OpenNotebookError(
                f"OpenNotebook {path} 返回 {response.status_code}：{detail}"
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise OpenNotebookError(f"OpenNotebook {path} 返回了非 JSON。") from exc

    def _search_documents(
        self, query: str, *, limit: int, notebook_ids: list[str] | None = None
    ) -> list[Document]:
        scoped = _normalize_ids(notebook_ids)
        members = self._membership(scoped) if scoped else None
        payload = self._search(query, limit=limit * 3 if members else limit)
        documents: list[Document] = []
        seen: set[str] = set()
        for hit in _as_list(payload):
            document = self._scoped_document(hit, members)
            if document is None or not document.page_content.strip():
                continue
            marker = str(document.metadata.get("id") or document.page_content[:40])
            if marker in seen:
                continue
            seen.add(marker)
            documents.append(document)
            if len(documents) >= limit:
                break
        if members is not None and len(documents) < limit:
            for document in self._documents_from_membership(members, query=query):
                marker = str(document.metadata.get("id") or document.page_content[:40])
                if marker in seen or not document.page_content.strip():
                    continue
                seen.add(marker)
                documents.append(document)
                if len(documents) >= limit:
                    break
        return documents

    def _search(self, query: str, *, limit: int) -> Any:
        body = {
            "query": query,
            "type": "vector",
            "limit": limit,
            "search_sources": True,
            "search_notes": True,
            "minimum_score": 0.2,
        }
        try:
            return self._json("POST", "/api/search", json=body)
        except OpenNotebookUnreachable:
            raise  # 没连上就别再问一遍文本检索（见 OpenNotebookUnreachable）
        except OpenNotebookError:
            body["type"] = "text"
            return self._json("POST", "/api/search", json=body)

    def _list_documents(self, notebook_ids: list[str] | None = None) -> list[Document]:
        documents: list[Document] = []
        names = self._notebook_names()
        for path, fallback_title, notebook_id in _list_paths(notebook_ids):
            try:
                payload = self._json("GET", path)
            except OpenNotebookError:
                continue
            info = {
                "notebook_id": notebook_id,
                "notebook_name": names.get(notebook_id, notebook_id),
            } if notebook_id else {}
            for item in _as_list(payload):
                document = self._hydrate(item, fallback_title=fallback_title)
                if info:
                    document.metadata.update(info)
                if document.page_content.strip():
                    documents.append(document)
        return documents

    def _membership(self, notebook_ids: list[str]) -> dict[str, dict[str, str]]:
        names = self._notebook_names()
        members: dict[str, dict[str, str]] = {}
        for notebook_id in notebook_ids:
            info = {
                "notebook_id": notebook_id,
                "notebook_name": names.get(notebook_id, notebook_id),
            }
            for path, _title, _nid in _list_paths([notebook_id]):
                try:
                    payload = self._json("GET", path)
                except OpenNotebookError:
                    continue
                for item in _as_list(payload):
                    if isinstance(item, dict) and item.get("id"):
                        members[str(item["id"])] = info
        return members

    def _notebook_names(self) -> dict[str, str]:
        try:
            payload = self._json("GET", "/api/notebooks")
        except OpenNotebookError:
            return {}
        names: dict[str, str] = {}
        for item in _as_list(payload):
            if isinstance(item, dict) and item.get("id"):
                names[str(item["id"])] = str(item.get("name") or item["id"])
        return names

    def _documents_from_membership(
        self, members: dict[str, dict[str, str]], *, query: str
    ) -> list[Document]:
        documents: list[Document] = []
        for item_id, info in members.items():
            path = f"/api/notes/{item_id}" if item_id.startswith("note:") else f"/api/sources/{item_id}"
            try:
                document = self._hydrate(self._json("GET", path))
            except OpenNotebookError:
                continue
            document.metadata.update(info)
            documents.append(document)
        query_text = (query or "").strip().lower()
        if query_text:
            documents.sort(
                key=lambda document: (
                    query_text not in document.page_content.lower()
                    and query_text not in str(document.metadata.get("h1", "")).lower(),
                    -len(document.page_content),
                )
            )
        return documents

    def _scoped_document(self, hit: Any, members: dict[str, dict[str, str]] | None) -> Document | None:
        document = self._hydrate(hit)
        if members is None:
            return document
        if not isinstance(hit, dict):
            return None
        ident = str(hit.get("id") or "")
        parent = str(hit.get("parent_id") or "")
        info = members.get(ident) or members.get(parent)
        if info is None:
            return None
        document.metadata.update(info)
        return document

    def _hydrate(self, hit: Any, *, fallback_title: str = "OpenNotebook") -> Document:
        document = _document_from_hit(hit, fallback_title=fallback_title)
        if document.page_content.strip() or not isinstance(hit, dict):
            return document
        ident = str(hit.get("id") or "")
        if ident.startswith("note:"):
            return _document_from_hit(self._json("GET", f"/api/notes/{ident}"), fallback_title=fallback_title)
        if ident.startswith("source:"):
            return _document_from_hit(self._json("GET", f"/api/sources/{ident}"), fallback_title=fallback_title)
        return document


def _as_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("results", "notes", "sources", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _document_from_hit(hit: Any, *, fallback_title: str = "OpenNotebook") -> Document:
    if isinstance(hit, str):
        return Document(
            page_content=hit.strip(),
            metadata={"h1": fallback_title, "source": "opennotebook"},
        )
    if not isinstance(hit, dict):
        return Document(page_content=str(hit), metadata={"h1": fallback_title, "source": "opennotebook"})
    text = ""
    for key in ("content", "full_text", "text", "snippet", "body", "page_content", "insight"):
        value = hit.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            break
    title = ""
    for key in ("title", "name", "heading", "id"):
        value = hit.get(key)
        if isinstance(value, str) and value.strip():
            title = value.strip()
            break
    ident = str(hit.get("id") or "")
    return Document(
        page_content=text,
        metadata={
            "id": ident,
            "h1": title or fallback_title,
            "h2": "",
            "h3": "",
            "source": "opennotebook",
            "notebook_id": str(hit.get("notebook_id") or ""),
            "notebook_name": str(hit.get("notebook_name") or ""),
        },
    )


def _normalize_ids(notebook_ids: list[str] | None) -> list[str]:
    if not notebook_ids:
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for item in notebook_ids:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _list_paths(notebook_ids: list[str] | None) -> list[tuple[str, str, str]]:
    scoped = _normalize_ids(notebook_ids)
    if not scoped:
        return [("/api/notes", "笔记", ""), ("/api/sources", "来源", "")]
    paths: list[tuple[str, str, str]] = []
    for notebook_id in scoped:
        encoded = notebook_id
        paths.append((f"/api/notes?notebook_id={encoded}", "笔记", notebook_id))
        paths.append((f"/api/sources?notebook_id={encoded}&limit=100", "来源", notebook_id))
    return paths
