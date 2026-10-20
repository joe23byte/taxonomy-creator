"""Transcript import: JSON (canonical), CSV, Excel and TXT → one normalized representation.

Canonical record::

    {"conversation_id": str, "channel": str|None, "segment": str|None, "language": str|None,
     "timestamp": str|None, "queue": str|None, "turns": [{"speaker": "customer"|"agent"|"system", "text": str}],
     "metadata": {...}}

The structure intentionally mirrors what can be derived from Genesys Cloud conversation
exports so an API connector can feed the same normaliser later.
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from . import db

FIELDS = ["conversation_id", "channel", "segment", "language", "timestamp", "queue"]
MAPPABLE = FIELDS + ["transcript", "speaker", "text"]

SPEAKER_ALIASES = {
    "customer": "customer", "client": "customer", "caller": "customer", "user": "customer", "kunde": "customer",
    "external": "customer", "c": "customer", "cust": "customer", "consumer": "customer",
    "agent": "agent", "rep": "agent", "advisor": "agent", "operator": "agent", "support": "agent", "a": "agent",
    "internal": "agent", "employee": "agent", "mitarbeiter": "agent",
    "system": "system", "bot": "system", "ivr": "system", "acd": "system",
}

COLUMN_GUESSES = {
    "conversation_id": ["conversation_id", "conversationid", "conversation", "id", "interaction_id", "call_id", "case_id"],
    "channel": ["channel", "media_type", "mediatype", "medium"],
    "segment": ["segment", "customer_segment", "plan_type", "contract_type"],
    "language": ["language", "lang", "locale"],
    "timestamp": ["timestamp", "start_time", "date", "datetime", "created_at", "conversation_start"],
    "queue": ["queue", "queue_name", "skill"],
    "transcript": ["transcript", "conversation_text", "dialogue", "text_full", "body", "content"],
    "speaker": ["speaker", "role", "participant", "participant_purpose", "from"],
    "text": ["text", "message", "utterance", "turn_text"],
}

LINE_RE = re.compile(r"^\s*\[?([A-Za-zÄÖÜäöü ]{1,20})\]?\s*[:：]\s*(.+)$")


class ImportErrorSafe(ValueError):
    pass


@dataclass
class ParseResult:
    format: str
    records: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    mapping: dict[str, str | None] = field(default_factory=dict)
    needs_mapping: bool = False


def normalize_speaker(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in SPEAKER_ALIASES:
        return SPEAKER_ALIASES[v]
    first = v.split(" ")[0] if v else ""
    if first in SPEAKER_ALIASES:
        return SPEAKER_ALIASES[first]
    return "agent" if "agent" in v else "customer"


def parse_transcript_text(text: str) -> list[dict]:
    """Parse 'Speaker: text' lines; unlabelled text becomes one customer turn."""
    turns: list[dict] = []
    for raw in str(text or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        m = LINE_RE.match(line)
        if m and m.group(1).strip().lower() in SPEAKER_ALIASES:
            turns.append({"speaker": normalize_speaker(m.group(1)), "text": m.group(2).strip()})
        elif turns:
            turns[-1]["text"] += " " + line
        else:
            turns.append({"speaker": "customer", "text": line})
    return turns


def _clean(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    s = str(v).strip()
    return s or None


def normalize_record(raw: dict, index: int, issues: list[dict]) -> dict | None:
    rec: dict[str, Any] = {k: _clean(raw.get(k)) for k in FIELDS}
    turns_in = raw.get("turns")
    turns: list[dict] = []
    if isinstance(turns_in, list):
        for t in turns_in:
            if isinstance(t, dict) and _clean(t.get("text")):
                turns.append({"speaker": normalize_speaker(t.get("speaker") or t.get("role")), "text": _clean(t["text"])})
            elif isinstance(t, str) and t.strip():
                turns.extend(parse_transcript_text(t))
    elif _clean(raw.get("transcript")):
        turns = parse_transcript_text(raw["transcript"])
    label = rec["conversation_id"] or f"record {index + 1}"
    if not turns:
        issues.append({"level": "error", "record": label, "message": "No transcript turns — skipped"})
        return None
    if not any(t["speaker"] == "customer" for t in turns):
        issues.append({"level": "warning", "record": label, "message": "No customer turn detected"})
    if rec["channel"]:
        rec["channel"] = rec["channel"].lower().replace(" ", "_")
    if rec["segment"]:
        rec["segment"] = rec["segment"].lower()
    rec["turns"] = turns
    known = set(FIELDS) | {"turns", "transcript"}
    rec["metadata"] = {k: v for k, v in raw.items() if k not in known and _clean(v) is not None and not isinstance(v, (list, dict))}
    return rec


def guess_mapping(columns: list[str]) -> dict[str, str | None]:
    lower = {c.lower().strip().replace(" ", "_"): c for c in columns}
    mapping: dict[str, str | None] = {}
    for target, options in COLUMN_GUESSES.items():
        mapping[target] = next((lower[o] for o in options if o in lower), None)
    if mapping.get("transcript") and mapping.get("text") == mapping.get("transcript"):
        mapping["text"] = None
    return mapping


def records_from_dataframe(df: pd.DataFrame, mapping: dict[str, str | None], issues: list[dict]) -> list[dict]:
    df = df.copy()
    m = {k: v for k, v in mapping.items() if v and v in df.columns}
    if m.get("speaker") and m.get("text"):
        if not m.get("conversation_id"):
            raise ImportErrorSafe("Turn-level files need a conversation ID column")
        raws = []
        for cid, grp in df.groupby(m["conversation_id"], sort=False):
            first = grp.iloc[0]
            raw = {k: first[c] for k, c in m.items() if k in FIELDS}
            raw["conversation_id"] = cid
            raw["turns"] = [{"speaker": r[m["speaker"]], "text": r[m["text"]]} for _, r in grp.iterrows()]
            raws.append(raw)
    elif m.get("transcript"):
        raws = []
        for _, row in df.iterrows():
            raw = {k: row[c] for k, c in m.items() if k in FIELDS}
            raw["transcript"] = row[m["transcript"]]
            for c in df.columns:
                if c not in m.values():
                    raw[c] = row[c]
            raws.append(raw)
    else:
        raise ImportErrorSafe("Map either a transcript column, or speaker + text columns")
    out = []
    for i, raw in enumerate(raws):
        rec = normalize_record(raw, i, issues)
        if rec:
            out.append(rec)
    return out


def parse_upload(files: list[tuple[str, bytes]], mapping: dict[str, str | None] | None = None,
                 txt_separator: str | None = None) -> ParseResult:
    if not files:
        raise ImportErrorSafe("No file uploaded")
    exts = {name.rsplit(".", 1)[-1].lower() if "." in name else "txt" for name, _ in files}
    if len(exts) > 1:
        raise ImportErrorSafe("Upload files of a single format at a time")
    ext = exts.pop()
    issues: list[dict] = []
    if ext == "json":
        if len(files) != 1:
            raise ImportErrorSafe("Upload one JSON file at a time")
        try:
            data = json.loads(files[0][1].decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ImportErrorSafe(f"Invalid JSON file ({type(e).__name__} at position {getattr(e, 'pos', '?')})") from None
        if isinstance(data, dict):
            data = data.get("conversations") or data.get("interactions") or [data]
        if not isinstance(data, list):
            raise ImportErrorSafe("JSON must be a list of conversations")
        recs = [r for i, item in enumerate(data) if isinstance(item, dict) and (r := normalize_record(item, i, issues))]
        return _finish(ParseResult("json", recs, issues))
    if ext in ("csv", "xlsx", "xls"):
        if len(files) != 1:
            raise ImportErrorSafe("Upload one table file at a time")
        try:
            if ext == "csv":
                df = pd.read_csv(io.BytesIO(files[0][1]), dtype=str, keep_default_na=False, sep=None, engine="python")
            else:
                df = pd.read_excel(io.BytesIO(files[0][1]), dtype=str).fillna("")
        except Exception as e:
            raise ImportErrorSafe(f"Could not read the table ({type(e).__name__})") from None
        cols = [str(c) for c in df.columns]
        df.columns = cols
        used = mapping or guess_mapping(cols)
        res = ParseResult("excel" if ext != "csv" else "csv", columns=cols, mapping=used)
        try:
            res.records = records_from_dataframe(df, used, issues)
        except ImportErrorSafe as e:
            res.needs_mapping = True
            issues.append({"level": "error", "record": None, "message": str(e)})
        res.issues = issues
        return _finish(res)
    if ext == "txt":
        recs = []
        for fi, (name, content) in enumerate(files):
            text = content.decode("utf-8-sig", errors="replace")
            chunks = text.split(txt_separator) if txt_separator else [text]
            stem = re.sub(r"[^A-Za-z0-9_-]+", "-", name.rsplit(".", 1)[0])[:40] or "txt"
            for ci, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                cid = stem if len(chunks) == 1 else f"{stem}-{ci + 1:03d}"
                rec = normalize_record({"conversation_id": cid, "transcript": chunk, "channel": None}, ci, issues)
                if rec:
                    recs.append(rec)
        return _finish(ParseResult("txt", recs, issues))
    raise ImportErrorSafe(f"Unsupported file type .{ext} (use JSON, CSV, XLSX or TXT)")


def _finish(res: ParseResult) -> ParseResult:
    seen: set[str] = set()
    for i, r in enumerate(res.records):
        if not r["conversation_id"]:
            r["conversation_id"] = f"IMPORT-{i + 1:05d}"
            res.issues.append({"level": "info", "record": r["conversation_id"], "message": "Missing conversation ID — generated"})
        if r["conversation_id"] in seen:
            new = f"{r['conversation_id']}-dup{i}"
            res.issues.append({"level": "warning", "record": r["conversation_id"], "message": f"Duplicate ID renamed to {new}"})
            r["conversation_id"] = new
        seen.add(r["conversation_id"])
    missing = [f for f in ("channel", "segment") if not any(r.get(f) for r in res.records)]
    if res.records and missing:
        res.issues.append({"level": "info", "record": None, "message": f"No {', '.join(missing)} metadata — continuing without it"})
    return res


def commit(conn: sqlite3.Connection, name: str, fmt: str, records: list[dict]) -> dict:
    existing = {r[0] for r in conn.execute("SELECT conversation_id FROM interactions")}
    new = [r for r in records if r["conversation_id"] not in existing]
    skipped = len(records) - len(new)
    with db.transaction(conn):
        cur = conn.execute("INSERT INTO imports(name, source_format, interaction_count, created_at) VALUES (?,?,?,?)",
                           (name, fmt, len(new), db.utcnow()))
        import_id = cur.lastrowid
        seq = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM interactions").fetchone()[0]
        for r in new:
            seq += 1
            conn.execute(
                "INSERT INTO interactions(conversation_id, import_id, seq, channel, segment, language, timestamp, queue, "
                "turns_json, metadata_json, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?, 'pending', ?)",
                (r["conversation_id"], import_id, seq, r.get("channel"), r.get("segment"), r.get("language"),
                 r.get("timestamp"), r.get("queue"), db.dumps(r["turns"]), db.dumps(r.get("metadata", {})), db.utcnow()),
            )
    return {"import_id": import_id, "imported": len(new), "skipped_existing": skipped}


def preview_payload(res: ParseResult, limit: int = 5) -> dict:
    turn_counts = [len(r["turns"]) for r in res.records]
    return {
        "format": res.format,
        "total": len(res.records),
        "columns": res.columns,
        "mapping": res.mapping,
        "needs_mapping": res.needs_mapping,
        "issues": res.issues[:100],
        "issue_counts": {lvl: sum(1 for i in res.issues if i["level"] == lvl) for lvl in ("error", "warning", "info")},
        "stats": {
            "avg_turns": round(sum(turn_counts) / len(turn_counts), 1) if turn_counts else 0,
            "channels": sorted({r["channel"] for r in res.records if r.get("channel")}),
            "segments": sorted({r["segment"] for r in res.records if r.get("segment")}),
        },
        "preview": [{**{k: r.get(k) for k in FIELDS}, "turns": r["turns"][:4], "turn_count": len(r["turns"])}
                    for r in res.records[:limit]],
    }
