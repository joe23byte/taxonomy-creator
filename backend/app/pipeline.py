"""Analysis pipeline: per-interaction extraction/matching and batch-level taxonomy refinement.

Durability rules:
- An interaction's intents, assignments and status are committed in one transaction.
- LLM calls happen outside transactions; a failed or malformed call never writes taxonomy data.
- Each cluster decision is committed independently, so an interruption loses at most one step.
"""
from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from typing import Callable

import numpy as np

from . import (assignments, clustering, config, db, embeddings, events, extraction, language, taxonomy,
               taxonomy_builder)
from .ollama_client import OllamaClient, OllamaError, StructuredOutputError

log = logging.getLogger("intent_studio.pipeline")

MAX_REFINEMENTS_PER_BATCH = 4
MAX_SPLITS_PER_BATCH = 2
OUTLIER_CHUNK = 8


def make_client(settings: config.Settings) -> OllamaClient:
    return OllamaClient(settings.ollama_url, timeout=settings.request_timeout)


class Ctx:
    """Per-run context passed through the pipeline."""

    def __init__(self, conn: sqlite3.Connection, client: OllamaClient, settings: config.Settings, run_id: int | None,
                 should_stop: Callable[[], bool] = lambda: False):
        self.conn = conn
        self.client = client
        self.settings = settings
        self.run_id = run_id
        self.th = settings.thresholds()
        self.lang = language.get(conn)
        self.should_stop = should_stop

    def emit(self, kind: str, message: str, **kw) -> None:
        events.emit(self.conn, kind, message, run_id=self.run_id, **kw)

    def step(self, conversation_id: str | None, step: str) -> None:
        if self.run_id:
            self.conn.execute("UPDATE analysis_runs SET current_interaction=?, current_step=? WHERE id=?",
                              (conversation_id, step, self.run_id))


def _l2_lookup(conn: sqlite3.Connection) -> dict[str, dict]:
    return {c["id"]: c for c in taxonomy.base_categories(conn)}


# --- per-interaction processing ------------------------------------------------------------

