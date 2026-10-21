"""Intent Studio FastAPI application."""
from __future__ import annotations

import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (assignments, branding, config, db, evaluation, events, export, importers, insights, interactions,
               language, ollama_client, pipeline, projects, report, taxonomy)
from .worker import WorkerBusy, worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("intent_studio")


@asynccontextmanager
async def lifespan(_: FastAPI):
    project = projects.init()
    log.info("Intent Studio ready (project: %s, database: %s)", project["name"], db.get_db_path())
    yield
    worker.stop()


app = FastAPI(title="Intent Studio", version="0.1.0", lifespan=lifespan)


# --- error handling (never echo transcript content) -------------------------------------

@app.exception_handler(taxonomy.TaxonomyError)
@app.exception_handler(assignments.AssignmentError)
@app.exception_handler(importers.ImportErrorSafe)
@app.exception_handler(projects.ProjectError)
@app.exception_handler(branding.BrandingError)
async def _bad_request(_: Request, exc: Exception):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(WorkerBusy)
async def _busy(_: Request, exc: Exception):
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.exception_handler(Exception)
async def _internal(_: Request, exc: Exception):
    log.error("Unhandled %s on request", type(exc).__name__)
    return JSONResponse({"detail": f"Internal error ({type(exc).__name__})"}, status_code=500)


# --- settings & connectivity ---------------------------------------------------------------

_status_cache: dict[str, Any] = {"at": 0.0, "value": None, "url": None}


@app.get("/api/health")
def health():
    return {"ok": True}


def _settings_payload(s: config.Settings) -> dict:
    with db.session() as conn:
        lang = language.get(conn)
    return {**s.to_dict(), "thresholds": s.thresholds(), "sensitivity_presets": config.SENSITIVITY_PRESETS,
            "taxonomy_language": lang, "languages": language.NAMES}


@app.get("/api/settings")
def get_settings():
    return _settings_payload(db.load_settings())


@app.put("/api/settings")
def put_settings(values: dict[str, Any] = Body(...)):
    allowed = set(config.Settings().to_dict())
    clean = {k: v for k, v in values.items() if k in allowed}
    if "batch_size" in clean and not 1 <= int(clean["batch_size"]) <= 500:
        raise HTTPException(400, "Batch size must be between 1 and 500")
    if "clustering_sensitivity" in clean and clean["clustering_sensitivity"] not in config.SENSITIVITY_PRESETS:
        raise HTTPException(400, "Unknown clustering sensitivity")
    if "request_timeout" in clean and not 5 <= float(clean["request_timeout"]) <= 1800:
        raise HTTPException(400, "Timeout must be between 5 and 1800 seconds")
    lang = values.get("taxonomy_language")
    if lang is not None and lang not in language.NAMES:
        raise HTTPException(400, "Unsupported analysis language")
    with db.session() as conn:
        s = db.save_settings(conn, clean)
        if lang is not None and lang != language.get(conn):
            with db.transaction(conn):
                language.store(conn, lang)
                events.emit(conn, "info", f"Analysis language set to {language.name(lang)}")
    _status_cache["at"] = 0
    return _settings_payload(s)


@app.post("/api/settings/test")
def test_connection(values: dict[str, Any] = Body(default={})):
    s = db.load_settings()
    url = values.get("ollama_url") or s.ollama_url
    result = ollama_client.connection_test(url, values.get("llm_model") or s.llm_model,
                                           values.get("embedding_model") or s.embedding_model,
                                           float(values.get("request_timeout") or s.request_timeout))
    _status_cache.update(at=time.time(), url=url, value={"ok": result["ok"], "reachable": bool(result["server"]["ok"]),
                                                         "url": url, "models": result["models"], "tested": True})
    return result


@app.get("/api/ollama/status")
def ollama_status():
    s = db.load_settings()
    if _status_cache["value"] and _status_cache["url"] == s.ollama_url and time.time() - _status_cache["at"] < 20:
        return _status_cache["value"]
    try:
        with ollama_client.OllamaClient(s.ollama_url, timeout=8) as c:
            names = [m.get("name") for m in c.tags()]
        value = {"ok": s.llm_model in names and s.embedding_model in names, "reachable": True, "url": s.ollama_url,
                 "models": names, "missing": [m for m in (s.llm_model, s.embedding_model) if m not in names]}
    except ollama_client.OllamaError as e:
        value = {"ok": False, "reachable": False, "url": s.ollama_url, "models": [], "error": str(e)}
    _status_cache.update(at=time.time(), url=s.ollama_url, value=value)
    return value


