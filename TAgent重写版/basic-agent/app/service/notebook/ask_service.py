"""问答（检索页的 Ask）：定策略 → 每个检索词分头检索并回答 → 汇总。

流式事件同原版 /api/search/ask：strategy、answer、final_answer、complete、error，
每条是一行 `data: {json}` 加空行。参数校验在开始流式之前做完，出错直接回 400/404。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Iterator

from app.errors.notebook import InvalidInput, NotebookError
from app.infra.notebook.llm_client import LLMClient
from app.prompts.notebook.ask import ANSWER, FINAL, STRATEGY
from app.service.notebook.search_service import SearchService

log = logging.getLogger(__name__)

MAX_SEARCHES = 3
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def parse_strategy(raw: str, question: str) -> dict:
    fallback = {"reasoning": "直接用问题本身检索知识库。", "searches": [{"term": question, "instructions": question}]}
    match = _JSON_OBJECT.search(raw or "")
    if not match:
        return fallback
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return fallback
    searches = []
    for item in data.get("searches") or []:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        if term:
            searches.append({"term": term[:200], "instructions": str(item.get("instructions") or question)[:500]})
        if len(searches) >= MAX_SEARCHES:
            break
    if not searches:
        return fallback
    return {"reasoning": str(data.get("reasoning") or "")[:1000], "searches": searches}


def format_context(docs: list[dict]) -> str:
    return "\n\n".join(f"[{doc['id']}] {doc['title']}\n{doc['text']}" for doc in docs)


class AskService:
    def __init__(self, search: SearchService, llm: LLMClient):
        self.search = search
        self.llm = llm

    def _prepare(self, question: str, raw_scope: list[str] | None) -> tuple[str, list[str] | None]:
        question = (question or "").strip()
        if not question:
            raise InvalidInput("Question cannot be empty")
        return question, self.search.resolve_scope(raw_scope)

    def _steps(self, question: str, notebook_ids: list[str] | None) -> Iterator[dict]:
        strategy = parse_strategy(
            self.llm.complete([{"role": "user", "content": STRATEGY.format(question=question)}], temperature=0.2),
            question,
        )
        yield {"type": "strategy", **strategy}
        answers: list[str] = []
        found_any = False
        for search in strategy["searches"]:
            docs = self.search.retrieve(search["term"], notebook_ids=notebook_ids)
            if not docs:
                answer = f"资料里没有找到与「{search['term']}」相关的内容。"
            else:
                found_any = True
                answer = self.llm.complete([{
                    "role": "user",
                    "content": ANSWER.format(question=question, term=search["term"],
                                             instructions=search["instructions"], context=format_context(docs)),
                }])
            answers.append(f"## {search['term']}\n{answer}")
            yield {"type": "answer", "content": answer}
        if found_any:
            final = self.llm.complete(
                [{"role": "user", "content": FINAL.format(question=question, answers="\n\n".join(answers))}]
            )
        else:
            final = "知识库里没有找到和这个问题相关的资料。可以先在笔记本里添加来源，或换个说法再问。"
        yield {"type": "final_answer", "content": final}

    def stream(self, question: str, raw_scope: list[str] | None) -> Iterator[str]:
        question, notebook_ids = self._prepare(question, raw_scope)

        def generate() -> Iterator[str]:
            final = ""
            try:
                for event in self._steps(question, notebook_ids):
                    if event["type"] == "final_answer":
                        final = event["content"]
                    yield sse(event)
                yield sse({"type": "complete", "final_answer": final})
            except NotebookError as exc:
                yield sse({"type": "error", "message": exc.detail})
            except Exception:  # noqa: BLE001 - 流已经开始，只能以 error 事件告诉前端
                log.exception("问答出错")
                yield sse({"type": "error", "message": "问答时出错，请稍后重试"})

        return generate()

    def ask(self, question: str, raw_scope: list[str] | None) -> dict:
        question, notebook_ids = self._prepare(question, raw_scope)
        final = ""
        for event in self._steps(question, notebook_ids):
            if event["type"] == "final_answer":
                final = event["content"]
        return {"answer": final, "question": question}
