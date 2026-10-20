"""Interaction ↔ intent ↔ category assignments, review actions and audit history."""
from __future__ import annotations

import sqlite3
from typing import Any

from . import db

SNAPSHOT_FIELDS = ("l1_id", "l2_id", "l3_id", "l4_id", "similarity", "method", "review_status",
                   "needs_review", "review_reason")
HUMAN_STATUSES = ("confirmed", "corrected", "unclassified")
REVIEW_STATUSES = ("pending", "confirmed", "corrected", "unclassified")


class AssignmentError(ValueError):
    pass


def snapshot(row: sqlite3.Row | dict) -> dict:
    return {k: row[k] for k in SNAPSHOT_FIELDS}


def _history(conn: sqlite3.Connection, assignment_id: int, actor: str, action: str, before: dict | None,
             after: dict | None) -> None:
    conn.execute(
        "INSERT INTO assignment_history(assignment_id, created_at, actor, action, before_json, after_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (assignment_id, db.utcnow(), actor, action, db.dumps(before) if before else None,
         db.dumps(after) if after else None),
    )


def path_for_node(conn: sqlite3.Connection, node_id: str | None) -> dict[str, str | None]:
    path: dict[str, str | None] = {"l1_id": None, "l2_id": None, "l3_id": None, "l4_id": None}
    seen = 0
    while node_id and seen < 6:
        row = conn.execute("SELECT id, level, parent_id FROM taxonomy_nodes WHERE id=?", (node_id,)).fetchone()
        if not row:
            break
        path[f"l{row['level']}_id"] = row["id"]
        node_id = row["parent_id"]
        seen += 1
    return path


def create(conn: sqlite3.Connection, *, intent_id: int, interaction_id: int, l2_id: str | None, method: str,
           needs_review: bool, review_reason: str | None, l4_id: str | None = None,
           similarity: float | None = None, alternatives: list | None = None) -> int:
    path = path_for_node(conn, l4_id or l2_id)
    values = {**path, "similarity": similarity, "method": method, "review_status": "pending",
              "needs_review": int(needs_review), "review_reason": review_reason}
    cur = conn.execute(
        "INSERT INTO assignments(intent_id, interaction_id, l1_id, l2_id, l3_id, l4_id, similarity, method, "
        "review_status, needs_review, review_reason, alternatives_json, ai_original_json, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (intent_id, interaction_id, values["l1_id"], values["l2_id"], values["l3_id"], values["l4_id"],
         similarity, method, "pending", int(needs_review), review_reason, db.dumps(alternatives or []),
         db.dumps(values), db.utcnow()),
    )
    aid = int(cur.lastrowid)
    _history(conn, aid, "ai", "created", None, values)
    return aid


def ai_assign(conn: sqlite3.Connection, assignment_id: int, *, l4_id: str | None, method: str,
              similarity: float | None = None, needs_review: bool = False, review_reason: str | None = None,
              alternatives: list | None = None, action: str = "assigned") -> bool:
    """Update an assignment on behalf of the AI. Human-reviewed assignments are never touched."""
    row = conn.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
    if not row or row["review_status"] in HUMAN_STATUSES:
        return False
    before = snapshot(row)
    if l4_id:
        path = path_for_node(conn, l4_id)
    else:
        path = {"l1_id": row["l1_id"], "l2_id": row["l2_id"], "l3_id": None, "l4_id": None}
    after = {**path, "similarity": similarity, "method": method, "review_status": "pending",
             "needs_review": int(needs_review), "review_reason": review_reason}
    sets = ", ".join(f"{k}=?" for k in after)
    params = list(after.values())
    if alternatives is not None:
        sets += ", alternatives_json=?"
        params.append(db.dumps(alternatives))
    conn.execute(f"UPDATE assignments SET {sets}, ai_original_json=?, updated_at=? WHERE id=?",
                 params + [db.dumps(after), db.utcnow(), assignment_id])
    _history(conn, assignment_id, "ai", action, before, after)
    return True


def repath(conn: sqlite3.Connection, assignment_id: int, actor: str, action: str) -> None:
    """Recompute L1–L3 from the assignment's L4 after a structural move (keeps review status)."""
    row = conn.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
    if not row or not row["l4_id"]:
        return
    path = path_for_node(conn, row["l4_id"])
    before = snapshot(row)
    if all(before[k] == path[k] for k in path):
        return
    conn.execute("UPDATE assignments SET l1_id=?, l2_id=?, l3_id=?, updated_at=? WHERE id=?",
                 (path["l1_id"], path["l2_id"], path["l3_id"], db.utcnow(), assignment_id))
    _history(conn, assignment_id, actor, action, before, {**before, **path})


