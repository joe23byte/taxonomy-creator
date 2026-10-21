"""Taxonomy management: fixed L1/L2 seed, dynamic L3/L4 nodes, proposals, history and versions."""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from . import assignments, clustering, config, db, embeddings, events, language

ACTIVE = "active"
PENDING = "proposed"


class TaxonomyError(ValueError):
    pass


# --- seed / import -----------------------------------------------------------

def validate_seed(data: dict) -> list[dict]:
    cats = data.get("categories") if isinstance(data, dict) else data
    if not isinstance(cats, list) or not cats:
        raise TaxonomyError("Taxonomy file must contain a non-empty 'categories' list")
    ids = set()
    for c in cats:
        for k in ("id", "label", "level"):
            if k not in c:
                raise TaxonomyError(f"Category is missing '{k}'")
        if c["level"] not in (1, 2):
            raise TaxonomyError("Only L1 and L2 categories can be predefined")
        if c["id"] in ids:
            raise TaxonomyError(f"Duplicate category id {c['id']}")
        ids.add(c["id"])
    for c in cats:
        if c["level"] == 1 and c.get("parent_id"):
            raise TaxonomyError(f"L1 category {c['id']} cannot have a parent")
        if c["level"] == 2 and c.get("parent_id") not in ids:
            raise TaxonomyError(f"L2 category {c['id']} needs a valid L1 parent_id")
    return cats


def _insert_seed(conn: sqlite3.Connection, cats: list[dict]) -> None:
    now = db.utcnow()
    for c in sorted(cats, key=lambda c: c["level"]):
        conn.execute(
            "INSERT INTO taxonomy_nodes(id, label, description, parent_id, level, source, status, created_at, "
            "updated_at, created_version) VALUES (?,?,?,?,?,?,?,?,?,1)",
            (c["id"], c["label"], c.get("description", ""), c.get("parent_id"), c["level"], "predefined",
             ACTIVE, now, now),
        )


def seed_if_empty(conn: sqlite3.Connection, path: Path | None = None) -> bool:
    """Load the default taxonomy into a database that has never had one (projects start without it)."""
    if conn.execute("SELECT COUNT(*) FROM taxonomy_nodes").fetchone()[0] or db.get_meta(conn, "taxonomy_version"):
        return False
    cats = validate_seed(json.loads(Path(path or config.TAXONOMY_SEED_PATH).read_text()))
    with db.transaction(conn):
        _insert_seed(conn, cats)
        conn.execute("INSERT OR IGNORE INTO taxonomy_versions(version, created_at, summary) VALUES (1, ?, ?)",
                     (db.utcnow(), "Predefined L1/L2 taxonomy loaded"))
        db.set_meta(conn, "taxonomy_version", "1")
    return True


def replace_base_taxonomy(conn: sqlite3.Connection, data: dict) -> int:
    """Load a new L1/L2 taxonomy. Only allowed before any intents have been classified.

    The analysis language is taken from an explicit ``language`` field or detected from the labels.
    """
    cats = validate_seed(data)
    explicit = str(data.get("language") or "").lower()[:2] if isinstance(data, dict) else ""
    lang = explicit if explicit in language.NAMES else language.detect_categories(cats)
    with db.write_lock, db.transaction(conn):
        if conn.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]:
            raise TaxonomyError("Reset the analysis before replacing the L1/L2 taxonomy")
        conn.execute("DELETE FROM taxonomy_nodes WHERE level IN (3,4)")
        conn.execute("DELETE FROM taxonomy_nodes WHERE level=2")
        conn.execute("DELETE FROM taxonomy_nodes WHERE level=1")
        _insert_seed(conn, cats)
        language.store(conn, lang)
        v = bump_version(conn, f"Base taxonomy replaced ({len(cats)} categories)")
    return v


# --- basic access --------------------------------------------------------------

def bump_version(conn: sqlite3.Connection, summary: str) -> int:
    v = int(db.get_meta(conn, "taxonomy_version", "1")) + 1
    conn.execute("INSERT INTO taxonomy_versions(version, created_at, summary) VALUES (?,?,?)",
                 (v, db.utcnow(), summary[:300]))
    db.set_meta(conn, "taxonomy_version", str(v))
    return v


def current_version(conn: sqlite3.Connection) -> int:
    return int(db.get_meta(conn, "taxonomy_version", "1"))


def get_node(conn: sqlite3.Connection, node_id: str | None) -> dict | None:
    if not node_id:
        return None
    r = conn.execute("SELECT * FROM taxonomy_nodes WHERE id=?", (node_id,)).fetchone()
    return dict(r) if r else None


def require_node(conn: sqlite3.Connection, node_id: str) -> dict:
    n = get_node(conn, node_id)
    if not n:
        raise TaxonomyError(f"Unknown category {node_id}")
    return n


