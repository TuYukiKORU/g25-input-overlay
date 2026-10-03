"""Background and cached execution for qualifying and race strategy analysis."""
import hashlib
import json
import logging
import queue
import threading
from datetime import datetime, timezone

from qualifying_optimizer import analyze_qualifying
from race_optimizer import analyze_race
from strategy_model import build_strategy_model
from analysis_freshness import source_signature, freshness
from strategy_workspace import analyze_workspace


def _now():
    return datetime.now(timezone.utc).isoformat()


class StrategyWorker:
    def __init__(self, storage):
        self.storage = storage
        self._jobs = {}
        self._models = {}
        self._lock = threading.RLock()
        self._queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True, name="strategy-analysis-worker").start()

    def _fingerprint(self, kind, session_id, track_id, settings):
        signature = source_signature(self.storage, track_id)
        laps = [{"id": lap["id"], "time": lap.get("lapTimeMs"), "samples": lap.get("sampleCount"),
                 "created": lap.get("createdAt")}
                for lap in self.storage.list_laps() if str(lap.get("trackId")) == str(track_id)]
        payload = {"schema": 5, "model": "condition-matched-section-actions-v5", "kind": kind,
                   "source_signature": signature,
                   "session": session_id, "track": str(track_id), "settings": settings, "laps": laps}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def status(self, session_id, track_id, kind, analysis_id):
        key = (str(session_id), str(track_id), kind, analysis_id)
        with self._lock:
            if key in self._jobs and self._jobs[key]["state"] in ("queued", "running"):
                return self._jobs[key].copy()
        saved = self.storage.load_strategy_artifact(session_id, track_id, kind, analysis_id, "status.json")
        result = self.storage.load_strategy_artifact(session_id, track_id, kind, analysis_id)
        return (saved or {"state": None, "progress": 0, "current": "未分析", "error": None,
                         "analysis_id": analysis_id}) | (freshness(self.storage, result, track_id) if result else {})

    def start(self, kind, session_id, track_id, settings, force=False):
        analysis_id = self._fingerprint(kind, session_id, track_id, settings)
        key = (str(session_id), str(track_id), kind, analysis_id)
        with self._lock:
            existing = self._jobs.get(key)
            if existing and existing["state"] in ("queued", "running"):
                return existing.copy(), False
            saved = self.storage.load_strategy_artifact(session_id, track_id, kind, analysis_id)
            if saved and not force:
                status = {"state": "completed", "progress": 100, "current": "保存済み分析を再利用",
                          "error": None, "analysis_id": analysis_id, "cached": True,
                          "completed_at": saved.get("generated_at")}
                return status, False
            status = {"state": "queued", "progress": 0, "current": "分析待ち", "error": None,
                      "analysis_id": analysis_id, "cached": False, "queued_at": _now(),
                      "started_at": None, "completed_at": None}
            self._jobs[key] = status
            self.storage.save_strategy_artifact(session_id, track_id, kind, analysis_id, status, "status.json")
            self._queue.put((key, settings))
            return status.copy(), True

    def _set(self, key, **changes):
        with self._lock:
            self._jobs[key].update(changes)
            value = self._jobs[key].copy()
        self.storage.save_strategy_artifact(key[0], key[1], key[2], key[3], value, "status.json")

    def _run(self):
        while True:
            key, settings = self._queue.get()
            session_id, track_id, kind, analysis_id = key
            try:
                signature = source_signature(self.storage, track_id)
                self._set(key, state="running", progress=5, current="ラップデータを読み込み中", started_at=_now())
                entries = []
                for metadata in self.storage.list_laps():
                    if str(metadata.get("trackId")) != str(track_id):
                        continue
                    lap = self.storage.load_lap(metadata["id"])
                    if lap:
                        entries.append((metadata["id"], lap))
                self._set(key, progress=25, current="共通セクション予測モデルを作成中")
                model_key = (signature, session_id, str(track_id), settings.get("selected_lap_id"),
                             settings.get("pace_window_percent", 8), settings.get("max_laps", 40))
                model = self._models.get(model_key)
                if model is None:
                    model = build_strategy_model(
                        entries, selected_session_id=session_id,
                        selected_lap_id=settings.get("selected_lap_id"),
                        track_profile=self.storage.load_track_profile(track_id),
                        pace_window_percent=settings.get("pace_window_percent", 8),
                        max_laps=settings.get("max_laps", 40))
                    if len(self._models) >= 4:
                        self._models.pop(next(iter(self._models)))
                    self._models[model_key] = model
                if not model.get("analyzable"):
                    raise ValueError(model.get("reason") or "戦略モデルを作成できませんでした")
                self._set(key, progress=70, current="ERS配分を最適化中")
                if kind == "workspace":
                    result = analyze_workspace(model, settings)
                elif kind == "qualifying":
                    result = analyze_qualifying(model, settings.get("start_soc"),
                                                settings.get("minimum_finish_soc", 5),
                                                settings.get("minimum_start_line_soc", 80))
                else:
                    result = analyze_race(model, settings.get("horizon", 5), settings.get("current_soc"),
                                          settings.get("minimum_soc", 5), settings.get("remaining_laps"))
                result.update({"schema_version": 5, "analysis_id": analysis_id, "analysis_kind": kind,
                               "source_signature": signature,
                               "session_id": session_id, "track_id": model.get("track_id"),
                               "settings": settings, "generated_at": _now()})
                self.storage.save_strategy_artifact(session_id, track_id, kind, analysis_id, result)
                self._set(key, state="completed", progress=100, current="分析完了", error=None,
                          completed_at=result["generated_at"])
            except Exception as error:
                logging.exception("Strategy analysis failed")
                self._set(key, state="failed", progress=100, current="分析失敗", error=str(error),
                          completed_at=_now())
            finally:
                self._queue.task_done()
