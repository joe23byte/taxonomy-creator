"""Persisted analysis events and the Server-Sent Events stream.

Events are written to SQLite after the corresponding backend operation has been
committed. The SSE endpoint tails the events table, which makes the feed
replayable after a page refresh or server restart.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from typing import Any, AsyncIterator

from . import db

# Event kinds shown in the UI. Kept here as the single reference list.
KINDS = {
    "run_started", "run_paused", "run_stopped", "run_completed", "run_failed", "run_resumed",
    "interaction_started", "extracting", "intents_extracted", "no_intent", "embedding",
    "candidate_extracted", "matched_existing", "candidate_new", "cluster_forming",
    "interaction_assigned", "needs_review", "interaction_failed",
    "batch_refinement", "cluster_discovered", "category_proposed", "category_approved",
    "category_refined", "merge_proposed", "split_proposed", "proposal_accepted", "proposal_rejected",
    "assignment_corrected", "taxonomy_edited", "outlier_pass", "warning", "error", "info",
}


def emit(conn: sqlite3.Connection, kind: str, message: str, *, level: str = "info", run_id: int | None = None,
         conversation_id: str | None = None, node_id: str | None = None, data: dict[str, Any] | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO events(created_at, run_id, kind, level, conversation_id, node_id, message, data_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (db.utcnow(), run_id, kind, level, conversation_id, node_id, message[:500], db.dumps(data or {})),
    )
    return int(cur.lastrowid)


def row_to_event(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "created_at": r["created_at"],
        "run_id": r["run_id"],
        "kind": r["kind"],
        "level": r["level"],
        "conversation_id": r["conversation_id"],
        "node_id": r["node_id"],
        "message": r["message"],
        "data": db.loads(r["data_json"], {}),
    }


def list_events(conn: sqlite3.Connection, after_id: int = 0, limit: int = 200, kinds: list[str] | None = None,
                conversation_id: str | None = None, node_id: str | None = None, newest_first: bool = False) -> list[dict]:
    sql = "SELECT * FROM events WHERE id > ?"
    params: list[Any] = [after_id]
    if kinds:
        sql += f" AND kind IN ({','.join('?' * len(kinds))})"
        params += kinds
    if conversation_id:
        sql += " AND conversation_id = ?"
        params.append(conversation_id)
    if node_id:
        sql += " AND node_id = ?"
        params.append(node_id)
    sql += " ORDER BY id DESC LIMIT ?" if newest_first else " ORDER BY id ASC LIMIT ?"
    params.append(limit)
    return [row_to_event(r) for r in conn.execute(sql, params)]


async def stream(after_id: int, poll_interval: float = 0.4) -> AsyncIterator[str]:
    last = after_id
    idle = 0.0
    yield "retry: 2000\n\n"
    while True:
        rows = await asyncio.to_thread(_fetch, last)
        for ev in rows:
            last = ev["id"]
            yield f"id: {ev['id']}\nevent: analysis\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        if rows:
            idle = 0.0
        else:
            idle += poll_interval
            if idle >= 15:
                idle = 0.0
                yield ": keepalive\n\n"
        await asyncio.sleep(poll_interval)


def _fetch(after_id: int) -> list[dict]:
    with db.session() as conn:
        return list_events(conn, after_id=after_id, limit=500)