def nodes(conn: sqlite3.Connection, statuses: tuple[str, ...] = (ACTIVE,), level: int | None = None,
          parent_id: str | None = None) -> list[dict]:
    sql = f"SELECT * FROM taxonomy_nodes WHERE status IN ({','.join('?' * len(statuses))})"
    params: list[Any] = list(statuses)
    if level is not None:
        sql += " AND level=?"
        params.append(level)
    if parent_id is not None:
        sql += " AND parent_id=?"
        params.append(parent_id)
    return [dict(r) for r in conn.execute(sql + " ORDER BY level, label", params)]


def base_categories(conn: sqlite3.Connection) -> list[dict]:
    """Active L2 categories with their L1, used by the extraction prompt."""
    rows = conn.execute(
        "SELECT c.id, c.label, c.description, p.id AS l1_id, p.label AS l1_label FROM taxonomy_nodes c "
        "JOIN taxonomy_nodes p ON p.id=c.parent_id WHERE c.level=2 AND c.status='active' "
        "AND p.status='active' ORDER BY p.label, c.label")
    return [dict(r) for r in rows]


def next_id(conn: sqlite3.Connection, level: int) -> str:
    key = f"seq_l{level}"
    n = int(db.get_meta(conn, key, "0")) + 1
    while conn.execute("SELECT 1 FROM taxonomy_nodes WHERE id=?", (f"L{level}-{n:04d}",)).fetchone():
        n += 1
    db.set_meta(conn, key, str(n))
    return f"L{level}-{n:04d}"


def norm_label(label: str) -> str:
    return re.sub(r"[\W_]+", " ", label.lower()).strip()


_DANGLING = {"a", "an", "and", "at", "by", "for", "from", "in", "is", "of", "on", "or", "the", "to", "via", "with",
             "und", "oder", "für", "von", "mit", "zu", "bei", "der", "die", "das", "&", "/"}


def clean_label(label: str, max_words: int = 8, lang: str = "en") -> str:
    """Trim and shorten a label. Title Case only applies to English; other languages keep their casing."""
    label = re.sub(r"\s+", " ", (label or "").strip().strip(".:-"))
    words = [w for w in label.split(" ") if w][:max_words]
    while len(words) > 1 and words[-1].lower() in _DANGLING:
        words.pop()
    if lang == "en":
        return " ".join(w if w.isupper() else (w[:1].upper() + w[1:]) for w in words)
    if words:
        words[0] = words[0][:1].upper() + words[0][1:]
    return language.tidy_label(" ".join(words), lang)


def find_by_label(conn: sqlite3.Connection, parent_id: str, label: str,
                  statuses: tuple[str, ...] = (ACTIVE, PENDING)) -> dict | None:
    target = norm_label(label)
    for n in nodes(conn, statuses, parent_id=parent_id):
        if norm_label(n["label"]) == target:
            return n
    return None


def _insert_node(conn: sqlite3.Connection, level: int, label: str, description: str, parent_id: str,
                 source: str, status: str) -> str:
    nid = next_id(conn, level)
    now = db.utcnow()
    conn.execute(
        "INSERT INTO taxonomy_nodes(id, label, description, parent_id, level, source, status, created_at, "
        "updated_at, created_version) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (nid, label, description, parent_id, level, source, status, now, now, current_version(conn)),
    )
    return nid


def record_change(conn: sqlite3.Connection, *, node_id: str | None, change_type: str, previous: Any,
                  proposed: Any, status: str, rationale: str | None, source: str, run_id: int | None,
                  version: int | None = None) -> int:
    decided = db.utcnow() if status in ("auto_accepted", "accepted", "rejected") else None
    cur = conn.execute(
        "INSERT INTO taxonomy_changes(created_at, node_id, change_type, previous_json, proposed_json, status, "
        "rationale, source, run_id, decided_at, version) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (db.utcnow(), node_id, change_type, db.dumps(previous) if previous is not None else None,
         db.dumps(proposed), status, rationale, source, run_id, decided, version),
    )
    return int(cur.lastrowid)


def change(conn: sqlite3.Connection, change_id: int) -> dict:
    r = conn.execute("SELECT * FROM taxonomy_changes WHERE id=?", (change_id,)).fetchone()
    if not r:
        raise TaxonomyError("Proposal not found")
    return change_to_dict(r)


def change_to_dict(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "created_at": r["created_at"], "node_id": r["node_id"], "change_type": r["change_type"],
            "previous": db.loads(r["previous_json"]), "proposed": db.loads(r["proposed_json"], {}),
            "status": r["status"], "rationale": r["rationale"], "source": r["source"], "run_id": r["run_id"],
            "decided_at": r["decided_at"], "version": r["version"]}


def list_changes(conn: sqlite3.Connection, status: str | None = None, node_id: str | None = None,
                 limit: int = 500) -> list[dict]:
    sql = "SELECT * FROM taxonomy_changes WHERE 1=1"
    params: list[Any] = []
    if status:
        sql += " AND status=?"
        params.append(status)
    if node_id:
        sql += " AND (node_id=? OR proposed_json LIKE ?)"
        params += [node_id, f'%"{node_id}"%']
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return [change_to_dict(r) for r in conn.execute(sql, params)]


