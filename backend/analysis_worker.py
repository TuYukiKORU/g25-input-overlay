"""Single background worker for persisted session analysis jobs."""
import logging
import queue
import threading
from datetime import datetime, timezone

from session_analysis import analyze_session
from analysis_freshness import source_signature, freshness


def _now():
    return datetime.now(timezone.utc).isoformat()


class AnalysisWorker:
    def __init__(self, storage):
        self.storage = storage
        self._jobs = {}
        self._lock = threading.RLock()
        self._queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True, name="session-analysis-worker").start()

    def _key(self, session_id, track_id):
        return str(session_id), str(track_id)

    def status(self, session_id, track_id):
        key = self._key(session_id, track_id)
        with self._lock:
            active = self._jobs.get(key)
            if active and active["state"] in ("running", "queued"):
                return active.copy()
        result = self.storage.load_session_analysis(session_id, track_id)
        context = freshness(self.storage, result, track_id, session_id) if result else {}
        persisted = self.storage.load_analysis_status(session_id, track_id)
        if persisted and persisted.get("state") in ("completed", "failed"):
            return persisted | context
        if result:
            return {"state": "completed", "progress": 100, "current": "保存済み分析を利用できます",
                    "error": None, "completed_at": result.get("generated_at")} | context
        return {"state": None, "progress": 0, "current": "未分析", "error": None}

    def start(self, session_id, track_id, selected_lap_id=None, force=False,
              section_settings=None, turn_definition=None):
        key = self._key(session_id, track_id)
        with self._lock:
            existing = self._jobs.get(key)
            if existing and existing["state"] in ("queued", "running"):
                return existing.copy(), False
            saved = self.storage.load_session_analysis(session_id, track_id)
            if (saved and not force and not freshness(self.storage, saved, track_id, session_id)["stale"]
                    and saved.get("requested_lap_id") == selected_lap_id
                    and saved.get("requested_settings") == (section_settings or {})
                    and saved.get("requested_definition") == turn_definition):
                return self.status(session_id, track_id), False
            status = {"state": "queued", "progress": 0, "current": "分析待ち", "error": None,
                      "queued_at": _now(), "started_at": None, "completed_at": None}
            self._jobs[key] = status
            self.storage.save_analysis_status(session_id, track_id, status)
            self._queue.put((session_id, track_id, selected_lap_id, section_settings or {}, turn_definition))
            return status.copy(), True

    def _set(self, key, **changes):
        with self._lock:
            self._jobs[key].update(changes)
            status = self._jobs[key].copy()
        self.storage.save_analysis_status(key[0], key[1], status)

    def _run(self):
        while True:
            session_id, track_id, selected_lap_id, section_settings, turn_definition = self._queue.get()
            key = self._key(session_id, track_id)
            try:
                self._set(key, state="running", progress=1, current="セッション分析を開始中", started_at=_now())
                signature = source_signature(self.storage, track_id, session_id)
                laps = self.storage.session_track_laps(session_id, track_id)
                if not laps:
                    raise ValueError("選択したセッション／コースに保存済みラップがありません")
                def progress(percent, current):
                    self._set(key, progress=max(1, min(99, int(percent))), current=current)
                result = analyze_session(laps, selected_lap_id, progress, section_settings, turn_definition)
                result.update(source_signature=signature, requested_lap_id=selected_lap_id,
                              requested_settings=section_settings, requested_definition=turn_definition)
                self.storage.save_session_analysis(session_id, track_id, result)
                self._set(key, state="completed", progress=100, current="分析完了", error=None, completed_at=_now())
            except Exception as error:  # Preserve a queryable failure instead of killing the daemon.
                logging.exception("Session analysis failed")
                self._set(key, state="failed", progress=100, current="分析失敗", error=str(error), completed_at=_now())
            finally:
                self._queue.task_done()