# --- status & analysis control ------------------------------------------------------------------

def _run_state(conn) -> dict:
    run = conn.execute("SELECT * FROM analysis_runs ORDER BY id DESC LIMIT 1").fetchone()
    state = dict(run) if run else None
    if state:
        state["settings"] = db.loads(state.pop("settings_json"), {})
    return {"run": state, "worker_alive": worker.is_running()}


@app.get("/api/summary")
def summary():
    with db.session() as conn:
        s = insights.summary(conn)
        p = projects.active()
        return {**s, **_run_state(conn), "project": {"id": p["id"], "name": p["name"]},
                "taxonomy_language": language.get(conn)}


# --- projects ------------------------------------------------------------------------------------

class ProjectBody(BaseModel):
    name: str | None = None
    description: str | None = None


@app.get("/api/projects")
def list_projects():
    return projects.list_projects()


@app.post("/api/projects")
def create_project(body: ProjectBody):
    inherited = {k: v for k, v in db.load_settings().to_dict().items()
                 if k in ("ollama_url", "llm_model", "embedding_model", "request_timeout")}
    return projects.create(body.name or "", body.description or "", inherited)


@app.patch("/api/projects/{pid}")
def update_project(pid: str, body: ProjectBody):
    return projects.update(pid, body.name, body.description)


@app.post("/api/projects/{pid}/activate")
def activate_project(pid: str):
    _require_idle()
    project = projects.activate(pid)
    _uploads.clear()
    return project


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    projects.delete(pid)
    return {"ok": True}


@app.post("/api/analysis/start")
def start_analysis():
    return {"run_id": worker.start("analysis")}


@app.post("/api/analysis/resume")
def resume_analysis():
    return {"run_id": worker.resume()}


@app.post("/api/analysis/pause")
def pause_analysis():
    worker.pause()
    return {"ok": True}


@app.post("/api/analysis/stop")
def stop_analysis():
    worker.stop()
    return {"ok": True}


@app.post("/api/analysis/recluster")
def recluster():
    return {"run_id": worker.start("recluster")}


@app.post("/api/analysis/retry-failed")
def retry_failed():
    with db.session() as conn:
        cur = conn.execute("UPDATE interactions SET status='pending', error=NULL WHERE status='failed'")
        return {"requeued": cur.rowcount}


def _require_idle():
    if worker.is_running():
        raise WorkerBusy("Pause or stop the running analysis first")


@app.post("/api/analysis/reset")
def reset_analysis():
    """Remove all analysis results (intents, assignments, L3/L4, proposals) but keep imported data."""
    _require_idle()
    with db.session() as conn, db.write_lock, db.transaction(conn):
        conn.execute("DELETE FROM assignment_history")
        conn.execute("DELETE FROM assignments")
        conn.execute("DELETE FROM intents")
        conn.execute("DELETE FROM taxonomy_changes")
        conn.execute("DELETE FROM batch_stats")
        conn.execute("DELETE FROM events")
        conn.execute("DELETE FROM analysis_runs")
        conn.execute("UPDATE taxonomy_nodes SET parent_id=NULL WHERE level IN (3,4)")
        conn.execute("DELETE FROM taxonomy_nodes WHERE level IN (3,4)")
        conn.execute("UPDATE interactions SET status='pending', summary=NULL, no_intent_reason=NULL, error=NULL, "
                     "processed_at=NULL, processed_order=NULL, batch_index=NULL, review_flag=0, review_unclassified=0")
        conn.execute("DELETE FROM meta WHERE key IN ('last_refined_order','seq_l3','seq_l4') OR key LIKE ?",
                     (insights.NOTES_META_KEY + "%",))
        v = taxonomy.bump_version(conn, "Analysis reset — L3/L4 removed")
        events.emit(conn, "info", "Analysis results reset — imported interactions kept")
    return {"ok": True, "version": v}


@app.post("/api/workspace/reset")
def reset_workspace():
    _require_idle()
    reset_analysis()
    with db.session() as conn, db.transaction(conn):
        conn.execute("DELETE FROM interactions")
        conn.execute("DELETE FROM imports")
        conn.execute("DELETE FROM events")
    return {"ok": True}


# --- import ------------------------------------------------------------------------------------

_uploads: dict[str, dict] = {}