def pending_member_intents(conn: sqlite3.Connection, include_rejected: bool = True) -> set[int]:
    """Intent ids already tied to an open (or rejected) creation proposal; excluded from re-clustering."""
    statuses = ("proposed", "rejected") if include_rejected else ("proposed",)
    out: set[int] = set()
    for r in conn.execute(f"SELECT proposed_json FROM taxonomy_changes WHERE change_type='create' AND status IN "
                          f"({','.join('?' * len(statuses))})", statuses):
        out.update(db.loads(r["proposed_json"], {}).get("member_intent_ids", []))
    return out


def pair_already_proposed(conn: sqlite3.Connection, a: str, b: str) -> bool:
    for r in conn.execute("SELECT proposed_json FROM taxonomy_changes WHERE change_type='merge'"):
        p = db.loads(r["proposed_json"], {})
        if {p.get("source_id"), p.get("target_id")} == {a, b}:
            return True
    return False


def split_already_proposed(conn: sqlite3.Connection, node_id: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM taxonomy_changes WHERE change_type='split' AND node_id=? "
                             "AND status IN ('proposed','rejected')", (node_id,)).fetchone())


# --- tree & details ----------------------------------------------------------------

def _counts(conn: sqlite3.Connection) -> tuple[dict[str, set[int]], dict[str, int], dict[str, int]]:
    per_node: dict[str, set[int]] = defaultdict(set)
    intents_per_node: dict[str, int] = defaultdict(int)
    candidates: dict[str, int] = defaultdict(int)
    for r in conn.execute("SELECT interaction_id, l1_id, l2_id, l3_id, l4_id FROM assignments "
                          "WHERE review_status!='unclassified'"):
        for k in ("l1_id", "l2_id", "l3_id", "l4_id"):
            if r[k]:
                per_node[r[k]].add(r["interaction_id"])
                intents_per_node[r[k]] += 1
        if r["l2_id"] and not r["l4_id"]:
            candidates[r["l2_id"]] += 1
    return per_node, intents_per_node, candidates


def tree(conn: sqlite3.Connection, include_inactive: bool = False) -> dict:
    statuses = ("active", "proposed", "merged", "split", "retired") if include_inactive else ("active", "proposed")
    per_node, intents_per_node, candidates = _counts(conn)
    pending = list_changes(conn, status="proposed")
    flags: dict[str, list[dict]] = defaultdict(list)
    proposal_members: dict[str, set[int]] = {}
    for p in pending:
        prop = p["proposed"]
        if p["change_type"] == "merge":
            for nid in (prop.get("source_id"), prop.get("target_id")):
                flags[nid].append({"type": "merge", "change_id": p["id"]})
        elif p["change_type"] == "split":
            flags[p["node_id"]].append({"type": "split", "change_id": p["id"]})
        elif p["change_type"] == "create":
            flags[p["node_id"]].append({"type": "create", "change_id": p["id"]})
            ids = prop.get("member_intent_ids", [])
            if ids:
                q = f"SELECT DISTINCT interaction_id FROM intents WHERE id IN ({','.join('?' * len(ids))})"
                proposal_members[p["node_id"]] = {r[0] for r in conn.execute(q, ids)}
            if prop.get("l3", {}).get("is_new"):
                flags[prop["l3"]["id"]].append({"type": "create", "change_id": p["id"]})
    out = []
    for n in nodes(conn, statuses):
        count = len(per_node.get(n["id"], ()))
        if n["status"] == "proposed" and n["level"] == 4:
            count = len(proposal_members.get(n["id"], ()))
        out.append({
            "id": n["id"], "label": n["label"], "description": n["description"], "parent_id": n["parent_id"],
            "level": n["level"], "source": n["source"], "status": n["status"], "merged_into": n["merged_into"],
            "interaction_count": count, "intent_count": intents_per_node.get(n["id"], 0),
            "candidate_count": candidates.get(n["id"], 0) if n["level"] == 2 else 0,
            "flags": flags.get(n["id"], []), "created_at": n["created_at"], "updated_at": n["updated_at"],
        })
    return {"version": current_version(conn), "nodes": out, "pending_proposals": len(pending)}


def node_detail(conn: sqlite3.Connection, node_id: str) -> dict:
    n = require_node(conn, node_id)
    level_col = f"l{n['level']}_id"
    path = []
    cur = n
    while cur:
        path.insert(0, {"id": cur["id"], "label": cur["label"], "level": cur["level"]})
        cur = get_node(conn, cur["parent_id"])
    rows = conn.execute(
        f"SELECT a.id AS assignment_id, a.review_status, a.similarity, a.method, i.intent_text, i.evidence, "
        f"x.conversation_id, x.channel, x.segment, x.id AS interaction_id FROM assignments a "
        f"JOIN intents i ON i.id=a.intent_id JOIN interactions x ON x.id=a.interaction_id "
        f"WHERE a.{level_col}=? AND a.review_status!='unclassified' ORDER BY a.similarity DESC NULLS LAST, a.id",
        (node_id,)).fetchall()
    examples = [dict(r) for r in rows]
    members_from_proposal: list[dict] = []
    if n["status"] == "proposed":
        for p in list_changes(conn, status="proposed", node_id=node_id):
            ids = p["proposed"].get("member_intent_ids", [])
            if ids:
                q = (f"SELECT i.id, i.intent_text, i.evidence, x.conversation_id, x.id AS interaction_id "
                     f"FROM intents i JOIN interactions x ON x.id=i.interaction_id "
                     f"WHERE i.id IN ({','.join('?' * len(ids))})")
                members_from_proposal = [dict(r) for r in conn.execute(q, ids)]
    children = [{"id": c["id"], "label": c["label"], "status": c["status"], "level": c["level"]}
                for c in nodes(conn, ("active", "proposed"), parent_id=node_id)]
    return {
        **n,
        "path": path,
        "children": children,
        "interaction_count": len({e["interaction_id"] for e in examples}),
        "intent_count": len(examples),
        "examples": examples[:50],
        "proposal_members": members_from_proposal,
        "history": list_changes(conn, node_id=node_id, limit=100),
        "events": events.list_events(conn, node_id=node_id, limit=50, newest_first=True),
    }