def process_interaction(ctx: Ctx, row: sqlite3.Row) -> str:
    """Extract, embed and match one interaction. Returns processed | failed | retry."""
    conn, s = ctx.conn, ctx.settings
    cid = row["conversation_id"]
    turns = db.loads(row["turns_json"], [])
    with db.transaction(conn):
        conn.execute("UPDATE interactions SET status='processing', error=NULL WHERE id=?", (row["id"],))
        ctx.step(cid, "Extracting customer intents")
        ctx.emit("extracting", f"Interaction {cid} — Extracting customer intents", conversation_id=cid)

    categories = taxonomy.base_categories(conn)
    try:
        result = extraction.extract_intents(ctx.client, s.llm_model, turns, categories, ctx.lang)
    except StructuredOutputError as e:
        with db.transaction(conn):
            conn.execute("UPDATE interactions SET status='failed', error=? WHERE id=?", (str(e), row["id"]))
            ctx.emit("interaction_failed", f"Interaction {cid} — extraction failed: {e}", level="error",
                     conversation_id=cid)
        return "failed"
    except OllamaError as e:
        with db.transaction(conn):
            conn.execute("UPDATE interactions SET status='pending' WHERE id=?", (row["id"],))
            ctx.emit("warning", f"Interaction {cid} — {e}", level="warning", conversation_id=cid)
        return "retry"

    n = len(result.intents)
    ctx.emit("intents_extracted",
             f"Interaction {cid} — {n} intent{'s' if n != 1 else ''} identified" if n else
             f"Interaction {cid} — no customer intent found", conversation_id=cid,
             level="info" if n else "warning",
             data={"intents": [{"text": i["intent"], "l2_id": i["category_id"]} for i in result.intents]})

    vectors: list[tuple[int, np.ndarray]] = []
    if result.intents:
        ctx.step(cid, "Computing embeddings")
        ctx.emit("embedding", f"Interaction {cid} — Computing embeddings", conversation_id=cid)
        try:
            vectors = embeddings.get_or_create(conn, ctx.client, s.embedding_model, [i["intent"] for i in result.intents])
        except OllamaError as e:
            with db.transaction(conn):
                conn.execute("UPDATE interactions SET status='pending' WHERE id=?", (row["id"],))
                ctx.emit("warning", f"Interaction {cid} — {e}", level="warning", conversation_id=cid)
            return "retry"

    l2s = _l2_lookup(conn)
    with db.write_lock, db.transaction(conn):
        order = conn.execute("SELECT COALESCE(MAX(processed_order), 0) + 1 FROM interactions").fetchone()[0]
        batch_index = (order - 1) // max(1, s.batch_size)
        cent_cache: dict[str, dict[str, np.ndarray]] = {}
        kept_vecs: list[np.ndarray] = []
        summary_parts = []
        for pos, (intent, (eid, vec)) in enumerate(zip(result.intents, vectors or [(None, None)] * n)):
            # in-conversation duplicates (same need phrased twice)
            if vec is not None and any(float(vec @ k) >= 0.95 for k in kept_vecs):
                ctx.emit("info", f"Interaction {cid} — duplicate intent merged: {intent['intent']}", conversation_id=cid)
                continue
            if vec is not None:
                kept_vecs.append(vec)
            cur = conn.execute(
                "INSERT INTO intents(interaction_id, position, intent_text, evidence, evidence_verified, reasoning, "
                "suggested_l2_id, embedding_id, model, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (row["id"], pos, intent["intent"], intent["evidence"], intent["evidence_verified"], intent["reasoning"],
                 intent["category_id"], eid, s.llm_model, db.utcnow()))
            intent_id = cur.lastrowid
            l2_id = intent["category_id"]
            ctx.emit("candidate_extracted", f"Interaction {cid} — Extracted candidate: “{intent['intent']}”",
                     conversation_id=cid, node_id=l2_id, data={"intent_id": intent_id})
            if not l2_id:
                assignments.create(conn, intent_id=intent_id, interaction_id=row["id"], l2_id=None,
                                   method="llm_extraction", needs_review=True,
                                   review_reason="Does not match any existing L1/L2 category")
                ctx.emit("needs_review", f"Interaction {cid} — “{intent['intent']}” does not fit any L1/L2 category",
                         level="warning", conversation_id=cid)
                summary_parts.append("unmatched")
                continue
            evidence_note = None if intent["evidence_verified"] else "Evidence quote not found in transcript"
            if l2_id not in cent_cache:
                cent_cache[l2_id] = embeddings.centroids(conn, l2_id)
            matches = clustering.best_matches(vec, cent_cache[l2_id], top=3) if vec is not None else []
            alts = [{"node_id": m, "similarity": round(sim, 4)} for m, sim in matches]
            if matches and matches[0][1] >= ctx.th["match"]:
                nid, sim = matches[0]
                close_second = len(matches) > 1 and matches[1][1] >= ctx.th["match"] and matches[0][1] - matches[1][1] < 0.02
                reason = evidence_note or ("Two categories are almost equally similar" if close_second else None)
                assignments.create(conn, intent_id=intent_id, interaction_id=row["id"], l2_id=l2_id, l4_id=nid,
                                   method="embedding_match", similarity=sim, alternatives=alts[1:],
                                   needs_review=bool(reason), review_reason=reason)
                node = taxonomy.get_node(conn, nid)
                ctx.emit("matched_existing", f"Interaction {cid} — Matched existing intent: {node['label']} "
                         f"(similarity {sim:.2f})", conversation_id=cid, node_id=nid, level="success",
                         data={"similarity": sim, "intent_id": intent_id})
                summary_parts.append(node["label"])
            else:
                near = matches[0] if matches else None
                assignments.create(conn, intent_id=intent_id, interaction_id=row["id"], l2_id=l2_id,
                                   method="llm_extraction", similarity=near[1] if near else None, alternatives=alts,
                                   needs_review=bool(evidence_note), review_reason=evidence_note)
                pending = (_pending_candidate_similarity(conn, l2_id, vec, row["id"], ctx.th["cluster"])
                           if vec is not None else (0, 0.0))
                msg = f"Interaction {cid} — New intent candidate in {l2s[l2_id]['label']}"
                if near:
                    msg += f" (closest category {near[1]:.2f}, below match threshold {ctx.th['match']:.2f})"
                ctx.emit("candidate_new", msg, conversation_id=cid, node_id=l2_id,
                         data={"intent_id": intent_id, "closest": alts[:1]})
                if pending[0]:
                    ctx.emit("cluster_forming", f"Interaction {cid} — similar to {pending[0]} pending candidate"
                             f"{'s' if pending[0] > 1 else ''} (max similarity {pending[1]:.2f}) — potential new cluster",
                             conversation_id=cid, node_id=l2_id, data={"count": pending[0], "max": pending[1]})
                summary_parts.append("candidate")
        conn.execute(
            "UPDATE interactions SET status='processed', summary=?, no_intent_reason=?, processed_at=?, "
            "processed_order=?, batch_index=? WHERE id=?",
            (result.summary, result.no_intent_reason, db.utcnow(), order, batch_index, row["id"]))
        if n == 0:
            ctx.emit("no_intent", f"Interaction {cid} — no actionable customer intent; marked for review",
                     level="warning", conversation_id=cid, data={"reason": result.no_intent_reason})
        else:
            matched = sum(1 for p in summary_parts if p not in ("candidate", "unmatched"))
            ctx.emit("interaction_assigned", f"Interaction {cid} — processed: {matched} matched, "
                     f"{summary_parts.count('candidate')} new candidate(s)", conversation_id=cid,
                     data={"order": order, "batch": batch_index})
        if ctx.run_id:
            conn.execute("UPDATE analysis_runs SET processed_in_run=processed_in_run+1 WHERE id=?", (ctx.run_id,))
    return "processed"


