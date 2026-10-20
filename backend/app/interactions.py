"""Read models for interactions, their extracted intents and assignments."""
from __future__ import annotations

import sqlite3

from . import assignments, db, events


def _labels(conn: sqlite3.Connection) -> dict[str, dict]:
    return {r["id"]: {"label": r["label"], "status": r["status"], "level": r["level"]}
            for r in conn.execute("SELECT id, label, status, level FROM taxonomy_nodes")}


def _assignment_dict(r: sqlite3.Row, labels: dict[str, dict]) -> dict:
    d = dict(r)
    for lvl in (1, 2, 3, 4):
        nid = d.get(f"l{lvl}_id")
        d[f"l{lvl}_label"] = labels.get(nid, {}).get("label") if nid else None
        d[f"l{lvl}_status"] = labels.get(nid, {}).get("status") if nid else None
    d["alternatives"] = [{**a, "label": labels.get(a.get("node_id"), {}).get("label")}
                         for a in db.loads(d.pop("alternatives_json", "[]"), [])]
    d["ai_original"] = db.loads(d.pop("ai_original_json", None))
    if d["ai_original"]:
        for lvl in (1, 2, 3, 4):
            nid = d["ai_original"].get(f"l{lvl}_id")
            d["ai_original"][f"l{lvl}_label"] = labels.get(nid, {}).get("label") if nid else None
    return d


def list_interactions(conn: sqlite3.Connection) -> list[dict]:
    labels = _labels(conn)
    by_inter: dict[int, list[dict]] = {}
    for r in conn.execute(
            "SELECT a.*, i.intent_text, i.evidence FROM assignments a JOIN intents i ON i.id=a.intent_id ORDER BY i.position"):
        by_inter.setdefault(r["interaction_id"], []).append(_assignment_dict(r, labels))
    out = []
    for r in conn.execute("SELECT id, conversation_id, seq, channel, segment, language, timestamp, queue, status, summary, "
                          "review_flag, review_unclassified, reviewer_notes, processed_order, batch_index, error "
                          "FROM interactions ORDER BY seq"):
        inter = dict(r)
        assigns = by_inter.get(r["id"], [])
        inter["assignments"] = [{k: a[k] for k in ("id", "intent_text", "l1_id", "l1_label", "l2_id", "l2_label",
                                                   "l3_id", "l3_label", "l4_id", "l4_label", "review_status",
                                                   "needs_review", "similarity", "method")} for a in assigns]
        inter["classification_status"] = assignments.classification_status(assigns, inter)
        inter["review_status"] = assignments.interaction_review_status(assigns, inter)
        out.append(inter)
    return out


def get_interaction(conn: sqlite3.Connection, interaction_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM interactions WHERE id=?", (interaction_id,)).fetchone()
    if not r:
        return None
    labels = _labels(conn)
    inter = dict(r)
    inter["turns"] = db.loads(inter.pop("turns_json"), [])
    inter["metadata"] = db.loads(inter.pop("metadata_json"), {})
    intents = []
    for it in conn.execute("SELECT * FROM intents WHERE interaction_id=? ORDER BY position", (interaction_id,)):
        a = conn.execute("SELECT * FROM assignments WHERE intent_id=?", (it["id"],)).fetchone()
        ad = _assignment_dict(a, labels) if a else None
        if ad:
            ad["history"] = assignments.history(conn, ad["id"])
        intents.append({**dict(it), "assignment": ad})
    inter["intents"] = intents
    assigns = [i["assignment"] for i in intents if i["assignment"]]
    inter["classification_status"] = assignments.classification_status(assigns, inter)
    inter["review_status"] = assignments.interaction_review_status(assigns, inter)
    inter["events"] = events.list_events(conn, conversation_id=inter["conversation_id"], limit=100)
    return inter


def set_interaction_review(conn: sqlite3.Connection, interaction_id: int, *, flag: bool | None = None,
                           unclassified: bool | None = None, notes: str | None = None) -> None:
    row = conn.execute("SELECT * FROM interactions WHERE id=?", (interaction_id,)).fetchone()
    if not row:
        raise ValueError("Interaction not found")
    if flag is not None:
        conn.execute("UPDATE interactions SET review_flag=? WHERE id=?", (int(flag), interaction_id))
    if unclassified is not None:
        conn.execute("UPDATE interactions SET review_unclassified=? WHERE id=?", (int(unclassified), interaction_id))
        if unclassified:
            for a in conn.execute("SELECT id FROM assignments WHERE interaction_id=?", (interaction_id,)).fetchall():
                assignments.review(conn, a["id"], "unclassify")
    if notes is not None:
        conn.execute("UPDATE interactions SET reviewer_notes=? WHERE id=?", (notes[:4000], interaction_id))
    events.emit(conn, "assignment_corrected", f"Interaction {row['conversation_id']} — review details updated",
                conversation_id=row["conversation_id"])