# --- proposals ------------------------------------------------------------------------

def propose_create(conn: sqlite3.Connection, *, l2_id: str, l3: dict, l4: dict, member_intent_ids: list[int],
                   cluster_info: dict, rationale: str, run_id: int | None, auto_accept: bool,
                   conflict: str | None, settings: config.Settings) -> dict:
    """Create proposed L3/L4 nodes for a cluster; auto-accept when allowed and conflict-free."""
    l2 = require_node(conn, l2_id)
    l3_new = False
    if l3.get("existing_id"):
        l3_node = require_node(conn, l3["existing_id"])
        l3_id = l3_node["id"]
        l3_label = l3_node["label"]
    else:
        l3_label = clean_label(l3["label"], lang=language.get(conn))
        same = find_by_label(conn, l2_id, l3_label)
        if same:
            l3_id = same["id"]
        else:
            l3_id = _insert_node(conn, 3, l3_label, l3.get("description", "")[:400], l2_id, "ai", PENDING)
            l3_new = True
    l4_label = clean_label(l4["label"], lang=language.get(conn))
    l4_id = _insert_node(conn, 4, l4_label, l4.get("description", "")[:400], l3_id, "ai", PENDING)
    proposed = {
        "l1_id": l2["parent_id"], "l2_id": l2_id,
        "l3": {"id": l3_id, "label": l3_label, "is_new": l3_new, "description": l3.get("description", "")},
        "l4": {"id": l4_id, "label": l4_label, "description": l4.get("description", "")},
        "member_intent_ids": member_intent_ids, "cluster": cluster_info, "conflict": conflict,
    }
    cid = record_change(conn, node_id=l4_id, change_type="create", previous=None, proposed=proposed,
                        status="proposed", rationale=rationale, source="ai", run_id=run_id)
    events.emit(conn, "category_proposed",
                f"New L4 category proposed: {l4_label}" + (f" (new L3: {l3_label})" if l3_new else f" under {l3_label}"),
                run_id=run_id, node_id=l4_id,
                data={"change_id": cid, "l3_id": l3_id, "l3_label": l3_label, "l3_new": l3_new, "l2_id": l2_id,
                      "size": len(member_intent_ids), "conflict": conflict})
    accepted = False
    if auto_accept and not conflict:
        accept(conn, cid, actor="auto", settings=settings, run_id=run_id)
        accepted = True
    return {"change_id": cid, "l4_id": l4_id, "l3_id": l3_id, "l3_new": l3_new, "accepted": accepted}


def attach_to_pending_create(conn: sqlite3.Connection, l4_id: str, intent_ids: list[int]) -> int | None:
    """Add intents to the open creation proposal of a proposed L4; they are assigned when it is accepted."""
    row = conn.execute("SELECT id, proposed_json FROM taxonomy_changes WHERE node_id=? AND change_type='create' "
                       "AND status='proposed' ORDER BY id DESC LIMIT 1", (l4_id,)).fetchone()
    if not row:
        return None
    p = db.loads(row["proposed_json"], {})
    members = p.get("member_intent_ids", [])
    added = [i for i in intent_ids if i not in members]
    p["member_intent_ids"] = members + added
    conn.execute("UPDATE taxonomy_changes SET proposed_json=? WHERE id=?", (db.dumps(p), row["id"]))
    return len(added)


def propose_merge(conn: sqlite3.Connection, source_id: str, target_id: str, similarity: float, rationale: str,
                  run_id: int | None) -> int | None:
    if pair_already_proposed(conn, source_id, target_id):
        return None
    s, t = require_node(conn, source_id), require_node(conn, target_id)
    proposed = {"source_id": source_id, "target_id": target_id, "source_label": s["label"],
                "target_label": t["label"], "similarity": round(similarity, 4), "level": s["level"]}
    cid = record_change(conn, node_id=source_id, change_type="merge", previous={"source": _snap(s), "target": _snap(t)},
                        proposed=proposed, status="proposed", rationale=rationale, source="ai", run_id=run_id)
    events.emit(conn, "merge_proposed", f"Merge proposed: “{s['label']}” → “{t['label']}” "
                f"(similarity {similarity:.2f})", run_id=run_id, node_id=source_id, level="warning",
                data={"change_id": cid, "target_id": target_id, "similarity": similarity})
    return cid


