"""几个仓储都要用的级联清理：删来源、删笔记时顺带清全文索引行和挂在它们身上的聊天会话。

都在调用方的事务里跑（传进来的是连接），不自己开事务。
"""

from __future__ import annotations

import sqlite3
from typing import Iterable, Iterator

_BATCH = 400


def batches(values: Iterable[str]) -> Iterator[list[str]]:
    batch: list[str] = []
    for value in values:
        batch.append(value)
        if len(batch) >= _BATCH:
            yield batch
            batch = []
    if batch:
        yield batch


def marks(values: list[str]) -> str:
    return ",".join("?" for _ in values)


def delete_fts(conn: sqlite3.Connection, *, item_ids: Iterable[str] = (), parent_ids: Iterable[str] = (),
               kinds: tuple[str, ...] = ()) -> None:
    kind_filter = f" AND kind IN ({marks(list(kinds))})" if kinds else ""
    for column, values in (("item_id", item_ids), ("parent_id", parent_ids)):
        for batch in batches(values):
            rowids = [
                row[0]
                for row in conn.execute(
                    f"SELECT rowid FROM fts_rows WHERE {column} IN ({marks(batch)}){kind_filter}",
                    [*batch, *kinds],
                )
            ]
            for ids in batches(str(r) for r in rowids):
                conn.execute(f"DELETE FROM search_fts WHERE rowid IN ({marks(ids)})", [int(i) for i in ids])
                conn.execute(f"DELETE FROM fts_rows WHERE rowid IN ({marks(ids)})", [int(i) for i in ids])


def purge_sources(conn: sqlite3.Connection, source_ids: list[str]) -> list[str]:
    """删来源（分块、洞察、笔记本关联靠外键级联），回被删来源的上传文件路径，文件由调用方删。"""
    paths: list[str] = []
    if not source_ids:
        return paths
    delete_fts(conn, parent_ids=source_ids)
    for batch in batches(source_ids):
        paths += [
            row[0]
            for row in conn.execute(
                f"SELECT asset_file_path FROM sources WHERE id IN ({marks(batch)}) AND asset_file_path IS NOT NULL",
                batch,
            )
        ]
        conn.execute(
            f"DELETE FROM chat_sessions WHERE kind = 'source' AND target_id IN ({marks(batch)})", batch
        )
        conn.execute(f"DELETE FROM sources WHERE id IN ({marks(batch)})", batch)
    return paths


def purge_notes(conn: sqlite3.Connection, note_ids: list[str]) -> None:
    if not note_ids:
        return
    delete_fts(conn, item_ids=note_ids)
    for batch in batches(note_ids):
        conn.execute(f"DELETE FROM notes WHERE id IN ({marks(batch)})", batch)