def _store_upload(files: list[tuple[str, bytes]], txt_separator: str | None) -> str:
    token = secrets.token_urlsafe(12)
    _uploads[token] = {"files": files, "txt_separator": txt_separator, "at": time.time()}
    for old in sorted(_uploads, key=lambda k: _uploads[k]["at"])[:-5]:
        _uploads.pop(old, None)
    return token


@app.post("/api/import/preview")
async def import_preview(files: list[UploadFile] = File(...), mapping: str | None = Form(None),
                         txt_separator: str | None = Form(None)):
    raw = [(f.filename or "upload.txt", await f.read()) for f in files]
    if sum(len(c) for _, c in raw) > 200 * 1024 * 1024:
        raise HTTPException(413, "Upload too large (max 200 MB)")
    m = json.loads(mapping) if mapping else None
    res = importers.parse_upload(raw, m, txt_separator or None)
    token = _store_upload(raw, txt_separator or None)
    return {"token": token, **importers.preview_payload(res)}


class CommitBody(BaseModel):
    token: str
    mapping: dict[str, str | None] | None = None
    name: str | None = None


@app.post("/api/import/remap")
def import_remap(body: CommitBody):
    up = _uploads.get(body.token)
    if not up:
        raise HTTPException(404, "Upload expired — please upload the file again")
    res = importers.parse_upload(up["files"], body.mapping, up["txt_separator"])
    return {"token": body.token, **importers.preview_payload(res)}


@app.post("/api/import/commit")
def import_commit(body: CommitBody):
    up = _uploads.get(body.token)
    if not up:
        raise HTTPException(404, "Upload expired — please upload the file again")
    res = importers.parse_upload(up["files"], body.mapping, up["txt_separator"])
    if not res.records:
        raise HTTPException(400, "No valid interactions to import")
    name = body.name or (up["files"][0][0] if len(up["files"]) == 1 else f"{len(up['files'])} text files")
    with db.session() as conn:
        out = importers.commit(conn, name, res.format, res.records)
        with db.transaction(conn):
            events.emit(conn, "info", f"Imported {out['imported']} interactions from {name}"
                        + (f" ({out['skipped_existing']} already present)" if out["skipped_existing"] else ""))
    _uploads.pop(body.token, None)
    return out


@app.post("/api/import/sample")
def import_sample():
    path = config.SAMPLE_DIR / "sample_transcripts.json"
    if not path.exists():
        raise HTTPException(404, "Sample dataset not found — run scripts/generate_sample_data.py")
    res = importers.parse_upload([(path.name, path.read_bytes())])
    with db.session() as conn:
        out = importers.commit(conn, "Synthetic Telco Sample (100)", "json", res.records)
        with db.transaction(conn):
            events.emit(conn, "info", f"Loaded {out['imported']} synthetic sample interactions"
                        + (f" ({out['skipped_existing']} already present)" if out["skipped_existing"] else ""))
    return out


@app.get("/api/import/template.csv")
def csv_template():
    return FileResponse(config.SAMPLE_DIR / "import_template.csv", media_type="text/csv",
                        filename="intent_studio_import_template.csv")