def propose_split(conn: sqlite3.Connection, source_id: str, parts: list[dict], rationale: str,
                  run_id: int | None) -> int:
    s = require_node(conn, source_id)
    cid = record_change(conn, node_id=source_id, change_type="split", previous=_snap(s),
                        proposed={"source_id": source_id, "source_label": s["label"], "parts": parts},
                        status="proposed", rationale=rationale, source="ai", run_id=run_id)
    events.emit(conn, "split_proposed", f"Split proposed for “{s['label']}” into "
                + ", ".join(f"“{p['label']}”" for p in parts), run_id=run_id, node_id=source_id, level="warning",
                data={"change_id": cid})
    return cid


def _snap(n: dict) -> dict:
    return {k: n[k] for k in ("id", "label", "description", "parent_id", "level", "status")}


def accept(conn: sqlite3.Connection, change_id: int, *, actor: str, settings: config.Settings,
           run_id: int | None = None) -> dict:
    ch = change(conn, change_id)
    if ch["status"] != "proposed":
        raise TaxonomyError(f"Proposal is already {ch['status']}")
    kind = ch["change_type"]
    if kind == "create":
        result = _apply_create(conn, ch, settings, run_id)
    elif kind == "merge":
        result = _apply_merge(conn, ch, run_id)
    elif kind == "split":
        result = _apply_split(conn, ch, settings, run_id)
    else:
        raise TaxonomyError(f"Cannot accept change type {kind}")
    status = "auto_accepted" if actor == "auto" else "accepted"
    v = bump_version(conn, result["summary"])
    conn.execute("UPDATE taxonomy_changes SET status=?, decided_at=?, version=? WHERE id=?",
                 (status, db.utcnow(), v, change_id))
    kind_event = "category_approved" if kind == "create" else "proposal_accepted"
    events.emit(conn, kind_event, result["summary"] + (" (auto-accepted)" if actor == "auto" else ""),
                run_id=run_id, node_id=result.get("node_id"), level="success",
                data={"change_id": change_id, "version": v, **{k: v2 for k, v2 in result.items() if k != "summary"}})
    return {**result, "version": v}


def reject(conn: sqlite3.Connection, change_id: int, run_id: int | None = None) -> dict:
    ch = change(conn, change_id)
    if ch["status"] != "proposed":
        raise TaxonomyError(f"Proposal is already {ch['status']}")
    if ch["change_type"] == "create":
        p = ch["proposed"]
        conn.execute("UPDATE taxonomy_nodes SET status='rejected', updated_at=? WHERE id=?", (db.utcnow(), p["l4"]["id"]))
        if p["l3"].get("is_new"):
            remaining = conn.execute("SELECT COUNT(*) FROM taxonomy_nodes WHERE parent_id=? AND status IN "
                                     "('active','proposed')", (p["l3"]["id"],)).fetchone()[0]
            if not remaining:
                conn.execute("UPDATE taxonomy_nodes SET status='rejected', updated_at=? WHERE id=?",
                             (db.utcnow(), p["l3"]["id"]))
        for iid in p.get("member_intent_ids", []):
            conn.execute("UPDATE assignments SET needs_review=1, review_reason=? WHERE intent_id=? "
                         "AND review_status='pending' AND l4_id IS NULL",
                         ("Proposed category was rejected — assign manually", iid))
    conn.execute("UPDATE taxonomy_changes SET status='rejected', decided_at=? WHERE id=?", (db.utcnow(), change_id))
    events.emit(conn, "proposal_rejected", f"Proposal #{change_id} ({ch['change_type']}) rejected",
                run_id=run_id, node_id=ch["node_id"], data={"change_id": change_id})
    return {"change_id": change_id, "status": "rejected"}


def _apply_create(conn: sqlite3.Connection, ch: dict, settings: config.Settings, run_id: int | None) -> dict:
    p = ch["proposed"]
    l3_id, l4_id = p["l3"]["id"], p["l4"]["id"]
    now = db.utcnow()
    conn.execute("UPDATE taxonomy_nodes SET status='active', updated_at=? WHERE id IN (?, ?)", (now, l3_id, l4_id))
    ids = p.get("member_intent_ids", [])
    rows = []
    if ids:
        rows = conn.execute(
            f"SELECT a.id, a.review_status, i.embedding_id FROM assignments a JOIN intents i ON i.id=a.intent_id "
            f"WHERE a.intent_id IN ({','.join('?' * len(ids))})", ids).fetchall()
    vecs = embeddings.load(conn, [r["embedding_id"] for r in rows])
    member_vecs = [vecs[r["embedding_id"]] for r in rows if r["embedding_id"] in vecs]
    centroid = embeddings.normalize(np.mean(member_vecs, axis=0)[None, :])[0] if member_vecs else None
    support = len(rows)
    assigned = 0
    for r in rows:
        sim = float(vecs[r["embedding_id"]] @ centroid) if centroid is not None and r["embedding_id"] in vecs else None
        low_support = support < 2
        if assignments.ai_assign(conn, r["id"], l4_id=l4_id, method="cluster" if support > 1 else "llm_outlier",
                                 similarity=sim, needs_review=low_support,
                                 review_reason="Category supported by a single intent" if low_support else None,
                                 action="assigned_by_new_category"):
            assigned += 1
    conn.execute("UPDATE taxonomy_nodes SET support_at_description=? WHERE id=?", (support, l4_id))
    rematched = rematch_candidates(conn, p["l2_id"], settings, run_id, only_nodes={l4_id})
    return {"summary": f"Category “{p['l4']['label']}” added under {p['l3']['label']}", "node_id": l4_id,
            "l3_id": l3_id, "assigned": assigned, "rematched": rematched}


