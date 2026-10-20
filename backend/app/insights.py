"""Progress metrics, discovery curve and per-batch statistics."""
from __future__ import annotations

import sqlite3

from . import assignments, interactions, taxonomy


def summary(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
    by_status = {r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM interactions GROUP BY status")}
    l3 = conn.execute("SELECT COUNT(*) FROM taxonomy_nodes WHERE level=3 AND status='active'").fetchone()[0]
    l4 = conn.execute("SELECT COUNT(*) FROM taxonomy_nodes WHERE level=4 AND status='active'").fetchone()[0]
    intents = conn.execute("SELECT COUNT(*) FROM intents").fetchone()[0]
    rows = interactions.list_interactions(conn)
    review = sum(1 for r in rows if r["review_status"] == "needs_review")
    unclassified = sum(1 for r in rows if r["classification_status"] == "unclassified")
    pending_props = conn.execute("SELECT COUNT(*) FROM taxonomy_changes WHERE status='proposed'").fetchone()[0]
    overlaps = conn.execute("SELECT COUNT(*) FROM taxonomy_changes WHERE status='proposed' AND change_type='merge'").fetchone()[0]
    candidates = conn.execute("SELECT COUNT(*) FROM assignments WHERE l2_id IS NOT NULL AND l4_id IS NULL "
                              "AND review_status='pending'").fetchone()[0]
    imports = [dict(r) for r in conn.execute("SELECT * FROM imports ORDER BY id DESC")]
    review_counts = {s: 0 for s in assignments.REVIEW_STATUSES}
    for r in conn.execute("SELECT review_status, COUNT(*) FROM assignments GROUP BY review_status"):
        review_counts[r[0]] = r[1]
    return {
        "interactions": total,
        "processed": by_status.get("processed", 0),
        "failed": by_status.get("failed", 0),
        "pending": by_status.get("pending", 0) + by_status.get("processing", 0),
        "intents_extracted": intents,
        "discovered_intents": l4,
        "l3_nodes": l3,
        "l4_nodes": l4,
        "needs_review": review,
        "unclassified": unclassified,
        "open_candidates": candidates,
        "pending_proposals": pending_props,
        "overlapping_categories": overlaps,
        "assignment_review": review_counts,
        "imports": imports,
        "dataset": imports[0]["name"] if imports else None,
        "taxonomy_version": taxonomy.current_version(conn),
    }


def discovery_curve(conn: sqlite3.Connection) -> dict:
    """Distinct L4 categories (current taxonomy) observed within the first N analysed interactions."""
    rows = conn.execute(
        "SELECT x.processed_order, a.l4_id FROM interactions x LEFT JOIN assignments a ON a.interaction_id=x.id "
        "AND a.review_status!='unclassified' WHERE x.processed_order IS NOT NULL ORDER BY x.processed_order").fetchall()
    seen: set[str] = set()
    points: list[dict] = []
    for r in rows:
        if r["l4_id"]:
            seen.add(r["l4_id"])
        if points and points[-1]["interactions"] == r["processed_order"]:
            points[-1]["categories"] = len(seen)
        else:
            points.append({"interactions": r["processed_order"], "categories": len(seen)})
    batches = [dict(r) for r in conn.execute("SELECT * FROM batch_stats ORDER BY id")]
    return {"points": points, "batches": batches}
