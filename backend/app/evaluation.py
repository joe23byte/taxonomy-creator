"""Optional comparison of the discovered taxonomy with the synthetic ground truth.

This module is only used by the Insights view. The analysis pipeline never imports it,
so ground-truth labels cannot leak into classification.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from . import config

GROUND_TRUTH_PATH = config.SAMPLE_DIR / "sample_ground_truth.json"


def load_ground_truth(path: Path = GROUND_TRUTH_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {c["conversation_id"]: c for c in data.get("conversations", [])}


def compare(conn: sqlite3.Connection, path: Path = GROUND_TRUTH_PATH) -> dict:
    gt = load_ground_truth(path)
    if not gt:
        return {"available": False}
    rows = conn.execute(
        "SELECT x.conversation_id, a.l2_id, a.l4_id, n.label AS l4_label FROM interactions x "
        "JOIN assignments a ON a.interaction_id=x.id LEFT JOIN taxonomy_nodes n ON n.id=a.l4_id "
        "WHERE x.status='processed' AND a.review_status!='unclassified'").fetchall()
    processed = {r[0] for r in conn.execute("SELECT conversation_id FROM interactions WHERE status='processed'")}
    evaluated = [cid for cid in processed if cid in gt]
    if not evaluated:
        return {"available": True, "evaluated": 0}
    per_conv: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    l4_labels: dict[str, str] = {}
    for r in rows:
        if r["l2_id"]:
            per_conv[r["conversation_id"]].append((r["l2_id"], r["l4_id"]))
        if r["l4_id"]:
            l4_labels[r["l4_id"]] = r["l4_label"]

    def paired_l4(cid: str, it: dict) -> set[str]:
        # A ground-truth intent is paired with assignments in its expected L2. Only
        # single-intent conversations fall back to every assignment, so that the
        # second intent of a multi-intent conversation does not distort the mapping.
        same_l2 = {l4 for l2, l4 in per_conv[cid] if l2 == it["l2_id"] and l4}
        if same_l2 or len(gt[cid]["intents"]) > 1:
            return same_l2
        return {l4 for _, l4 in per_conv[cid] if l4}

    l2_hits = l2_total = 0
    type_to_l4: dict[str, Counter] = defaultdict(Counter)
    type_info: dict[str, dict] = {}
    l4_types: dict[str, Counter] = defaultdict(Counter)
    for cid in evaluated:
        assigned_l2 = {l2 for l2, _ in per_conv[cid]}
        for it in gt[cid]["intents"]:
            l2_total += 1
            l2_hits += int(it["l2_id"] in assigned_l2)
            type_info.setdefault(it["key"], {"label": it["label"], "l2_id": it["l2_id"], "count": 0})
            type_info[it["key"]]["count"] += 1
            for l4 in paired_l4(cid, it):
                type_to_l4[it["key"]][l4] += 1
                l4_types[l4][it["key"]] += 1

    # purity: for each L4, share of its paired ground-truth intents that belong to its dominant type
    purity_num = sum(c.most_common(1)[0][1] for c in l4_types.values())
    purity_den = sum(sum(c.values()) for c in l4_types.values())
    l4_convs = {l4 for l4s in per_conv.values() for _, l4 in l4s if l4}

    types = []
    for key, info in sorted(type_info.items(), key=lambda kv: -kv[1]["count"]):
        top = type_to_l4[key].most_common(2)
        types.append({
            "key": key, "label": info["label"], "expected_l2": info["l2_id"], "conversations": info["count"],
            "top_categories": [{"id": nid, "label": l4_labels.get(nid), "conversations": n} for nid, n in top],
            "distinct_categories": len(type_to_l4[key]),
        })
    tags = Counter(t for cid in evaluated for t in gt[cid].get("tags", []))
    return {
        "available": True,
        "evaluated": len(evaluated),
        "ground_truth_types": len(type_info),
        "discovered_l4": len(l4_convs),
        "l2_recall": round(l2_hits / l2_total, 3) if l2_total else None,
        "l4_purity": round(purity_num / purity_den, 3) if purity_den else None,
        "types": types,
        "tags": dict(tags),
        "note": "Synthetic ground truth only; 100 interactions are not enough to claim taxonomy completeness.",
    }