def _flag_reviewed(conn: sqlite3.Connection, level: int, node_id: str, reason: str) -> int:
    col = f"l{level}_id"
    cur = conn.execute(f"UPDATE assignments SET needs_review=1, review_reason=? WHERE {col}=? AND "
                       f"review_status IN ('confirmed','corrected')", (reason, node_id))
    return cur.rowcount


def _apply_merge(conn: sqlite3.Connection, ch: dict, run_id: int | None) -> dict:
    p = ch["proposed"]
    src, tgt = require_node(conn, p["source_id"]), require_node(conn, p["target_id"])
    if src["status"] != ACTIVE or tgt["status"] != ACTIVE:
        raise TaxonomyError("Both categories must be active to merge")
    now = db.utcnow()
    moved = 0
    if src["level"] == 4:
        for r in conn.execute("SELECT id FROM assignments WHERE l4_id=? AND review_status='pending'",
                              (src["id"],)).fetchall():
            if assignments.ai_assign(conn, r["id"], l4_id=tgt["id"], method="merge", action="moved_by_merge"):
                moved += 1
    else:  # L3: move child L4 categories, update all paths (leaf decisions are unchanged)
        for child in conn.execute("SELECT id FROM taxonomy_nodes WHERE parent_id=? AND status IN ('active','proposed')",
                                  (src["id"],)).fetchall():
            conn.execute("UPDATE taxonomy_nodes SET parent_id=?, updated_at=? WHERE id=?", (tgt["id"], now, child["id"]))
            for r in conn.execute("SELECT id FROM assignments WHERE l4_id=?", (child["id"],)).fetchall():
                assignments.repath(conn, r["id"], "ai", "path_updated_by_merge")
                moved += 1
    flagged = _flag_reviewed(conn, src["level"], src["id"], f"Category merged into {tgt['label']} — please re-check")
    conn.execute("UPDATE taxonomy_nodes SET status='merged', merged_into=?, updated_at=? WHERE id=?",
                 (tgt["id"], now, src["id"]))
    return {"summary": f"Merged “{src['label']}” into “{tgt['label']}”", "node_id": tgt["id"],
            "moved": moved, "reviewed_preserved": flagged}


def _apply_split(conn: sqlite3.Connection, ch: dict, settings: config.Settings, run_id: int | None) -> dict:
    p = ch["proposed"]
    src = require_node(conn, p["source_id"])
    if src["status"] != ACTIVE:
        raise TaxonomyError("Category must be active to split")
    part_ids = []
    intent_to_part: dict[int, str] = {}
    for part in p["parts"]:
        nid = _insert_node(conn, 4, clean_label(part["label"], lang=language.get(conn)), part.get("description", ""), src["parent_id"], "ai",
                           ACTIVE)
        part_ids.append(nid)
        part["id"] = nid
        for iid in part.get("member_intent_ids", []):
            intent_to_part[iid] = nid
    conn.execute("UPDATE taxonomy_changes SET proposed_json=? WHERE id=?", (db.dumps(p), ch["id"]))
    rows = conn.execute("SELECT a.id, a.intent_id, i.embedding_id FROM assignments a JOIN intents i "
                        "ON i.id=a.intent_id WHERE a.l4_id=? AND a.review_status='pending'", (src["id"],)).fetchall()
    vecs = embeddings.load(conn, [r["embedding_id"] for r in rows])
    part_cents = {}
    for nid in part_ids:
        vs = [vecs[r["embedding_id"]] for r in rows if intent_to_part.get(r["intent_id"]) == nid and r["embedding_id"] in vecs]
        if vs:
            part_cents[nid] = embeddings.normalize(np.mean(vs, axis=0)[None, :])[0]
    moved = 0
    for r in rows:
        target = intent_to_part.get(r["intent_id"])
        sim = None
        if r["embedding_id"] in vecs and part_cents:
            matches = clustering.best_matches(vecs[r["embedding_id"]], part_cents, top=1)
            if not target:
                target = matches[0][0]
            sim = float(vecs[r["embedding_id"]] @ part_cents[target]) if target in part_cents else None
        target = target or part_ids[0]
        if assignments.ai_assign(conn, r["id"], l4_id=target, method="split", similarity=sim, action="moved_by_split"):
            moved += 1
    flagged = _flag_reviewed(conn, 4, src["id"], "Category was split — please choose the more specific category")
    conn.execute("UPDATE taxonomy_nodes SET status='split', updated_at=? WHERE id=?", (db.utcnow(), src["id"]))
    return {"summary": f"Split “{src['label']}” into " + ", ".join(f"“{x['label']}”" for x in p["parts"]),
            "node_id": src["parent_id"], "new_nodes": part_ids, "moved": moved, "reviewed_preserved": flagged}


