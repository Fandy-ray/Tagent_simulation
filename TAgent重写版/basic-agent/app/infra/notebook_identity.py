"""The verified browser identity available to synchronous notebook retrieval."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class NotebookIdentity:
    cookie: str
    account_id: str
    csrf: str
    public_origin: str


_identity: ContextVar[NotebookIdentity | None] = ContextVar(
    "tagent_notebook_identity", default=None
)


def bind_notebook_identity(identity: NotebookIdentity) -> Token:
    return _identity.set(identity)


def current_notebook_identity() -> NotebookIdentity | None:
    return _identity.get()


def reset_notebook_identity(token: Token) -> None:
    _identity.reset(token)