def validate_path(conn: sqlite3.Connection, ids: dict[str, str | None]) -> dict[str, str | None]:
    """Ensure the chosen L1–L4 ids form a consistent active path; deepest id wins."""
    deepest = ids.get("l4_id") or ids.get("l3_id") or ids.get("l2_id") or ids.get("l1_id")
    if not deepest:
        return {"l1_id": None, "l2_id": None, "l3_id": None, "l4_id": None}
    node = conn.execute("SELECT * FROM taxonomy_nodes WHERE id=?", (deepest,)).fetchone()
    if not node:
        raise AssignmentError(f"Unknown category {deepest}")
    if node["status"] not in ("active",):
        raise AssignmentError(f"Category {deepest} is not active")
    path = path_for_node(conn, deepest)
    for k, v in ids.items():
        if v and path.get(k) != v:
            raise AssignmentError(f"{v} is not on the path of {deepest}")
    return path


def review(conn: sqlite3.Connection, assignment_id: int, action: str, *, path: dict | None = None,
           notes: str | None = None) -> dict:
    row = conn.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
    if not row:
        raise AssignmentError("Assignment not found")
    before = snapshot(row)
    updates: dict[str, Any] = {}
    if action == "confirm":
        if not row["l2_id"]:
            raise AssignmentError("Cannot confirm an assignment without at least an L1/L2 category")
        updates = {"review_status": "confirmed", "needs_review": 0}
    elif action == "correct":
        new_path = validate_path(conn, path or {})
        if not new_path["l2_id"]:
            raise AssignmentError("A correction needs at least an L2 category")
        updates = {**new_path, "review_status": "corrected", "needs_review": 0, "method": "manual",
                   "similarity": None}
    elif action == "unclassify":
        updates = {"review_status": "unclassified", "needs_review": 0}
    elif action == "flag":
        updates = {"needs_review": 1, "review_reason": "Flagged by reviewer"}
    elif action == "reset":
        updates = {"review_status": "pending"}
    elif action == "note":
        updates = {}
    else:
        raise AssignmentError(f"Unknown review action {action}")
    if notes is not None:
        updates["reviewer_notes"] = notes
    if updates:
        sets = ", ".join(f"{k}=?" for k in updates)
        conn.execute(f"UPDATE assignments SET {sets}, updated_at=? WHERE id=?",
                     list(updates.values()) + [db.utcnow(), assignment_id])
    new_row = conn.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
    after = snapshot(new_row)
    if notes is not None:
        after["reviewer_notes"] = notes
    _history(conn, assignment_id, "user", action, before, after)
    return dict(new_row)


def history(conn: sqlite3.Connection, assignment_id: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM assignment_history WHERE assignment_id=? ORDER BY id", (assignment_id,))
    return [{"id": r["id"], "created_at": r["created_at"], "actor": r["actor"], "action": r["action"],
             "before": db.loads(r["before_json"]), "after": db.loads(r["after_json"])} for r in rows]


def classification_status(assigns: list[dict], interaction: dict) -> str:
    if interaction["status"] == "failed":
        return "failed"
    if interaction["status"] in ("pending", "processing"):
        return "not_processed"
    active = [a for a in assigns if a["review_status"] != "unclassified"]
    if interaction.get("review_unclassified") or not active:
        return "unclassified"
    if all(a["l4_id"] for a in active):
        return "classified"
    if any(a["l2_id"] for a in active):
        return "partial"
    return "unclassified"


def interaction_review_status(assigns: list[dict], interaction: dict) -> str:
    if interaction.get("review_unclassified"):
        return "unclassified"
    if interaction.get("review_flag") or any(a["needs_review"] and a["review_status"] == "pending" for a in assigns):
        return "needs_review"
    if not assigns:
        return "pending" if interaction["status"] != "processed" else "needs_review"
    statuses = {a["review_status"] for a in assigns}
    if "pending" in statuses:
        return "pending"
    if "corrected" in statuses:
        return "corrected"
    if statuses == {"unclassified"}:
        return "unclassified"
    return "confirmed"