def apply_refinement(conn: sqlite3.Connection, node_id: str, description: str, support: int, rationale: str,
                     run_id: int | None) -> int:
    n = require_node(conn, node_id)
    v = bump_version(conn, f"Description of “{n['label']}” refined")
    cid = record_change(conn, node_id=node_id, change_type="refine", previous={"description": n["description"]},
                        proposed={"description": description, "support": support}, status="auto_accepted",
                        rationale=rationale, source="ai", run_id=run_id, version=v)
    conn.execute("UPDATE taxonomy_nodes SET description=?, support_at_description=?, updated_at=? WHERE id=?",
                 (description[:400], support, db.utcnow(), node_id))
    events.emit(conn, "category_refined", f"Category refined: {n['label']} (now based on {support} intents)",
                run_id=run_id, node_id=node_id, data={"change_id": cid})
    return cid


# --- candidate re-matching ------------------------------------------------------------------

def rematch_candidates(conn: sqlite3.Connection, l2_id: str, settings: config.Settings, run_id: int | None,
                       only_nodes: set[str] | None = None) -> int:
    """Assign still-unclassified, unreviewed candidates in an L2 to sufficiently similar L4 categories."""
    th = settings.thresholds()
    cents = embeddings.centroids(conn, l2_id)
    if only_nodes is not None:
        cents = {k: v for k, v in cents.items() if k in only_nodes}
    if not cents:
        return 0
    blocked = pending_member_intents(conn)
    rows = conn.execute(
        "SELECT a.id, a.intent_id, i.embedding_id, x.conversation_id FROM assignments a JOIN intents i "
        "ON i.id=a.intent_id JOIN interactions x ON x.id=a.interaction_id WHERE a.l2_id=? AND a.l4_id IS NULL "
        "AND a.review_status='pending' AND i.embedding_id IS NOT NULL", (l2_id,)).fetchall()
    vecs = embeddings.load(conn, [r["embedding_id"] for r in rows])
    n = 0
    for r in rows:
        if r["intent_id"] in blocked or r["embedding_id"] not in vecs:
            continue
        matches = clustering.best_matches(vecs[r["embedding_id"]], cents, top=3)
        if matches and matches[0][1] >= th["match"]:
            nid, sim = matches[0]
            alts = [{"node_id": m, "similarity": round(s, 4)} for m, s in matches[1:]]
            if assignments.ai_assign(conn, r["id"], l4_id=nid, method="embedding_match", similarity=sim,
                                     alternatives=alts, action="rematched"):
                n += 1
                node = get_node(conn, nid)
                events.emit(conn, "interaction_assigned",
                            f"Interaction {r['conversation_id']} — candidate assigned to {node['label']} "
                            f"(similarity {sim:.2f})", run_id=run_id, conversation_id=r["conversation_id"],
                            node_id=nid, data={"similarity": sim})
    return n


# --- manual edits -------------------------------------------------------------------------------

def manual_update(conn: sqlite3.Connection, node_id: str, label: str | None, description: str | None) -> dict:
    n = require_node(conn, node_id)
    new = {"label": clean_label(label, 8, language.get(conn)) if label else n["label"],
           "description": description if description is not None else n["description"]}
    if n["parent_id"] and new["label"] != n["label"]:
        dup = find_by_label(conn, n["parent_id"], new["label"], (ACTIVE,))
        if dup and dup["id"] != node_id:
            raise TaxonomyError(f"A sibling category named “{new['label']}” already exists")
    v = bump_version(conn, f"“{n['label']}” edited manually")
    record_change(conn, node_id=node_id, change_type="update",
                  previous={"label": n["label"], "description": n["description"]}, proposed=new, status="accepted",
                  rationale="Manual edit", source="user", run_id=None, version=v)
    conn.execute("UPDATE taxonomy_nodes SET label=?, description=?, updated_at=? WHERE id=?",
                 (new["label"], new["description"], db.utcnow(), node_id))
    events.emit(conn, "taxonomy_edited", f"Category edited: {new['label']}", node_id=node_id)
    return require_node(conn, node_id)


