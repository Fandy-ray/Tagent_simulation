"""检索：文本（FTS5 + 中文切词，BM25）和向量（余弦），结果形状同原版 fn::text_search / fn::vector_search。

文本结果：{id, parent_id, title, relevance}
向量结果：{id, parent_id, title, similarity, matches}
来源的标题、分块命中都归到来源本身（id = parent_id = 来源 id），洞察命中 id 是洞察、parent_id 是来源，
笔记命中 id = parent_id = 笔记 id；每个条目取最高分，分数降序、编号升序。
"""

from __future__ import annotations

import re

from app.errors.notebook import InvalidInput, NotFound
from app.rag.notebook.embedder import Embedder
from app.rag.notebook.tokenize import match_expression, query_tokens
from app.rag.notebook.vectors import VectorCache, cosine_scores
from app.repository.notebook.database import Database
from app.repository.notebook.notebooks import NotebookRepository
from app.repository.notebook.search_index import NOTE_KINDS, SOURCE_KINDS, SearchIndexRepository

_NOTEBOOK_ID = re.compile(r"^notebook:[A-Za-z0-9_-]{1,64}$")
MAX_MATCHES = 10
CANDIDATE_FACTOR = 20
MAX_CANDIDATES = 5000


def _hit_key(kind: str, item_id: str, parent_id: str) -> tuple[str, str]:
    if kind in ("source_title", "source_chunk", "chunk"):
        return parent_id, parent_id
    return item_id, parent_id


