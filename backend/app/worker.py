"""Single managed background worker for analysis runs (start / pause / stop / resume / re-cluster)."""
from __future__ import annotations

import logging
import threading
import time
import traceback

from . import db, events, pipeline
from .ollama_client import OllamaError

log = logging.getLogger("intent_studio.worker")

MAX_CONSECUTIVE_CONNECTION_ERRORS = 2


class WorkerBusy(RuntimeError):
    pass


class AnalysisWorker:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._pause = threading.Event()
        self._stop = threading.Event()
        self.run_id: int | None = None

    # -- control ------------------------------------------------------------------
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, job: str = "analysis", resume_run: int | None = None) -> int:
        with self._lock:
            if self.is_running():
                raise WorkerBusy("An analysis job is already running")
            self._pause.clear()
            self._stop.clear()
            with db.session() as conn:
                settings = db.load_settings(conn)
                if not conn.execute("SELECT 1 FROM taxonomy_nodes WHERE level=2 AND status='active' LIMIT 1").fetchone():
                    raise WorkerBusy("Import an L1/L2 taxonomy before starting the analysis")
                pending = conn.execute("SELECT COUNT(*) FROM interactions WHERE status='pending'").fetchone()[0]
                if job == "analysis" and not pending and resume_run is None:
                    unrefined = self._needs_final_refinement(conn)
                    if not unrefined:
                        raise WorkerBusy("No unprocessed interactions — import data first")
                with db.transaction(conn):
                    if resume_run:
                        conn.execute("UPDATE analysis_runs SET status='running', finished_at=NULL, error=NULL WHERE id=?",
                                     (resume_run,))
                        run_id = resume_run
                        events.emit(conn, "run_resumed", f"Analysis resumed — {pending} interactions remaining",
                                    run_id=run_id, data={"pending": pending})
                    else:
                        cur = conn.execute("INSERT INTO analysis_runs(status, job, started_at, settings_json, total_target) "
                                           "VALUES ('running', ?, ?, ?, ?)",
                                           (job, db.utcnow(), db.dumps(settings.to_dict()), pending))
                        run_id = int(cur.lastrowid)
                        msg = (f"Analysis started — {pending} interactions, batch size {settings.batch_size}, "
                               f"model {settings.llm_model}" if job == "analysis" else "Re-clustering existing data")
                        events.emit(conn, "run_started", msg, run_id=run_id,
                                    data={"pending": pending, "job": job, "settings": settings.to_dict()})
            self.run_id = run_id
            self._thread = threading.Thread(target=self._run, args=(run_id, job), name="analysis-worker", daemon=True)
            self._thread.start()
            return run_id

    def resume(self) -> int:
        with db.session() as conn:
            row = conn.execute("SELECT id, status, job FROM analysis_runs ORDER BY id DESC LIMIT 1").fetchone()
        if row and row["status"] in ("paused", "interrupted", "stopped", "failed") and row["job"] == "analysis":
            return self.start("analysis", resume_run=row["id"])
        return self.start("analysis")

    def pause(self) -> None:
        if self.is_running():
            self._pause.set()

    def stop(self) -> None:
        if self.is_running():
            self._stop.set()
            with db.session() as conn:
                conn.execute("UPDATE analysis_runs SET status='stopping' WHERE id=?", (self.run_id,))

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    @staticmethod
    def _needs_final_refinement(conn) -> bool:
        last = int(db.get_meta(conn, "last_refined_order", "0"))
        mx = conn.execute("SELECT COALESCE(MAX(processed_order), 0) FROM interactions").fetchone()[0]
        return mx > last

    # -- thread body ------------------------------------------------------------------
    def _finish(self, conn, run_id: int, status: str, kind: str, message: str, level: str = "info",
                error: str | None = None) -> None:
        with db.transaction(conn):
            conn.execute("UPDATE analysis_runs SET status=?, finished_at=?, current_step=NULL, current_interaction=NULL, "
                         "error=? WHERE id=?", (status, db.utcnow(), error, run_id))
            events.emit(conn, kind, message, run_id=run_id, level=level)

    def _run(self, run_id: int, job: str) -> None:
        conn = db.connect()
        settings = db.load_settings(conn)
        client = pipeline.make_client(settings)
        ctx = pipeline.Ctx(conn, client, settings, run_id, should_stop=lambda: self._stop.is_set())
        try:
            if job == "recluster":
                with db.write_lock, db.transaction(conn):
                    from . import taxonomy
                    for l2 in taxonomy.base_categories(conn):
                        taxonomy.rematch_candidates(conn, l2["id"], settings, run_id)
                batch = conn.execute("SELECT COALESCE(MAX(batch_index), 0) FROM interactions").fetchone()[0]
                pipeline.refine(ctx, batch, final=True, label="Re-clustering all open intent candidates")
                self._finish(conn, run_id, "completed", "run_completed", "Re-clustering completed", "success")
                return
            consecutive = 0
            while True:
                if self._pause.is_set():
                    self._finish(conn, run_id, "paused", "run_paused", "Analysis paused — resume to continue")
                    return
                if self._stop.is_set():
                    break
                row = conn.execute("SELECT * FROM interactions WHERE status='pending' ORDER BY seq LIMIT 1").fetchone()
                if not row:
                    break
                outcome = pipeline.process_interaction(ctx, row)
                if outcome == "retry":
                    consecutive += 1
                    if consecutive >= MAX_CONSECUTIVE_CONNECTION_ERRORS:
                        self._finish(conn, run_id, "paused", "run_paused",
                                     "Analysis paused — Ollama is not responding. Check Settings and resume.",
                                     level="error", error="Ollama unreachable")
                        return
                    time.sleep(2)
                    continue
                consecutive = 0
                last = int(db.get_meta(conn, "last_refined_order", "0"))
                mx = conn.execute("SELECT COALESCE(MAX(processed_order), 0) FROM interactions").fetchone()[0]
                if mx - last >= settings.batch_size:
                    pipeline.refine(ctx, (mx - 1) // settings.batch_size, final=False)
            stopped = self._stop.is_set()
            self._stop.clear()  # allow the final refinement to complete
            if self._needs_final_refinement(conn) or not stopped:
                mx = conn.execute("SELECT COALESCE(MAX(processed_order), 0) FROM interactions").fetchone()[0]
                pipeline.refine(ctx, max(0, (mx - 1) // settings.batch_size), final=True,
                                label="Final refinement — clustering remaining candidates and reviewing rare intents")
            if stopped:
                self._finish(conn, run_id, "stopped", "run_stopped", "Analysis stopped — remaining interactions stay queued")
            else:
                self._finish(conn, run_id, "completed", "run_completed", "Analysis completed", "success")
        except OllamaError as e:
            self._finish(conn, run_id, "failed", "run_failed", f"Analysis failed: {e}", "error", error=str(e))
        except Exception as e:  # never leak transcript content: only the exception type is reported
            log.error("Analysis worker crashed: %s\n%s", type(e).__name__, "".join(traceback.format_tb(e.__traceback__)))
            self._finish(conn, run_id, "failed", "run_failed", f"Analysis failed with an internal error "
                         f"({type(e).__name__}); see server log", "error", error=type(e).__name__)
        finally:
            client.close()
            conn.close()


worker = AnalysisWorker()