def manual_create(conn: sqlite3.Connection, parent_id: str | None, label: str, description: str) -> dict:
    if parent_id:
        parent = require_node(conn, parent_id)
        level = parent["level"] + 1
        if level > 4:
            raise TaxonomyError("L4 is the deepest level")
        if find_by_label(conn, parent_id, label, (ACTIVE,)):
            raise TaxonomyError("A sibling with this name already exists")
    else:
        level = 1
    source = "predefined" if level <= 2 else "manual"
    if level <= 2:
        nid = f"L{level}-USR-{int(db.get_meta(conn, 'seq_user', '0')) + 1:03d}"
        db.set_meta(conn, "seq_user", str(int(db.get_meta(conn, "seq_user", "0")) + 1))
        now = db.utcnow()
        conn.execute("INSERT INTO taxonomy_nodes(id, label, description, parent_id, level, source, status, "
                     "created_at, updated_at, created_version) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (nid, clean_label(label, 8, language.get(conn)), description, parent_id, level, source, ACTIVE, now, now,
                      current_version(conn)))
    else:
        nid = _insert_node(conn, level, clean_label(label, 8, language.get(conn)), description, parent_id, source, ACTIVE)
    v = bump_version(conn, f"Category “{label}” created manually")
    record_change(conn, node_id=nid, change_type="create", previous=None,
                  proposed={"label": label, "description": description, "parent_id": parent_id, "level": level},
                  status="accepted", rationale="Manual creation", source="user", run_id=None, version=v)
    events.emit(conn, "taxonomy_edited", f"Category created manually: {label}", node_id=nid)
    return require_node(conn, nid)


def manual_move(conn: sqlite3.Connection, node_id: str, new_parent_id: str) -> dict:
    n = require_node(conn, node_id)
    parent = require_node(conn, new_parent_id)
    if n["level"] < 3:
        raise TaxonomyError("Fixed L1/L2 categories cannot be moved")
    if parent["level"] != n["level"] - 1 or parent["status"] != ACTIVE:
        raise TaxonomyError("Target parent must be an active category one level up")
    v = bump_version(conn, f"“{n['label']}” moved under “{parent['label']}”")
    record_change(conn, node_id=node_id, change_type="move", previous={"parent_id": n["parent_id"]},
                  proposed={"parent_id": new_parent_id}, status="accepted", rationale="Manual move", source="user",
                  run_id=None, version=v)
    conn.execute("UPDATE taxonomy_nodes SET parent_id=?, updated_at=? WHERE id=?", (new_parent_id, db.utcnow(), node_id))
    col = f"l{n['level']}_id"
    for r in conn.execute(f"SELECT id, l4_id, l3_id FROM assignments WHERE {col}=?", (node_id,)).fetchall():
        if r["l4_id"]:
            assignments.repath(conn, r["id"], "user", "path_updated_by_move")
        else:
            before = dict(conn.execute("SELECT * FROM assignments WHERE id=?", (r["id"],)).fetchone())
            path = assignments.path_for_node(conn, r["l3_id"])
            conn.execute("UPDATE assignments SET l1_id=?, l2_id=? WHERE id=?", (path["l1_id"], path["l2_id"], r["id"]))
            assignments._history(conn, r["id"], "user", "path_updated_by_move", assignments.snapshot(before),
                                 {**assignments.snapshot(before), **{k: path[k] for k in ("l1_id", "l2_id")}})
    events.emit(conn, "taxonomy_edited", f"Category moved: {n['label']} → {parent['label']}", node_id=node_id)
    return require_node(conn, node_id)


def manual_retire(conn: sqlite3.Connection, node_id: str) -> dict:
    n = require_node(conn, node_id)
    if n["level"] < 3:
        raise TaxonomyError("Fixed L1/L2 categories cannot be retired here")
    if conn.execute("SELECT 1 FROM taxonomy_nodes WHERE parent_id=? AND status='active'", (node_id,)).fetchone():
        raise TaxonomyError("Retire or move the child categories first")
    v = bump_version(conn, f"“{n['label']}” retired")
    record_change(conn, node_id=node_id, change_type="retire", previous=_snap(n), proposed={"status": "retired"},
                  status="accepted", rationale="Manual retirement", source="user", run_id=None, version=v)
    col = f"l{n['level']}_id"
    for r in conn.execute(f"SELECT id FROM assignments WHERE {col}=? AND review_status='pending'", (node_id,)).fetchall():
        assignments.ai_assign(conn, r["id"], l4_id=None, method="candidate", needs_review=True,
                              review_reason="Category retired", action="unassigned_by_retire")
    _flag_reviewed(conn, n["level"], node_id, "Category retired — please reassign")
    conn.execute("UPDATE taxonomy_nodes SET status='retired', updated_at=? WHERE id=?", (db.utcnow(), node_id))
    events.emit(conn, "taxonomy_edited", f"Category retired: {n['label']}", node_id=node_id)
    return require_node(conn, node_id)


def manual_merge(conn: sqlite3.Connection, source_id: str, target_id: str, settings: config.Settings) -> dict:
    s, t = require_node(conn, source_id), require_node(conn, target_id)
    if s["level"] != t["level"] or s["level"] < 3 or s["id"] == t["id"]:
        raise TaxonomyError("Merge requires two different L3 or two different L4 categories")
    cid = record_change(conn, node_id=source_id, change_type="merge", previous={"source": _snap(s), "target": _snap(t)},
                        proposed={"source_id": source_id, "target_id": target_id, "source_label": s["label"],
                                  "target_label": t["label"], "level": s["level"]},
                        status="proposed", rationale="Manual merge", source="user", run_id=None)
    return accept(conn, cid, actor="user", settings=settings)
