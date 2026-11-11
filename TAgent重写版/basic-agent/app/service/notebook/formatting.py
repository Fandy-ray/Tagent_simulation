"""把仓储的行整理成原版接口的响应形状（字段名、时间格式、空值都对齐 api/models.py）。"""

from __future__ import annotations

import pathlib

from app.util.notebook.timefmt import fmt


def notebook_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row.get("description") or "",
        "archived": bool(row.get("archived")),
        "created": fmt(row["created"]),
        "updated": fmt(row["updated"]),
        "source_count": int(row.get("source_count") or 0),
        "note_count": int(row.get("note_count") or 0),
    }


def note_out(row: dict, *, command_id: str | None = None) -> dict:
    return {
        "id": row["id"],
        "title": row.get("title"),
        "content": row.get("content"),
        "note_type": row.get("note_type"),
        "created": fmt(row["created"]),
        "updated": fmt(row["updated"]),
        "command_id": command_id,
    }


def _asset(row: dict) -> dict | None:
    if not row.get("asset_url") and not row.get("asset_file_path"):
        return None
    return {"file_path": row.get("asset_file_path"), "url": row.get("asset_url")}


def _file_available(row: dict, upload_dir: pathlib.Path) -> bool | None:
    path = row.get("asset_file_path")
    if not path:
        return None
    try:
        resolved = pathlib.Path(path).resolve()
        return resolved.is_relative_to(upload_dir.resolve()) and resolved.is_file()
    except OSError:
        return False


def processing_info(row: dict) -> dict | None:
    if not row.get("job_status"):
        return None
    error = row.get("job_error")
    return {
        "status": row["job_status"],
        "started_at": fmt(row.get("job_started_at")),
        "completed_at": fmt(row.get("job_completed_at")),
        "error": error[:200] if error else None,
    }


def source_list_out(row: dict, upload_dir: pathlib.Path) -> dict:
    embedded_chunks = int(row.get("embedded_chunks") or 0)
    return {
        "id": row["id"],
        "title": row.get("title"),
        "topics": row.get("topics") or [],
        "asset": _asset(row),
        "embedded": embedded_chunks > 0,
        "embedded_chunks": embedded_chunks,
        "insights_count": int(row.get("insights_count") or 0),
        "created": fmt(row["created"]),
        "updated": fmt(row["updated"]),
        "file_available": _file_available(row, upload_dir),
        "command_id": row.get("job_id"),
        "status": row.get("job_status"),
        "processing_info": processing_info(row),
    }


def source_out(row: dict, upload_dir: pathlib.Path) -> dict:
    data = source_list_out(row, upload_dir)
    data.pop("insights_count", None)
    data["full_text"] = row.get("full_text")
    data["notebooks"] = row.get("notebooks") or []
    return data


def insight_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "source_id": row["source_id"],
        "insight_type": row["insight_type"],
        "content": row["content"],
        "created": fmt(row.get("created")),
        "updated": fmt(row.get("updated")),
    }


def message_out(row: dict) -> dict:
    return {"id": row["id"], "type": row["role"], "content": row["content"], "timestamp": fmt(row.get("created"))}


def session_out(row: dict) -> dict:
    data = {
        "id": row["id"],
        "title": row.get("title") or "Untitled Session",
        "created": fmt(row["created"]),
        "updated": fmt(row["updated"]),
        "message_count": int(row.get("message_count") or 0),
        "model_override": row.get("model_override"),
    }
    data["source_id" if row.get("kind") == "source" else "notebook_id"] = row.get("target_id")
    return data