class SearchService:
    def __init__(self, db: Database, notebooks: NotebookRepository, index: SearchIndexRepository,
                 embedder: Embedder, cache: VectorCache):
        self.db = db
        self.notebooks = notebooks
        self.index = index
        self.embedder = embedder
        self.cache = cache

    def resolve_scope(self, raw_ids: list[str] | None) -> list[str] | None:
        """同原版 resolve_notebook_scope：必须是 notebook:<key> 且存在。"""
        if not raw_ids:
            return None
        ids: list[str] = []
        for raw in raw_ids:
            value = (raw or "").strip()
            if not _NOTEBOOK_ID.match(value):
                raise InvalidInput(f"Invalid notebook id: {raw}")
            if value not in ids:
                ids.append(value)
        missing = set(ids) - self.notebooks.existing(ids)
        if missing:
            raise NotFound(f"Notebook not found: {sorted(missing)[0]}")
        return ids

    @staticmethod
    def _kinds(sources: bool, notes: bool) -> tuple[str, ...]:
        return (SOURCE_KINDS if sources else ()) + (NOTE_KINDS if notes else ())

    def text_hits(self, query: str, *, limit: int, sources: bool, notes: bool,
                  notebook_ids: list[str] | None) -> list[dict]:
        if not query or not query.strip():
            raise InvalidInput("Search query cannot be empty")
        tokens = query_tokens(query)
        if not tokens:
            return []
        return self.index.text_hits(
            match_expression(tokens), kinds=self._kinds(sources, notes), notebook_ids=notebook_ids,
            limit=min(MAX_CANDIDATES, max(limit * CANDIDATE_FACTOR, 200)),
        )

    def _titles(self, results: list[dict]) -> None:
        source_ids, note_ids, insight_ids = set(), set(), set()
        for item in results:
            if item["id"].startswith("source_insight:"):
                insight_ids.add(item["id"])
            elif item["id"].startswith("note:"):
                note_ids.add(item["id"])
            else:
                source_ids.add(item["id"])
        titles = self.index.titles(source_ids=source_ids, note_ids=note_ids, insight_ids=insight_ids)
        for item in results:
            item["title"] = titles.get(item["id"], "")

    def text_search(self, query: str, *, limit: int, sources: bool, notes: bool,
                    notebook_ids: list[str] | None) -> list[dict]:
        """相关度 = 这条内容命中了查询里多少比例的词（0~1），BM25 只用来在同分时排先后。

        只用 BM25 当分数的话，资料少的时候（一个笔记本就几份来源）SQLite 会把出现在大多数文档里的词
        的 IDF 压到 1e-6，界面上全显示 0.00；命中比例在任何规模下都看得懂。
        """
        tokens = set(query_tokens(query))
        best: dict[str, dict] = {}
        for hit in self.text_hits(query, limit=limit, sources=sources, notes=notes, notebook_ids=notebook_ids):
            key, parent = _hit_key(hit["kind"], hit["item_id"], hit["parent_id"])
            entry = best.setdefault(key, {"id": key, "parent_id": parent, "rows": []})
            entry["rows"].append((int(hit["rowid"]), float(hit["score"])))
        if not best:
            return []
        candidates = sorted(best.values(), key=lambda e: (-max(s for _, s in e["rows"]), e["id"]))[: max(limit * 3, 50)]
        row_tokens = self.index.row_tokens([rowid for e in candidates for rowid, _ in e["rows"][:8]])
        results = []
        for entry in candidates:
            coverage = max(
                (len(tokens & row_tokens.get(rowid, set())) / len(tokens) for rowid, _ in entry["rows"][:8]),
                default=0.0,
            )
            bm25 = max(score for _, score in entry["rows"])
            results.append(({"id": entry["id"], "parent_id": entry["parent_id"], "title": "",
                             "relevance": round(coverage, 4)}, bm25))
        results.sort(key=lambda pair: (-pair[0]["relevance"], -pair[1], pair[0]["id"]))
        ranked = [item for item, _ in results[:limit]]
        self._titles(ranked)
        return ranked

    def vector_ready(self) -> None:
        if not self.embedder.available():
            raise InvalidInput(f"Vector search requires an embedding model（{self.embedder.unavailable_reason()}）")

    def vector_search(self, query: str, *, limit: int, sources: bool, notes: bool, minimum_score: float,
                      notebook_ids: list[str] | None) -> list[dict]:
        if not query or not query.strip():
            raise InvalidInput("Search query cannot be empty")
        self.vector_ready()
        rows, matrix = self.cache.snapshot(self.db.vector_version, self.index.vector_rows)
        if not rows:
            return []
        query_vector = self.embedder.embed([query.strip()])[0]
        scores = cosine_scores(query_vector, matrix)
        if scores.size == 0:
            return []
        allowed_kinds = {"chunk", "insight"} if sources else set()
        if notes:
            allowed_kinds.add("note")
        members: set[str] | None = None
        if notebook_ids is not None:
            source_ids, note_ids = self.index.scope_members(notebook_ids)
            members = source_ids | note_ids
        best: dict[str, dict] = {}
        for position in scores.argsort()[::-1]:
            score = float(scores[position])
            if score < minimum_score:
                break
            row = rows[int(position)]
            if row.kind not in allowed_kinds or (members is not None and row.parent_id not in members):
                continue
            key, parent = _hit_key(row.kind, row.item_id, row.parent_id)
            item = best.get(key)
            if item is None:
                if len(best) >= limit:
                    continue
                item = best[key] = {"id": key, "parent_id": parent, "title": "", "similarity": score, "matches": []}
            if len(item["matches"]) < MAX_MATCHES:
                item["matches"].append(row.text)
        results = sorted(best.values(), key=lambda item: (-item["similarity"], item["id"]))
        self._titles(results)
        return results

    def search(self, *, query: str, kind: str, limit: int, sources: bool, notes: bool, minimum_score: float,
               raw_scope: list[str] | None) -> dict:
        notebook_ids = self.resolve_scope(raw_scope)
        if kind == "vector":
            results = self.vector_search(query, limit=limit, sources=sources, notes=notes,
                                         minimum_score=minimum_score, notebook_ids=notebook_ids)
        else:
            results = self.text_search(query, limit=limit, sources=sources, notes=notes, notebook_ids=notebook_ids)
        return {"results": results, "total_count": len(results), "search_type": kind}

    def retrieve(self, query: str, *, notebook_ids: list[str] | None, k: int = 6, max_chars: int = 3000) -> list[dict]:
        """给问答用：向量能用就用向量，不能用就用文本；回 [{id, title, text}]。"""
        if self.embedder.available():
            hits = self.vector_search(query, limit=k, sources=True, notes=True, minimum_score=0.2,
                                      notebook_ids=notebook_ids)
            return [
                {"id": hit["id"], "title": hit["title"], "text": "\n\n".join(hit["matches"])[:max_chars]}
                for hit in hits if hit["matches"]
            ]
        raw_hits = self.text_hits(query, limit=k, sources=True, notes=True, notebook_ids=notebook_ids)
        ranked = self.text_search(query, limit=k, sources=True, notes=True, notebook_ids=notebook_ids)
        wanted = {item["id"] for item in ranked}
        picked = [hit for hit in raw_hits if _hit_key(hit["kind"], hit["item_id"], hit["parent_id"])[0] in wanted]
        texts = self.index.hit_texts(picked[: k * 3], max_chars=max_chars)
        out = []
        for item in ranked:
            source_key = item["id"]
            text = texts.get(source_key) or texts.get(item["parent_id"], "")
            if text:
                out.append({"id": source_key, "title": item["title"], "text": text})
        return out