@app.get("/api/import/template.json")
def json_template():
    example = [
        {"conversation_id": "CONV-0001", "channel": "voice", "segment": "prepaid", "language": "en",
         "timestamp": "2026-10-20T10:00:00Z", "queue": "Prepaid Support",
         "turns": [{"speaker": "customer", "text": "I topped up yesterday, but the credit is still missing."},
                   {"speaker": "agent", "text": "I can check the transaction for you."}]},
        {"conversation_id": "CONV-0002", "channel": "whatsapp", "segment": "postpaid", "language": "en",
         "turns": [{"speaker": "customer", "text": "Why is my bill higher than last month?"},
                   {"speaker": "agent", "text": "Let me go through the line items with you."}]},
    ]
    return Response(json.dumps(example, indent=2), media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=intent_studio_import_template.json"})


@app.get("/api/import/sample.csv")
def sample_csv():
    return FileResponse(config.SAMPLE_DIR / "sample_transcripts.csv", media_type="text/csv",
                        filename="sample_transcripts.csv")


# --- taxonomy ----------------------------------------------------------------------------------

@app.get("/api/taxonomy")
def get_taxonomy(include_inactive: bool = False):
    with db.session() as conn:
        return taxonomy.tree(conn, include_inactive)


@app.get("/api/taxonomy/nodes/{node_id}")
def get_node(node_id: str):
    with db.session() as conn:
        return taxonomy.node_detail(conn, node_id)


class NodeCreate(BaseModel):
    parent_id: str | None = None
    label: str
    description: str = ""


class NodeUpdate(BaseModel):
    label: str | None = None
    description: str | None = None


@app.post("/api/taxonomy/nodes")
def create_node(body: NodeCreate):
    with db.session() as conn, db.write_lock, db.transaction(conn):
        return taxonomy.manual_create(conn, body.parent_id, body.label, body.description)


@app.patch("/api/taxonomy/nodes/{node_id}")
def update_node(node_id: str, body: NodeUpdate):
    with db.session() as conn, db.write_lock, db.transaction(conn):
        return taxonomy.manual_update(conn, node_id, body.label, body.description)


@app.post("/api/taxonomy/nodes/{node_id}/move")
def move_node(node_id: str, parent_id: str = Body(..., embed=True)):
    with db.session() as conn, db.write_lock, db.transaction(conn):
        return taxonomy.manual_move(conn, node_id, parent_id)


@app.post("/api/taxonomy/nodes/{node_id}/retire")
def retire_node(node_id: str):
    with db.session() as conn, db.write_lock, db.transaction(conn):
        return taxonomy.manual_retire(conn, node_id)


@app.post("/api/taxonomy/merge")
def merge_nodes(source_id: str = Body(...), target_id: str = Body(...)):
    with db.session() as conn, db.write_lock, db.transaction(conn):
        return taxonomy.manual_merge(conn, source_id, target_id, db.load_settings(conn))


@app.post("/api/taxonomy/import")
async def import_taxonomy(file: UploadFile = File(...)):
    try:
        data = json.loads((await file.read()).decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(400, "Taxonomy file must be valid JSON")
    with db.session() as conn:
        v = taxonomy.replace_base_taxonomy(conn, data)
        lang = language.get(conn)
        with db.transaction(conn):
            events.emit(conn, "taxonomy_edited", f"Base L1/L2 taxonomy replaced from file "
                        f"(analysis language: {language.name(lang)})")
    return {"version": v, "language": lang}


@app.get("/api/taxonomy/base.json")
def export_base_taxonomy():
    with db.session() as conn:
        cats = [{"id": n["id"], "label": n["label"], "description": n["description"], "parent_id": n["parent_id"],
                 "level": n["level"]} for n in taxonomy.nodes(conn, ("active",)) if n["level"] <= 2]
    return Response(json.dumps({"name": "Intent Studio base taxonomy", "categories": cats}, indent=2),
                    media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=taxonomy_base.json"})


@app.get("/api/proposals")
def proposals(status: str | None = "proposed"):
    with db.session() as conn:
        return taxonomy.list_changes(conn, status=status or None)


@app.post("/api/proposals/{change_id}/accept")
def accept_proposal(change_id: int):
    with db.session() as conn, db.write_lock, db.transaction(conn):
        return taxonomy.accept(conn, change_id, actor="user", settings=db.load_settings(conn))


@app.post("/api/proposals/{change_id}/reject")
def reject_proposal(change_id: int):
    with db.session() as conn, db.write_lock, db.transaction(conn):
        return taxonomy.reject(conn, change_id)


@app.get("/api/changes")
def changes(limit: int = 500):
    with db.session() as conn:
        return taxonomy.list_changes(conn, limit=limit)


@app.get("/api/versions")
def versions():
    with db.session() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM taxonomy_versions ORDER BY version DESC")]


# --- interactions & review -------------------------------------------------------------------------

@app.get("/api/interactions")
def list_interactions():
    with db.session() as conn:
        return interactions.list_interactions(conn)


@app.get("/api/interactions/{interaction_id}")
def get_interaction(interaction_id: int):
    with db.session() as conn:
        inter = interactions.get_interaction(conn, interaction_id)
    if not inter:
        raise HTTPException(404, "Interaction not found")
    return inter


class InteractionReview(BaseModel):
    flag: bool | None = None
    unclassified: bool | None = None
    notes: str | None = None


@app.patch("/api/interactions/{interaction_id}/review")
def review_interaction(interaction_id: int, body: InteractionReview):
    with db.session() as conn, db.write_lock, db.transaction(conn):
        try:
            interactions.set_interaction_review(conn, interaction_id, flag=body.flag, unclassified=body.unclassified,
                                                notes=body.notes)
        except ValueError as e:
            raise HTTPException(404, str(e))
        return interactions.get_interaction(conn, interaction_id)


class AssignmentReview(BaseModel):
    action: str
    path: dict[str, str | None] | None = None
    notes: str | None = None


@app.post("/api/assignments/{assignment_id}/review")
def review_assignment(assignment_id: int, body: AssignmentReview):
    with db.session() as conn, db.write_lock, db.transaction(conn):
        row = assignments.review(conn, assignment_id, body.action, path=body.path, notes=body.notes)
        cid = conn.execute("SELECT conversation_id FROM interactions WHERE id=?", (row["interaction_id"],)).fetchone()[0]
        verb = {"confirm": "confirmed", "correct": "corrected", "unclassify": "marked unclassified",
                "flag": "flagged for review", "reset": "reset to pending", "note": "annotated"}.get(body.action, body.action)
        events.emit(conn, "assignment_corrected", f"Interaction {cid} — assignment {verb} by reviewer",
                    conversation_id=cid, node_id=row["l4_id"] or row["l2_id"], data={"assignment_id": assignment_id})
        return row


# --- events ---------------------------------------------------------------------------------------

@app.get("/api/events")
def list_events(after: int = 0, limit: int = Query(200, le=2000), newest: bool = True,
                conversation_id: str | None = None):
    with db.session() as conn:
        rows = events.list_events(conn, after_id=after, limit=limit, newest_first=newest, conversation_id=conversation_id)
    return rows


@app.get("/api/events/stream")
async def stream_events(request: Request, after: int | None = None):
    last = request.headers.get("last-event-id")
    start = int(last) if last and last.isdigit() else after
    if start is None:
        with db.session() as conn:
            start = conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0]
    return StreamingResponse(events.stream(start), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- insights & export -------------------------------------------------------------------------------

@app.get("/api/insights/curve")
def curve():
    with db.session() as conn:
        return insights.discovery_curve(conn)


@app.get("/api/insights/evaluation")
def evaluation_view():
    with db.session() as conn:
        return evaluation.compare(conn)


@app.get("/api/insights/intents")
def intent_volume(lang: str = "en"):
    with db.session() as conn:
        dist = insights.intent_distribution(conn)
        return {**dist, "notes": insights.cached_notes(conn, dist, lang)}


@app.post("/api/insights/intents/notes")
def intent_notes(force: bool = False, lang: str = "en"):
    s = db.load_settings()
    with db.session() as conn, pipeline.make_client(s) as client:
        return insights.generate_notes(conn, client, s.llm_model, force=force, lang=lang)


@app.get("/api/insights/overlaps")
def overlaps():
    with db.session() as conn:
        return insights.overlap_pairs(conn, db.load_settings().thresholds()["merge"])


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M")


@app.get("/api/export/xlsx")
def export_xlsx(lang: str = "en"):
    with db.session() as conn:
        data = export.to_xlsx(conn, lang)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=intent_studio_{_stamp()}.xlsx"})


@app.get("/api/export/csv")
def export_csv(sheet: str | None = None, lang: str = "en"):
    with db.session() as conn:
        try:
            data, mime, name = export.to_csv(conn, sheet, lang)
        except KeyError:
            raise HTTPException(400, f"Unknown sheet; choose one of {export.SHEETS}")
    return Response(data, media_type=mime, headers={"Content-Disposition": f"attachment; filename={name}"})


@app.get("/api/export/json")
def export_json():
    with db.session() as conn:
        data = export.to_json(conn)
    return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f"attachment; filename=intent_studio_{_stamp()}.json"})


@app.get("/api/export/report.pdf")
def export_report(lang: str = "en"):
    project = projects.active()
    with db.session() as conn:
        data = report.build(conn, lang, project["name"], branding.logo_path())
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=intent_studio_report_{_stamp()}.pdf"})


# --- branding ----------------------------------------------------------------------------------------

@app.get("/api/branding")
def get_branding():
    return branding.info()


@app.get("/api/branding/logo")
def get_logo():
    path = branding.logo_path()
    if not path.exists():
        raise HTTPException(404, "No logo uploaded")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-cache"})


@app.post("/api/branding/logo")
async def upload_logo(file: UploadFile = File(...)):
    return branding.save_logo(await file.read())


@app.delete("/api/branding/logo")
def delete_logo():
    return branding.delete_logo()


# --- built frontend (optional single-process mode) ----------------------------------------------------

_dist = config.REPO_DIR / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = _dist / path
        if path and target.is_file() and _dist in target.resolve().parents:
            return FileResponse(target)
        return FileResponse(_dist / "index.html")