def _pending_candidate_similarity(conn: sqlite3.Connection, l2_id: str, vec: np.ndarray,
                                  exclude_interaction: int, threshold: float) -> tuple[int, float]:
    rows = conn.execute("SELECT i.embedding_id FROM assignments a JOIN intents i ON i.id=a.intent_id "
                        "WHERE a.l2_id=? AND a.l4_id IS NULL AND a.review_status='pending' AND a.interaction_id!=? "
                        "AND i.embedding_id IS NOT NULL", (l2_id, exclude_interaction)).fetchall()
    vecs = embeddings.load(conn, [r["embedding_id"] for r in rows])
    sims = [float(v @ vec) for v in vecs.values()]
    if not sims:
        return 0, 0.0
    return sum(1 for x in sims if x >= threshold), max(sims)


# --- batch refinement -------------------------------------------------------------------------

def _candidates_by_l2(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    blocked = taxonomy.pending_member_intents(conn)
    rows = conn.execute(
        "SELECT a.id AS aid, a.intent_id, a.l2_id, i.intent_text, i.evidence, i.embedding_id, x.conversation_id "
        "FROM assignments a JOIN intents i ON i.id=a.intent_id JOIN interactions x ON x.id=a.interaction_id "
        "WHERE a.l2_id IS NOT NULL AND a.l4_id IS NULL AND a.review_status='pending' AND i.embedding_id IS NOT NULL "
        "ORDER BY a.id").fetchall()
    vecs = embeddings.load(conn, [r["embedding_id"] for r in rows])
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["intent_id"] in blocked or r["embedding_id"] not in vecs:
            continue
        out[r["l2_id"]].append({**dict(r), "vec": vecs[r["embedding_id"]]})
    return out


def _structure(conn: sqlite3.Connection, l2_id: str) -> tuple[list[dict], dict[str, list[dict]]]:
    l3s = taxonomy.nodes(conn, ("active", "proposed"), level=3, parent_id=l2_id)
    l4_by_l3 = {l3["id"]: taxonomy.nodes(conn, ("active", "proposed"), level=4, parent_id=l3["id"]) for l3 in l3s}
    return l3s, l4_by_l3


def _assign_members_to_existing(ctx: Ctx, members: list[dict], node_id: str, method: str,
                                review_below_match: bool) -> int:
    conn = ctx.conn
    cents = embeddings.centroids(conn)
    cent = cents.get(node_id)
    n = 0
    for m in members:
        sim = float(m["vec"] @ cent) if cent is not None else None
        low = review_below_match and (sim is None or sim < ctx.th["match"])
        if assignments.ai_assign(conn, m["aid"], l4_id=node_id, method=method, similarity=sim, needs_review=low,
                                 review_reason="Assigned by the LLM with low semantic similarity" if low else None,
                                 action="assigned_by_refinement"):
            n += 1
    return n


def _attach_to_proposal(ctx: Ctx, members: list[dict], node: dict) -> bool:
    added = taxonomy.attach_to_pending_create(ctx.conn, node["id"], [m["intent_id"] for m in members])
    if added is None:
        return False
    for m in members:
        ctx.conn.execute("UPDATE assignments SET needs_review=1, review_reason=? WHERE id=? AND review_status='pending'",
                         (f"Waiting for proposed category “{node['label']}” to be reviewed", m["aid"]))
    ctx.emit("needs_review", f"{len(members)} intent(s) added to proposed category “{node['label']}” — assigned "
             f"once the proposal is accepted", level="warning", node_id=node["id"],
             data={"intent_ids": [m["intent_id"] for m in members]})
    return True


def _cluster_similarity(conn: sqlite3.Connection, members: list[dict], node_id: str | None) -> float | None:
    cent = embeddings.centroids(conn).get(node_id) if node_id else None
    if cent is None:
        return None
    centroid = embeddings.normalize(np.mean([m["vec"] for m in members], axis=0)[None, :])[0]
    return float(centroid @ cent)


def _conflict_for(ctx: Ctx, l2_id: str, centroid: np.ndarray, label: str) -> str | None:
    cents = embeddings.centroids(ctx.conn, l2_id)
    best = clustering.best_matches(centroid, cents, top=1)
    if best and best[0][1] >= ctx.th["merge"]:
        node = taxonomy.get_node(ctx.conn, best[0][0])
        return f"Very similar to existing category “{node['label']}” (similarity {best[0][1]:.2f})"
    for n in taxonomy.nodes(ctx.conn, ("active", "proposed"), level=4):
        if taxonomy.norm_label(n["label"]) == taxonomy.norm_label(label):
            path = assignments.path_for_node(ctx.conn, n["id"])
            if path["l2_id"] != l2_id:
                return f"Same label already exists in another L2 ({n['id']})"
    return None


def _create_from_decision(ctx: Ctx, l2_id: str, decision: taxonomy_builder.Decision, members: list[dict],
                          cluster_info: dict, doubt: str | None = None) -> dict | None:
    conn = ctx.conn
    # identical label inside this L2 → treat as the existing category
    for n in taxonomy.nodes(conn, ("active",), level=4):
        if taxonomy.norm_label(n["label"]) == taxonomy.norm_label(decision.l4_label) and \
                assignments.path_for_node(conn, n["id"])["l2_id"] == l2_id:
            assigned = _assign_members_to_existing(ctx, members, n["id"], "llm_cluster_match", review_below_match=True)
            ctx.emit("matched_existing", f"Cluster of {len(members)} matched existing intent: {n['label']}",
                     node_id=n["id"], level="success", data={"assigned": assigned})
            return None
    centroid = embeddings.normalize(np.mean([m["vec"] for m in members], axis=0)[None, :])[0]
    conflict = _conflict_for(ctx, l2_id, centroid, decision.l4_label) or doubt
    l3 = ({"existing_id": decision.l3_existing_id} if decision.l3_existing_id
          else {"label": decision.l3_label, "description": decision.l3_description})
    return taxonomy.propose_create(
        conn, l2_id=l2_id, l3=l3, l4={"label": decision.l4_label, "description": decision.l4_description},
        member_intent_ids=[m["intent_id"] for m in members], cluster_info=cluster_info,
        rationale=decision.rationale, run_id=ctx.run_id,
        auto_accept=ctx.settings.auto_accept_new_categories, conflict=conflict, settings=ctx.settings)


def cluster_l2(ctx: Ctx, l2: dict, cands: list[dict], stats: dict) -> None:
    conn = ctx.conn
    X = np.stack([c["vec"] for c in cands])
    res = clustering.cluster_candidates(X, ctx.th["cluster"])
    with db.transaction(conn):
        ctx.emit("info", f"{l2['label']}: {len(cands)} open candidates → {len(res.clusters)} cluster(s), "
                 f"{len(res.outliers)} outlier(s) [{res.method}]", node_id=l2["id"],
                 data={"method": res.method, "clusters": [len(c.members) for c in res.clusters],
                       "outliers": len(res.outliers)})
    for cl in res.clusters:
        if ctx.should_stop():
            return
        members = [cands[i] for i in cl.members]
        statements = [m["intent_text"] for m in members]
        cluster_info = {"size": len(members), "cohesion": round(cl.cohesion, 4), "method": cl.method,
                        "examples": statements[:6]}
        with db.transaction(conn):
            ctx.step(None, f"Naming cluster in {l2['label']}")
            ctx.emit("cluster_discovered", f"New cluster discovered in {l2['label']}: {len(members)} similar intents "
                     f"(cohesion {cl.cohesion:.2f})", node_id=l2["id"], data=cluster_info)
        l3s, l4_by_l3 = _structure(conn, l2["id"])
        try:
            decision = taxonomy_builder.name_cluster(ctx.client, ctx.settings.llm_model, l2, l3s, l4_by_l3, statements,
                                                     [m["evidence"] for m in members if m["evidence"]], lang=ctx.lang)
        except OllamaError as e:
            with db.transaction(conn):
                ctx.emit("warning", f"Cluster naming failed in {l2['label']} ({e}); candidates kept for review",
                         level="warning", node_id=l2["id"])
            continue
        if decision is None:
            with db.transaction(conn):
                ctx.emit("warning", f"Model returned an unusable category for a cluster in {l2['label']}; "
                         f"candidates kept", level="warning", node_id=l2["id"])
            continue
        doubt = None
        if decision.kind == "existing":
            # The LLM tends to reuse categories. If the group is semantically far from the chosen
            # category, ask again without it; the alternative then always goes to human review,
            # so neither the reuse nor the new category is applied on the model's word alone.
            sim = _cluster_similarity(conn, members, decision.existing_l4_id)
            if sim is not None and sim < ctx.th["match"]:
                chosen = taxonomy.get_node(conn, decision.existing_l4_id)
                try:
                    alt = taxonomy_builder.name_cluster(
                        ctx.client, ctx.settings.llm_model, l2, l3s, l4_by_l3, statements,
                        [m["evidence"] for m in members if m["evidence"]], exclude_l4={chosen["id"]: sim}, lang=ctx.lang)
                except OllamaError:
                    alt = None
                if alt is not None:
                    doubt = (f"The model first matched this group to “{chosen['label']}”, but its semantic "
                             f"similarity is only {sim:.2f}; confirm that it is a distinct intent")
                    with db.transaction(conn):
                        ctx.emit("info", f"Cluster in {l2['label']} is semantically distant from "
                                 f"“{chosen['label']}” ({sim:.2f}); asked the model for an alternative",
                                 node_id=chosen["id"], data={"similarity": round(sim, 4)})
                    decision = alt
        with db.write_lock, db.transaction(conn):
            if decision.kind == "existing":
                node = taxonomy.get_node(conn, decision.existing_l4_id)
                if node and node["status"] == "active":
                    n = _assign_members_to_existing(ctx, members, node["id"], "llm_cluster_match", review_below_match=True)
                    ctx.emit("matched_existing", f"Cluster of {len(members)} matched existing intent: {node['label']}",
                             node_id=node["id"], level="success", data={"assigned": n, "rationale": decision.rationale})
                elif node and node["status"] == "proposed":
                    _attach_to_proposal(ctx, members, node)
                continue
            out = _create_from_decision(ctx, l2["id"], decision, members, cluster_info, doubt=doubt)
            if out:
                stats["proposals"] += 1
                if out["accepted"]:
                    stats["new_l4"] += 1
                    stats["new_l3"] += int(out["l3_new"])


def outlier_pass(ctx: Ctx, l2: dict, cands: list[dict], stats: dict) -> None:
    conn = ctx.conn
    with db.transaction(conn):
        ctx.emit("outlier_pass", f"{l2['label']}: reviewing {len(cands)} rare intent(s) that did not form a cluster",
                 node_id=l2["id"])
    for start in range(0, len(cands), OUTLIER_CHUNK):
        if ctx.should_stop():
            return
        chunk = cands[start:start + OUTLIER_CHUNK]
        l3s, l4_by_l3 = _structure(conn, l2["id"])
        try:
            decisions = taxonomy_builder.place_outliers(ctx.client, ctx.settings.llm_model, l2, l3s, l4_by_l3,
                                                        [c["intent_text"] for c in chunk], lang=ctx.lang)
        except OllamaError as e:
            with db.transaction(conn):
                ctx.emit("warning", f"Outlier review failed in {l2['label']} ({e})", level="warning", node_id=l2["id"])
            continue
        groups: dict[str, list[int]] = defaultdict(list)
        with db.write_lock, db.transaction(conn):
            for idx, c in enumerate(chunk):
                action, dec = decisions.get(idx, ("unclassified", None))
                if action == "existing" and dec:
                    node = taxonomy.get_node(conn, dec.existing_l4_id)
                    if node and node["status"] == "active":
                        _assign_members_to_existing(ctx, [c], node["id"], "llm_outlier", review_below_match=True)
                        ctx.emit("matched_existing", f"Interaction {c['conversation_id']} — rare intent placed in "
                                 f"{node['label']}", conversation_id=c["conversation_id"], node_id=node["id"])
                        continue
                    if node and node["status"] == "proposed" and _attach_to_proposal(ctx, [c], node):
                        continue
                    action = "unclassified"
                if action == "new" and dec:
                    groups[taxonomy.norm_label(dec.l4_label)].append(idx)
                    continue
                conn.execute("UPDATE assignments SET needs_review=1, review_reason=? WHERE id=? AND review_status='pending'",
                             ("No suitable L3/L4 category found — needs human review", c["aid"]))
                ctx.emit("needs_review", f"Interaction {c['conversation_id']} — “{c['intent_text']}” left for human "
                         f"review", level="warning", conversation_id=c["conversation_id"], node_id=l2["id"])
            for _, idxs in groups.items():
                dec = decisions[idxs[0]][1]
                members = [chunk[i] for i in idxs]
                info = {"size": len(members), "cohesion": None, "method": "llm_outlier",
                        "examples": [m["intent_text"] for m in members]}
                out = _create_from_decision(ctx, l2["id"], dec, members, info)
                if out:
                    stats["proposals"] += 1
                    if out["accepted"]:
                        stats["new_l4"] += 1
                        stats["new_l3"] += int(out["l3_new"])


def detect_overlaps(ctx: Ctx) -> int:
    conn = ctx.conn
    created = 0
    with db.write_lock, db.transaction(conn):
        for l2 in taxonomy.base_categories(conn):
            member_vecs = embeddings.node_member_vectors(conn, l2["id"])
            cents = {k: embeddings.normalize(np.mean([v for _, v in vs], axis=0)[None, :])[0]
                     for k, vs in member_vecs.items()}
            ids = sorted(cents, key=lambda k: -len(member_vecs[k]))
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    sim = float(cents[a] @ cents[b])
                    if sim >= ctx.th["merge"]:
                        if taxonomy.propose_merge(conn, b, a, sim, f"Category centroids are highly similar "
                                                  f"({sim:.2f} ≥ {ctx.th['merge']:.2f})", ctx.run_id):
                            created += 1
            # L3 level: compare sub-topic centroids
            l3_vecs: dict[str, list[np.ndarray]] = defaultdict(list)
            for l4, vs in member_vecs.items():
                parent = taxonomy.get_node(conn, l4)["parent_id"]
                l3_vecs[parent].extend(v for _, v in vs)
            l3c = {k: embeddings.normalize(np.mean(v, axis=0)[None, :])[0] for k, v in l3_vecs.items() if v}
            l3ids = sorted(l3c, key=lambda k: -len(l3_vecs[k]))
            for i, a in enumerate(l3ids):
                for b in l3ids[i + 1:]:
                    sim = float(l3c[a] @ l3c[b])
                    if sim >= ctx.th["merge"]:
                        if taxonomy.propose_merge(conn, b, a, sim, f"L3 sub-topics overlap ({sim:.2f})", ctx.run_id):
                            created += 1
    return created


def refine_descriptions(ctx: Ctx) -> int:
    conn = ctx.conn
    member_vecs = embeddings.node_member_vectors(conn)
    done = 0
    for nid, members in sorted(member_vecs.items(), key=lambda kv: -len(kv[1])):
        if done >= MAX_REFINEMENTS_PER_BATCH or ctx.should_stop():
            break
        node = taxonomy.get_node(conn, nid)
        support = len(members)
        if node["source"] != "ai" or support < 3 or support < 2 * max(1, node["support_at_description"]):
            continue
        aids = [a for a, _ in members][:20]
        texts = [r[0] for r in conn.execute(
            f"SELECT i.intent_text FROM assignments a JOIN intents i ON i.id=a.intent_id WHERE a.id IN "
            f"({','.join('?' * len(aids))})", aids)]
        try:
            desc = taxonomy_builder.refine_description(ctx.client, ctx.settings.llm_model, node["label"],
                                                       node["description"], texts, lang=ctx.lang)
        except OllamaError:
            continue
        if desc and desc != node["description"]:
            with db.write_lock, db.transaction(conn):
                taxonomy.apply_refinement(conn, nid, desc, support, f"Support grew from "
                                          f"{node['support_at_description']} to {support} intents", ctx.run_id)
            done += 1
    return done


def detect_splits(ctx: Ctx) -> int:
    conn = ctx.conn
    member_vecs = embeddings.node_member_vectors(conn)
    made = 0
    for nid, members in member_vecs.items():
        if made >= MAX_SPLITS_PER_BATCH or len(members) < 8 or taxonomy.split_already_proposed(conn, nid):
            continue
        X = np.stack([v for _, v in members])
        groups = clustering.find_subclusters(X, ctx.th["cluster"], separation=ctx.th["match"])
        if not groups:
            continue
        aids = [a for a, _ in members]
        info = {r["id"]: (r["intent_id"], r["intent_text"]) for r in conn.execute(
            f"SELECT a.id, a.intent_id, i.intent_text FROM assignments a JOIN intents i ON i.id=a.intent_id "
            f"WHERE a.id IN ({','.join('?' * len(aids))})", aids)}
        text_groups = [[info[aids[i]][1] for i in g] for g in groups]
        node = taxonomy.get_node(conn, nid)
        try:
            out = taxonomy_builder.propose_split_labels(ctx.client, ctx.settings.llm_model, node["label"],
                                                        node["description"], text_groups, lang=ctx.lang)
        except OllamaError:
            continue
        if not out:
            continue
        parts = []
        for p in out.parts:
            if 0 <= p.group < len(groups) and all(x["group"] != p.group for x in parts):
                parts.append({"group": p.group, "label": p.label, "description": p.description,
                              "member_intent_ids": [info[aids[i]][0] for i in groups[p.group]]})
        with db.write_lock, db.transaction(conn):
            taxonomy.propose_split(conn, nid, parts, out.rationale or "Distinct sub-groups detected", ctx.run_id)
        made += 1
    return made


def refine(ctx: Ctx, batch_index: int, final: bool, label: str | None = None) -> dict:
    conn = ctx.conn
    stats = {"new_l3": 0, "new_l4": 0, "proposals": 0}
    with db.transaction(conn):
        ctx.step(None, "Refining L3/L4 taxonomy")
        ctx.emit("batch_refinement", label or f"Batch {batch_index + 1} completed — Refining L3/L4 taxonomy",
                 data={"batch": batch_index, "final": final})
    l2s = _l2_lookup(conn)
    for l2_id, cands in _candidates_by_l2(conn).items():
        if ctx.should_stop():
            break
        if l2_id in l2s:
            cluster_l2(ctx, l2s[l2_id], cands, stats)
    if final and not ctx.should_stop():
        for l2_id, cands in _candidates_by_l2(conn).items():
            if l2_id in l2s and cands:
                outlier_pass(ctx, l2s[l2_id], cands, stats)
    with db.write_lock, db.transaction(conn):
        rematched = sum(taxonomy.rematch_candidates(conn, l2, ctx.settings, ctx.run_id) for l2 in l2s)
    overlaps = detect_overlaps(ctx)
    refined = refine_descriptions(ctx)
    splits = detect_splits(ctx)
    stats["proposals"] += overlaps + splits
    with db.transaction(conn):
        processed = conn.execute("SELECT COUNT(*) FROM interactions WHERE status='processed'").fetchone()[0]
        last_refined = int(db.get_meta(conn, "last_refined_order", "0"))
        max_order = conn.execute("SELECT COALESCE(MAX(processed_order), 0) FROM interactions").fetchone()[0]
        in_batch = max_order - last_refined
        intents_in_batch = conn.execute(
            "SELECT COUNT(*) FROM intents i JOIN interactions x ON x.id=i.interaction_id WHERE x.processed_order > ?",
            (last_refined,)).fetchone()[0]
        total_l3 = conn.execute("SELECT COUNT(*) FROM taxonomy_nodes WHERE level=3 AND status='active'").fetchone()[0]
        total_l4 = conn.execute("SELECT COUNT(*) FROM taxonomy_nodes WHERE level=4 AND status='active'").fetchone()[0]
        conn.execute("INSERT INTO batch_stats(run_id, batch_index, processed_total, interactions_in_batch, "
                     "intents_extracted, new_l3, new_l4, total_l3, total_l4, proposals_created, created_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (ctx.run_id, batch_index, processed, in_batch, intents_in_batch, stats["new_l3"], stats["new_l4"],
                      total_l3, total_l4, stats["proposals"], db.utcnow()))
        db.set_meta(conn, "last_refined_order", str(max_order))
        ctx.emit("info", f"Refinement finished: {stats['new_l4']} new L4, {stats['new_l3']} new L3, "
                 f"{rematched} candidates re-matched, {overlaps} overlap(s), {refined} description(s) refined",
                 level="success", data={**stats, "rematched": rematched, "overlaps": overlaps, "refined": refined,
                                        "splits": splits, "total_l3": total_l3, "total_l4": total_l4})
    return stats
