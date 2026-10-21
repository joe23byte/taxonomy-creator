"""Progress metrics, discovery curve, per-batch statistics and intent volume insights."""
from __future__ import annotations

import logging
import sqlite3
import threading
from collections import Counter

import numpy as np
from pydantic import BaseModel, Field

from . import assignments, db, embeddings, interactions, taxonomy
from .ollama_client import OllamaClient, OllamaError

log = logging.getLogger("intent_studio.insights")

TOP_N = 5
LONG_TAIL_MAX = 2
NOTES_META_KEY = "top_intent_notes"
_notes_lock = threading.Lock()


def summary(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
    by_status = {r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM interactions GROUP BY status")}
    levels = {r[0]: r[1] for r in conn.execute(
        "SELECT level, COUNT(*) FROM taxonomy_nodes WHERE status='active' GROUP BY level")}
    l3, l4 = levels.get(3, 0), levels.get(4, 0)
    intents = conn.execute("SELECT COUNT(*) FROM intents").fetchone()[0]
    rows = interactions.list_interactions(conn)
    review = sum(1 for r in rows if r["review_status"] == "needs_review")
    unclassified = sum(1 for r in rows if r["classification_status"] == "unclassified")
    pending_props = conn.execute("SELECT COUNT(*) FROM taxonomy_changes WHERE status='proposed'").fetchone()[0]
    overlaps = conn.execute("SELECT COUNT(*) FROM taxonomy_changes WHERE status='proposed' AND change_type='merge'").fetchone()[0]
    open_rows = conn.execute("SELECT intent_id FROM assignments WHERE l2_id IS NOT NULL AND l4_id IS NULL "
                             "AND review_status='pending'").fetchall()
    candidates = len(open_rows)
    waiting_ids = taxonomy.pending_member_intents(conn, include_rejected=False)
    waiting = sum(1 for r in open_rows if r[0] in waiting_ids)
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
        "l1_nodes": levels.get(1, 0),
        "l2_nodes": levels.get(2, 0),
        "l3_nodes": l3,
        "l4_nodes": l4,
        "needs_review": review,
        "unclassified": unclassified,
        "open_candidates": candidates,
        "open_waiting": waiting,
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


# --- intent volume ---------------------------------------------------------------------------

def _paths(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    nodes = {r["id"]: dict(r) for r in conn.execute("SELECT id, label, level, parent_id FROM taxonomy_nodes")}
    out: dict[str, list[dict]] = {}
    for nid in nodes:
        path, cur = [], nodes.get(nid)
        while cur:
            path.insert(0, {"id": cur["id"], "label": cur["label"], "level": cur["level"]})
            cur = nodes.get(cur["parent_id"])
        out[nid] = path
    return out


def _mix(counter: Counter, total: int) -> list[dict]:
    return [{"name": k, "interactions": v, "share": v / total if total else 0.0}
            for k, v in counter.most_common() if k]


def intent_distribution(conn: sqlite3.Connection, top_n: int = TOP_N) -> dict:
    """Interaction volume per active L4 intent, concentration KPIs and the extracted-intent mix."""
    processed = conn.execute("SELECT COUNT(*) FROM interactions WHERE status='processed'").fetchone()[0]
    rows = conn.execute(
        "SELECT a.l4_id, a.interaction_id, x.channel, x.segment FROM assignments a "
        "JOIN interactions x ON x.id=a.interaction_id JOIN taxonomy_nodes n ON n.id=a.l4_id "
        "WHERE n.status='active' AND a.review_status!='unclassified'").fetchall()
    members: dict[str, set[int]] = {}
    intent_counts: Counter = Counter()
    channels: dict[str, Counter] = {}
    segments: dict[str, Counter] = {}
    for r in rows:
        nid, iid = r["l4_id"], r["interaction_id"]
        intent_counts[nid] += 1
        if iid not in members.setdefault(nid, set()):
            members[nid].add(iid)
            channels.setdefault(nid, Counter())[r["channel"]] += 1
            segments.setdefault(nid, Counter())[r["segment"]] += 1

    paths = _paths(conn)
    nodes = {r["id"]: dict(r) for r in conn.execute(
        "SELECT id, label, description FROM taxonomy_nodes WHERE id IN (%s)" % ",".join("?" * len(members)),
        list(members))} if members else {}
    ranked = sorted(members, key=lambda k: (-len(members[k]), -intent_counts[k], nodes[k]["label"]))
    items = []
    for rank, nid in enumerate(ranked, 1):
        n = len(members[nid])
        items.append({
            "rank": rank, "id": nid, "label": nodes[nid]["label"], "description": nodes[nid]["description"],
            "path": paths.get(nid, []), "interactions": n, "intents": intent_counts[nid],
            "share": n / processed if processed else 0.0,
            "channels": _mix(channels.get(nid, Counter()), n), "segments": _mix(segments.get(nid, Counter()), n),
        })

    covered: set[int] = set()
    coverage = []
    for it in ranked:
        covered |= members[it]
        coverage.append(len(covered) / processed if processed else 0.0)
    classified = len(covered)
    top_union = set().union(*(members[k] for k in ranked[:top_n])) if ranked else set()
    for_80 = next((i + 1 for i, c in enumerate(coverage) if processed and c * processed >= 0.8 * classified), None)

    per_interaction = Counter(r[0] for r in conn.execute(
        "SELECT a.interaction_id FROM assignments a JOIN interactions x ON x.id=a.interaction_id "
        "WHERE x.status='processed'"))
    open_or_unclassified = conn.execute(
        "SELECT COUNT(*) FROM assignments a LEFT JOIN taxonomy_nodes n ON n.id=a.l4_id "
        "WHERE a.l4_id IS NULL OR n.status!='active' OR a.review_status='unclassified'").fetchone()[0]
    top_intents = sum(intent_counts[k] for k in ranked[:top_n])
    other_intents = sum(intent_counts[k] for k in ranked[top_n:])
    others = max(len(ranked) - top_n, 0)
    mix = [{"id": k, "kind": "intent", "label": nodes[k]["label"], "intents": intent_counts[k]} for k in ranked[:top_n]]
    mix += [{"id": None, "kind": "other", "count": others, "label": f"Other L4 intents ({others})", "intents": other_intents},
            {"id": None, "kind": "none", "label": "Not yet in an L4", "intents": open_or_unclassified}]

    return {
        "processed": processed,
        "top_n": top_n,
        "items": items,
        "kpis": {
            "classified_interactions": classified,
            "classified_share": classified / processed if processed else 0.0,
            "top_coverage": len(top_union) / processed if processed else 0.0,
            "top_intent_share": top_intents / (top_intents + other_intents + open_or_unclassified)
            if (top_intents + other_intents + open_or_unclassified) else 0.0,
            "intents_for_80": for_80,
            "active_l4": len(ranked),
            "long_tail": sum(1 for k in ranked if len(members[k]) <= LONG_TAIL_MAX),
            "long_tail_max": LONG_TAIL_MAX,
            "multi_intent_share": sum(1 for v in per_interaction.values() if v > 1) / processed if processed else 0.0,
            "avg_intents": sum(per_interaction.values()) / processed if processed else 0.0,
        },
        "coverage": coverage,
        "mix": [m for m in mix if m["intents"]],
    }


def overlap_pairs(conn: sqlite3.Connection, merge_threshold: float, limit: int = 10) -> dict:
    """Closest pairs of active L4 categories within the same L2, by centroid cosine similarity."""
    paths = _paths(conn)
    pending = {}
    for p in taxonomy.list_changes(conn, status="proposed"):
        if p["change_type"] == "merge":
            pending[frozenset((p["proposed"].get("source_id"), p["proposed"].get("target_id")))] = p["id"]
    pairs = []
    for l2 in taxonomy.base_categories(conn):
        member_vecs = embeddings.node_member_vectors(conn, l2["id"])
        ids = sorted(member_vecs)
        cents = {k: embeddings.normalize(np.mean([v for _, v in member_vecs[k]], axis=0)[None, :])[0] for k in ids}
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                pa, pb = paths.get(a, []), paths.get(b, [])
                pairs.append({
                    "a": {"id": a, "label": pa[-1]["label"] if pa else a, "intents": len(member_vecs[a])},
                    "b": {"id": b, "label": pb[-1]["label"] if pb else b, "intents": len(member_vecs[b])},
                    "l2": l2["label"], "similarity": float(cents[a] @ cents[b]),
                    "same_l3": bool(pa and pb and len(pa) > 2 and len(pb) > 2 and pa[2]["id"] == pb[2]["id"]),
                    "proposal_id": pending.get(frozenset((a, b))),
                })
    pairs.sort(key=lambda p: -p["similarity"])
    return {"merge_threshold": merge_threshold, "pairs": pairs[:limit], "compared": len(pairs)}


# --- AI notes for the top intents -------------------------------------------------------------

NOTE_SYSTEM = """You are a contact center analyst. You explain in one or two short sentences why a customer intent
deserves a closer look, based ONLY on its interaction volume and what customers ask for.
- Mention the volume (count and share of interactions) and what the intent is about.
- You may name the kind of improvement worth investigating (e.g. self-service, clearer information, process or
  root-cause fixes), phrased as something to examine, not as a fact.
- Do NOT claim anything about handling time, costs, satisfaction or automation potential; that data is not available.
- Plain text, at most 45 words, in the requested language. Answer as JSON."""

LANGUAGES = {"en": "English", "de": "German"}


class VolumeNote(BaseModel):
    rationale: str = Field(min_length=10, max_length=500)


def _fingerprint(item: dict, processed: int) -> str:
    return f"{item['label']}|{item['interactions']}|{processed}"


def _note_prompt(conn: sqlite3.Connection, item: dict, processed: int, total_l4: int) -> str:
    samples = [r[0] for r in conn.execute(
        "SELECT i.intent_text FROM assignments a JOIN intents i ON i.id=a.intent_id WHERE a.l4_id=? "
        "AND a.review_status!='unclassified' ORDER BY a.similarity DESC NULLS LAST, a.id LIMIT 5", (item["id"],))]
    channels = ", ".join(f"{c['name']} {c['share']:.0%}" for c in item["channels"][:3]) or "unknown"
    segments = ", ".join(f"{c['name']} {c['share']:.0%}" for c in item["segments"][:3]) or "unknown"
    return (f"Intent (rank {item['rank']} of {total_l4} by volume): {' > '.join(p['label'] for p in item['path'])}\n"
            f"Description: {item['description']}\n"
            f"Volume: {item['interactions']} of {processed} analysed interactions ({item['share']:.0%})\n"
            f"Channels: {channels}\nSegments: {segments}\n"
            "Example customer intents:\n" + "\n".join(f"- {s}" for s in samples) +
            '\n\nReturn {"rationale": "..."}.')


def _notes_key(lang: str) -> str:
    return NOTES_META_KEY if lang == "en" else f"{NOTES_META_KEY}:{lang}"


def cached_notes(conn: sqlite3.Connection, dist: dict, lang: str = "en") -> dict[str, dict]:
    stored = db.loads(db.get_meta(conn, _notes_key(lang), "{}"), {}) or {}
    out = {}
    for it in dist["items"][:dist["top_n"]]:
        note = stored.get(it["id"])
        if note:
            out[it["id"]] = {**note, "stale": note.get("fingerprint") != _fingerprint(it, dist["processed"])}
    return out


def generate_notes(conn: sqlite3.Connection, client: OllamaClient, model: str, force: bool = False,
                   lang: str = "en") -> dict:
    """Create volume-based notes for the current top intents; reuses notes whose inputs did not change."""
    if lang not in LANGUAGES:
        lang = "en"
    if not _notes_lock.acquire(blocking=False):
        return {"generated": 0, "busy": True}
    try:
        dist = intent_distribution(conn)
        stored = db.loads(db.get_meta(conn, _notes_key(lang), "{}"), {}) or {}
        generated, errors = 0, []
        for it in dist["items"][:dist["top_n"]]:
            fp = _fingerprint(it, dist["processed"])
            if not force and stored.get(it["id"], {}).get("fingerprint") == fp:
                continue
            try:
                prompt = _note_prompt(conn, it, dist["processed"], len(dist["items"]))
                prompt += f"\nWrite the rationale in {LANGUAGES[lang]}."
                out = client.chat_structured(model, NOTE_SYSTEM, prompt, VolumeNote)
            except OllamaError as e:
                log.warning("Top-intent note failed for %s: %s", it["id"], type(e).__name__)
                errors.append(it["id"])
                continue
            stored[it["id"]] = {"text": " ".join(out.rationale.split()), "fingerprint": fp, "model": model,
                                "created_at": db.utcnow()}
            generated += 1
        top_ids = {it["id"] for it in dist["items"][:dist["top_n"]]}
        stored = {k: v for k, v in stored.items() if k in top_ids}
        with db.write_lock, db.transaction(conn):
            db.set_meta(conn, _notes_key(lang), db.dumps(stored))
        return {"generated": generated, "failed": errors, "busy": False}
    finally:
        _notes_lock.release()
