"""Embedding generation with a persistent SQLite cache (no recomputation for known texts)."""
from __future__ import annotations

import hashlib
import sqlite3

import numpy as np

from . import db
from .ollama_client import OllamaClient

# qwen3-embedding is instruction-aware; one shared instruction keeps vectors comparable.
INSTRUCTION = ("Instruct: Given a customer service intent, identify the specific underlying problem or request, "
               "distinguishing it from related problems in the same topic\nQuery: ")


def prepare(text: str) -> str:
    return INSTRUCTION + " ".join(text.split())


def text_hash(text: str) -> str:
    return hashlib.sha256(prepare(text).encode("utf-8")).hexdigest()


def normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    n[n == 0] = 1.0
    return v / n


def get_or_create(conn: sqlite3.Connection, client: OllamaClient | None, model: str,
                  texts: list[str]) -> list[tuple[int, np.ndarray]]:
    """Return (embedding_id, unit vector) per text, calling Ollama only for unseen texts."""
    hashes = [text_hash(t) for t in texts]
    found: dict[str, tuple[int, np.ndarray]] = {}
    for h in set(hashes):
        row = conn.execute("SELECT id, vector FROM embeddings WHERE model=? AND text_hash=?", (model, h)).fetchone()
        if row:
            found[h] = (row["id"], np.frombuffer(row["vector"], dtype=np.float32))
    missing = [(h, t) for h, t in zip(hashes, texts) if h not in found]
    # de-duplicate while preserving order
    uniq: dict[str, str] = {}
    for h, t in missing:
        uniq.setdefault(h, t)
    if uniq:
        if client is None:
            raise RuntimeError("Embedding client required for uncached texts")
        vectors = client.embed(model, [prepare(t) for t in uniq.values()])
        for (h, _), vec in zip(uniq.items(), vectors):
            arr = normalize(np.asarray(vec, dtype=np.float32)[None, :])[0].astype(np.float32)
            cur = conn.execute(
                "INSERT OR IGNORE INTO embeddings(model, text_hash, dim, vector, created_at) VALUES (?,?,?,?,?)",
                (model, h, int(arr.shape[0]), arr.tobytes(), db.utcnow()),
            )
            eid = cur.lastrowid
            if not cur.rowcount:
                eid = conn.execute("SELECT id FROM embeddings WHERE model=? AND text_hash=?", (model, h)).fetchone()["id"]
            found[h] = (int(eid), arr)
    return [found[h] for h in hashes]


def load(conn: sqlite3.Connection, embedding_ids: list[int]) -> dict[int, np.ndarray]:
    out: dict[int, np.ndarray] = {}
    ids = [i for i in set(embedding_ids) if i is not None]
    for chunk_start in range(0, len(ids), 500):
        chunk = ids[chunk_start:chunk_start + 500]
        q = f"SELECT id, vector FROM embeddings WHERE id IN ({','.join('?' * len(chunk))})"
        for r in conn.execute(q, chunk):
            out[r["id"]] = np.frombuffer(r["vector"], dtype=np.float32)
    return out


def node_member_vectors(conn: sqlite3.Connection, l2_id: str | None = None) -> dict[str, list[tuple[int, np.ndarray]]]:
    """Map active L4 id -> [(assignment_id, vector)] for assignments that count as evidence."""
    sql = ("SELECT a.id AS aid, a.l4_id, i.embedding_id FROM assignments a JOIN intents i ON i.id=a.intent_id "
           "JOIN taxonomy_nodes n ON n.id=a.l4_id WHERE n.status='active' AND a.review_status!='unclassified' "
           "AND i.embedding_id IS NOT NULL")
    params: list = []
    if l2_id:
        sql += " AND a.l2_id=?"
        params.append(l2_id)
    rows = conn.execute(sql, params).fetchall()
    vecs = load(conn, [r["embedding_id"] for r in rows])
    out: dict[str, list[tuple[int, np.ndarray]]] = {}
    for r in rows:
        if r["embedding_id"] in vecs:
            out.setdefault(r["l4_id"], []).append((r["aid"], vecs[r["embedding_id"]]))
    return out


def centroids(conn: sqlite3.Connection, l2_id: str | None = None) -> dict[str, np.ndarray]:
    return {nid: normalize(np.mean([v for _, v in members], axis=0)[None, :])[0]
            for nid, members in node_member_vectors(conn, l2_id).items() if members}
