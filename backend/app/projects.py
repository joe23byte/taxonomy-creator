"""Projects: each project is an independent workspace with its own SQLite database.

A small JSON registry next to the databases lists the projects and the active one. The API
and the worker always work on the active project's database (``db.get_db_path()``).
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
from pathlib import Path

from . import db

_lock = threading.Lock()


class ProjectError(ValueError):
    """Safe-to-display project error."""


_state: dict[str, Path | None] = {"registry": None}


def _load() -> dict:
    path = _state["registry"]
    if path and path.exists():
        return json.loads(path.read_text())
    return {"active": None, "projects": []}


def _save(data: dict) -> None:
    path = _state["registry"]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


def data_dir() -> Path:
    """Directory of the project registry; holds app-wide files such as the branding logo."""
    return (_state["registry"] or db.get_db_path().parent / "projects.json").parent


def _db_file(project: dict) -> Path:
    p = Path(project["db"])
    return p if p.is_absolute() else _state["registry"].parent / p


def init() -> dict:
    """Load the registry next to the current database; register that database as the first project if needed."""
    current = db.get_db_path()
    _state["registry"] = current.parent / "projects.json"
    with _lock:
        data = _load()
        if not data["projects"]:
            name = "Default project"
            if current.exists():
                with db.session() as conn:
                    db.migrate(conn)
                    row = conn.execute("SELECT name FROM imports ORDER BY id LIMIT 1").fetchone()
                    if row:
                        name = re.sub(r"\s*\(\d+\)$", "", row["name"]) or name
            pid = secrets.token_hex(4)
            data = {"active": pid, "projects": [{"id": pid, "name": name, "description": "",
                                                 "db": current.name, "created_at": db.utcnow()}]}
            _save(data)
        active = next((p for p in data["projects"] if p["id"] == data["active"]), data["projects"][0])
        db.set_db_path(_db_file(active))
    db.init_db()
    return active


def active() -> dict:
    data = _load()
    return next(p for p in data["projects"] if p["id"] == data["active"])


def _stats(path: Path) -> dict:
    if not path.exists():
        return {}
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        run = conn.execute("SELECT status, started_at, finished_at FROM analysis_runs ORDER BY id DESC LIMIT 1").fetchone()
        last_import = conn.execute("SELECT name, created_at FROM imports ORDER BY id DESC LIMIT 1").fetchone()
        return {
            "interactions": one("SELECT COUNT(*) FROM interactions"),
            "processed": one("SELECT COUNT(*) FROM interactions WHERE status='processed'"),
            "imports": one("SELECT COUNT(*) FROM imports"),
            "l1": one("SELECT COUNT(*) FROM taxonomy_nodes WHERE level=1 AND status='active'"),
            "l2": one("SELECT COUNT(*) FROM taxonomy_nodes WHERE level=2 AND status='active'"),
            "l4": one("SELECT COUNT(*) FROM taxonomy_nodes WHERE level=4 AND status='active'"),
            "pending_proposals": one("SELECT COUNT(*) FROM taxonomy_changes WHERE status='proposed'"),
            "run_status": run["status"] if run else None,
            "last_activity": max(filter(None, [run and (run["finished_at"] or run["started_at"]),
                                               last_import and last_import["created_at"]]), default=None),
            "dataset": last_import["name"] if last_import else None,
        }
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


def list_projects() -> dict:
    data = _load()
    return {"active": data["active"],
            "projects": [{**p, "stats": _stats(_db_file(p))} for p in data["projects"]]}


def _clean_name(name: str) -> str:
    name = " ".join((name or "").split())
    if not name:
        raise ProjectError("Project name must not be empty")
    if len(name) > 80:
        raise ProjectError("Project name must be at most 80 characters")
    return name


def create(name: str, description: str = "", settings: dict | None = None) -> dict:
    name = _clean_name(name)
    with _lock:
        data = _load()
        pid = secrets.token_hex(4)
        project = {"id": pid, "name": name, "description": (description or "").strip()[:500],
                   "db": f"projects/{pid}.db", "created_at": db.utcnow()}
        path = _db_file(project)
        previous = db.get_db_path()
        try:
            db.set_db_path(path)
            db.init_db(seed=False)
            if settings:
                with db.session() as conn:
                    db.save_settings(conn, settings)
        finally:
            db.set_db_path(previous)
        data["projects"].append(project)
        _save(data)
    return project


def update(pid: str, name: str | None = None, description: str | None = None) -> dict:
    with _lock:
        data = _load()
        project = next((p for p in data["projects"] if p["id"] == pid), None)
        if not project:
            raise ProjectError("Unknown project")
        if name is not None:
            project["name"] = _clean_name(name)
        if description is not None:
            project["description"] = description.strip()[:500]
        _save(data)
    return project


def activate(pid: str) -> dict:
    with _lock:
        data = _load()
        project = next((p for p in data["projects"] if p["id"] == pid), None)
        if not project:
            raise ProjectError("Unknown project")
        data["active"] = pid
        _save(data)
        db.set_db_path(_db_file(project))
    db.init_db()
    return project


def delete(pid: str) -> None:
    with _lock:
        data = _load()
        project = next((p for p in data["projects"] if p["id"] == pid), None)
        if not project:
            raise ProjectError("Unknown project")
        if pid == data["active"]:
            raise ProjectError("Switch to another project before deleting this one")
        data["projects"] = [p for p in data["projects"] if p["id"] != pid]
        _save(data)
        path = _db_file(project)
        for suffix in ("", "-wal", "-shm"):
            Path(f"{path}{suffix}").unlink(missing_ok=True)
