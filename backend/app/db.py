"""SQLite persistence: connections, migrations and small helpers."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from . import config

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

# Serialises structural writes (taxonomy, assignments) between the API and the worker.
write_lock = threading.RLock()

_db_path: Path = config.DB_PATH


def set_db_path(path: Path) -> None:
    global _db_path
    _db_path = Path(path)


def get_db_path() -> Path:
    return _db_path


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: str | None, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def connect() -> sqlite3.Connection:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Explicit transaction; commits on success and rolls back on any exception."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def migrate(conn: sqlite3.Connection) -> list[str]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    applied = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations")}
    newly = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        conn.executescript("BEGIN;" + path.read_text() + ";COMMIT;")
        conn.execute("INSERT INTO schema_migrations(name, applied_at) VALUES (?, ?)", (path.name, utcnow()))
        newly.append(path.name)
    return newly


def init_db() -> None:
    from . import taxonomy  # local import to avoid cycles

    with session() as conn:
        migrate(conn)
        taxonomy.seed_if_empty(conn)
        recover_interrupted(conn)


def recover_interrupted(conn: sqlite3.Connection) -> None:
    """After a restart, mark unfinished runs as interrupted and roll back half-processed interactions."""
    with transaction(conn):
        conn.execute(
            "UPDATE analysis_runs SET status='interrupted', finished_at=? "
            "WHERE status IN ('running','stopping')",
            (utcnow(),),
        )
        stuck = [r["id"] for r in conn.execute("SELECT id FROM interactions WHERE status='processing'")]
        for iid in stuck:
            conn.execute("DELETE FROM intents WHERE interaction_id=?", (iid,))
            conn.execute("UPDATE interactions SET status='pending' WHERE id=?", (iid,))


# --- settings & meta -------------------------------------------------------

def load_settings(conn: sqlite3.Connection | None = None) -> config.Settings:
    s = config.Settings()
    own = conn is None
    conn = conn or connect()
    try:
        for row in conn.execute("SELECT key, value FROM settings"):
            if hasattr(s, row["key"]):
                try:
                    setattr(s, row["key"], config.coerce_setting(row["key"], json.loads(row["value"])))
                except (KeyError, ValueError, TypeError):
                    pass
    finally:
        if own:
            conn.close()
    return s


def save_settings(conn: sqlite3.Connection, values: dict[str, Any]) -> config.Settings:
    with transaction(conn):
        for key, value in values.items():
            coerced = config.coerce_setting(key, value)
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(coerced)),
            )
    return load_settings(conn)


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
