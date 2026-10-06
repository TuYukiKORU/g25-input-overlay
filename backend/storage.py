"""Thread-safe, atomic JSON persistence for recorded sessions."""
import json
import os
import hashlib
import threading
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from track_names import track_name, track_slug
from session_names import game_mode_name, session_type_name, session_activity_name


LAP_METADATA_KEYS = (
    "packetFormat", "gameYear", "gameVersion", "udpMode", "sourcePacketFormat", "sourceGameYear",
    "editionDetection", "udpConfigurationWarning", "sessionUid", "trackId", "sessionType", "totalLaps",
    "lapNumber", "lapTimeMs", "validLap", "sampleCount", "createdAt", "setupId", "tyreCompound",
    "tyreAgeLapsAtStart", "tyreAgeLapsAtEnd", "fuelInTankKgAtStart", "fuelInTankKgAtEnd",
    "activeAeroUses", "ersUsageCount", "pitEntryCount", "pitLaneUsed", "note",
    "rewindCount", "recordingRevision",
)


def _normalize_track_profile(value):
    """Read profiles written before the F1 X/Z handedness correction."""
    if not isinstance(value, dict) or value.get("direction_convention", 1) >= 2:
        return value
    has_direction_data = any(corner.get("direction") in ("left", "right")
                             for corner in value.get("corners", [])) or any(
        direction in ("left", "right")
        for chicane in value.get("chicanes", [])
        for direction in chicane.get("directions", [])
    )
    if not has_direction_data:
        return value
    for corner in value.get("corners", []):
        if corner.get("direction") in ("left", "right"):
            corner["direction"] = "right" if corner["direction"] == "left" else "left"
    for chicane in value.get("chicanes", []):
        chicane["directions"] = ["right" if direction == "left" else "left"
                                 for direction in chicane.get("directions", [])]
    value["direction_convention"] = 2
    return value


class LapStorage:
    def __init__(self, root=None):
        supplied_root = root or os.environ.get("F1_SESSIONS_DIR")
        self.root = Path(supplied_root or Path(__file__).resolve().parents[1] / "data" / "sessions")
        self.track_profiles_root = (self.root / "_track_profiles" if supplied_root
                                    else self.root.parent / "track_profiles")
        self._lock = threading.RLock()
        self.session_dir = None
        self._session_uid = None
        self._session_key = None
        self._laps_cache = None
        self._navigation_index = None
        self._recording_paths = {}

    def _write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8") as out:
            json.dump(value, out, ensure_ascii=False, indent=2)
            out.flush(); os.fsync(out.fileno())
        os.replace(temp, path)

    def _safe_session_dir(self, session_id):
        """Resolve a client supplied session id without allowing path traversal."""
        if not isinstance(session_id, str) or not session_id:
            return None
        path = (self.root / session_id).resolve()
        root = self.root.resolve()
        return path if path.parent == root and path.is_dir() else None

    def session_track_laps(self, session_id, track_id=None):
        """Return ``(lap_id, lap)`` pairs for one persisted session/track."""
        session_dir = self._safe_session_dir(session_id)
        if session_dir is None:
            return []
        values = []
        for path in session_dir.glob("track-*/laps/lap_*.json"):
            try:
                lap = json.loads(path.read_text(encoding="utf-8"))
                if track_id is not None and str(lap.get("trackId")) != str(track_id):
                    continue
                lap_id = str(path.relative_to(self.root)).replace("\\", "/")
                values.append((lap_id, lap))
            except (OSError, ValueError):
                continue
        values.sort(key=lambda item: (int(item[1].get("lapNumber") or 0), item[0]))
        return values

    def analysis_path(self, session_id, track_id, name="result.json"):
        session_dir = self._safe_session_dir(session_id)
        if session_dir is None:
            return None
        safe_track = str(track_id).replace("/", "_").replace("\\", "_")
        return session_dir / "analysis" / f"track-{safe_track}" / name

    def load_session_analysis(self, session_id, track_id):
        path = self.analysis_path(session_id, track_id)
        if path is None or not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save_session_analysis(self, session_id, track_id, value):
        path = self.analysis_path(session_id, track_id)
        if path is None:
            raise ValueError("Session not found")
        with self._lock:
            self._write(path, value)

    def load_analysis_status(self, session_id, track_id):
        path = self.analysis_path(session_id, track_id, "status.json")
        if path is None or not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save_analysis_status(self, session_id, track_id, value):
        path = self.analysis_path(session_id, track_id, "status.json")
        if path is None:
            raise ValueError("Session not found")
        with self._lock:
            self._write(path, value)

    def strategy_path(self, session_id, track_id, kind, analysis_id, name="result.json"):
        session_dir = self._safe_session_dir(session_id)
        if session_dir is None or kind not in ("qualifying", "race", "workspace"):
            return None
        safe_track = str(track_id).replace("/", "_").replace("\\", "_")
        safe_id = str(analysis_id)
        if not safe_id or any(character not in "0123456789abcdef" for character in safe_id):
            return None
        return session_dir / "analysis" / f"track-{safe_track}" / "strategies" / kind / safe_id / name

    def load_strategy_artifact(self, session_id, track_id, kind, analysis_id, name="result.json"):
        path = self.strategy_path(session_id, track_id, kind, analysis_id, name)
        if path is None or not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save_strategy_artifact(self, session_id, track_id, kind, analysis_id, value, name="result.json"):
        path = self.strategy_path(session_id, track_id, kind, analysis_id, name)
        if path is None:
            raise ValueError("Invalid strategy result target")
        with self._lock:
            self._write(path, value)

    def track_profile_path(self, track_id):
        safe_track = str(track_id).replace("/", "_").replace("\\", "_")
        return self.track_profiles_root / f"track-{safe_track}.json"

    def load_track_profile(self, track_id):
        path = self.track_profile_path(track_id)
        if not path.is_file():
            return None
        try:
            return _normalize_track_profile(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None

    def save_track_profile(self, track_id, value):
        with self._lock:
            self._write(self.track_profile_path(track_id), value)

    def list_track_profiles(self):
        profiles = []
        if not self.track_profiles_root.exists():
            return profiles
        for path in self.track_profiles_root.glob("track-*.json"):
            try:
                value = _normalize_track_profile(json.loads(path.read_text(encoding="utf-8")))
                if value.get("corners"):
                    profiles.append(value)
            except (OSError, ValueError):
                continue
        return sorted(profiles, key=lambda value: str(value.get("track_id")))

    def start_session(self, metadata):
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        with self._lock:
            uid = metadata.get("sessionUid")
            track_id = metadata.get("trackId")
            uid_label = f"{int(uid):016x}"[-8:] if uid is not None else "manual"
            track_label = f"_track-{track_id}" if track_id is not None else ""
            base = self.root / f"{stamp}_session-{uid_label}{track_label}"
            self.session_dir = base
            attempt = 2
            while self.session_dir.exists():
                self.session_dir = self.root / f"{base.name}_{attempt:03d}"
                attempt += 1
            self._session_uid = uid
            self._session_key = (uid, track_id, metadata.get("sessionLinkIdentifier"), metadata.get("sessionType"))
            metadata = metadata.copy()
            metadata.setdefault("sessionUidHex", f"{int(uid):016x}" if uid is not None else None)
            metadata.setdefault("trackName", track_name(track_id) if track_id is not None else None)
            metadata.setdefault("sessionTypeName", session_type_name(metadata.get("sessionType")))
            metadata.setdefault("gameModeName", game_mode_name(metadata.get("gameMode")))
            self._write(self.session_dir / "session.json", metadata)

    def _lap_directory(self, lap):
        uid = lap.get("sessionUid")
        track_id = lap.get("trackId")
        session_key = (uid, track_id, lap.get("sessionLinkIdentifier"), lap.get("sessionType"))
        if self.session_dir is None or session_key != self._session_key:
            self.start_session({"sessionUid": uid, "packetFormat": lap.get("packetFormat"),
                                "gameYear": lap.get("gameYear"), "gameVersion": lap.get("gameVersion"),
                                "udpMode": lap.get("udpMode"),
                                "sourcePacketFormat": lap.get("sourcePacketFormat"),
                                "sourceGameYear": lap.get("sourceGameYear"),
                                "editionDetection": lap.get("editionDetection"),
                                "formula": lap.get("formula"),
                                "udpConfigurationWarning": lap.get("udpConfigurationWarning"),
                                "sessionType": lap.get("sessionType"),
                                "totalLaps": lap.get("totalLaps"),
                                "sessionTypeName": lap.get("sessionTypeName"),
                                "gameMode": lap.get("gameMode"),
                                "gameModeName": lap.get("gameModeName"),
                                "seasonLinkIdentifier": lap.get("seasonLinkIdentifier"),
                                "weekendLinkIdentifier": lap.get("weekendLinkIdentifier"),
                                "sessionLinkIdentifier": lap.get("sessionLinkIdentifier"),
                                "trackId": track_id,
                                "createdAt": datetime.now(timezone.utc).isoformat()})
        track_dir = self.session_dir / f"track-{track_id}-{track_slug(track_id)}"
        self._write(track_dir / "track.json", {"trackId": track_id, "trackName": track_name(track_id)})
        return track_dir / "laps", track_dir

    def _store_setup(self, track_dir, setup):
        """Deduplicate setup snapshots; laps retain only a short reference."""
        if not isinstance(setup, dict) or not setup:
            return None
        encoded = json.dumps(setup, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        setup_id = hashlib.sha256(encoded).hexdigest()[:12]
        path = track_dir / "setups" / f"setup-{setup_id}.json"
        if not path.exists():
            self._write(path, {"setupId": setup_id, **setup})
        return setup_id

    def save_lap(self, lap):
        with self._lock:
            lap = lap.copy()
            laps_dir, track_dir = self._lap_directory(lap)
            setup_id = self._store_setup(track_dir, lap.pop("_carSetup", None))
            if setup_id:
                lap["setupId"] = setup_id
            # These describe the parent session and would otherwise be repeated
            # in every large lap file. Keep only sessionType/sessionUid/trackId
            # on laps for compatibility; richer identity lives in session.json.
            for key in ("sessionTypeName", "gameMode", "gameModeName",
                        "seasonLinkIdentifier", "weekendLinkIdentifier",
                        "sessionLinkIdentifier"):
                lap.pop(key, None)
            base = laps_dir / f"lap_{int(lap['lapNumber']):03d}.json"
            recording_key = (str(laps_dir), lap.get("recordingId"))
            revision_path = self._recording_paths.get(recording_key) if lap.get("recordingId") else None
            path = revision_path or base
            attempt = 2
            while not revision_path and path.exists():
                path = laps_dir / f"lap_{int(lap['lapNumber']):03d}_{attempt:03d}.json"
                attempt += 1
            if revision_path and path.exists():
                old = json.loads(path.read_text(encoding="utf-8"))
                self._write(track_dir / "rewind-revisions" /
                            f"revision-{path.stem}-{old.get('recordingRevision', 1)}.json", old)
                if old.get("note") and not lap.get("note"):
                    lap["note"] = old["note"]
            self._write(path, lap)
            if lap.get("recordingId"):
                self._recording_paths[recording_key] = path
            self._laps_cache = None
            if revision_path:
                # A replayed lap can be slower or invalid. Rebuild the derived
                # best rather than leaving the superseded result as reference.
                candidates = [json.loads(p.read_text(encoding="utf-8")) for p in laps_dir.glob("lap_*.json")]
                best = min((value for value in candidates if value.get("validLap")),
                           key=lambda value: value["lapTimeMs"], default=None)
                best_path = track_dir / "best_lap.json"
                if best is not None:
                    self._write(best_path, best)
                else:
                    best_path.unlink(missing_ok=True)
            elif lap.get("validLap"):
                best_path = track_dir / "best_lap.json"
                try: best = json.loads(best_path.read_text(encoding="utf-8"))
                except (OSError, ValueError): best = None
                if best is None or lap["lapTimeMs"] < best["lapTimeMs"]:
                    self._write(best_path, lap)

    def _lap_paths(self):
        return sorted(self.root.rglob("lap_*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if self.root.exists() else []

    def _load_navigation_index(self):
        if self._navigation_index is None:
            try:
                value = json.loads((self.root / ".navigation-index.json").read_text(encoding="utf-8"))
                entries = value.get("entries") if isinstance(value, dict) and value.get("version") == 1 else None
                self._navigation_index = entries if isinstance(entries, dict) else {}
            except (OSError, ValueError):
                self._navigation_index = {}
        return self._navigation_index

    def _save_navigation_index(self, entries):
        # This is a disposable cache. A read-only recording folder must still
        # be usable, and independent app processes must not share a temp file.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root,
                    prefix=".navigation-index-", suffix=".tmp", delete=False) as out:
                temporary = Path(out.name)
                json.dump({"version": 1, "entries": entries}, out, ensure_ascii=False, separators=(",", ":"))
            os.replace(temporary, self.root / ".navigation-index.json")
        except OSError:
            pass
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def list_laps(self, refresh=False):
        with self._lock:
            if refresh or self._laps_cache is None:
                paths = self._lap_paths()
                signature = tuple((str(path), path.stat().st_size, path.stat().st_mtime_ns) for path in paths)
                if signature != getattr(self, "_laps_cache_signature", None):
                    self._laps_cache = None
                    self._laps_cache_signature = signature
            if self._laps_cache is None:
                previous = self._load_navigation_index()
                result, updated = [], {}
                for p in paths:
                    try:
                        lap_id = p.relative_to(self.root).as_posix()
                        stat = p.stat()
                        file_signature = [stat.st_size, stat.st_mtime_ns]
                        cached = previous.get(lap_id)
                        metadata = cached.get("metadata") if isinstance(cached, dict) else None
                        if (not isinstance(metadata, dict) or cached.get("signature") != file_signature
                                or not all(key in metadata for key in LAP_METADATA_KEYS)):
                            lap = json.loads(p.read_text(encoding="utf-8"))
                            if not isinstance(lap, dict):
                                continue
                            metadata = {key: lap.get(key) for key in LAP_METADATA_KEYS}
                        updated[lap_id] = {"signature": file_signature, "metadata": metadata}
                        result.append(metadata | {"trackName": track_name(metadata.get("trackId")),
                            "session": p.relative_to(self.root).parts[0], "id": lap_id})
                    except (OSError, ValueError):
                        continue
                if updated != previous:
                    self._save_navigation_index(updated)
                self._navigation_index = updated
                self._laps_cache = result
            return [item | {"sessionActivityName": session_activity_name(item.get("sessionType"))}
                    for item in self._laps_cache]

    def load_lap(self, lap_id):
        path = (self.root / lap_id).resolve()
        if self.root.resolve() not in path.parents or not path.is_file():
            return None
        try: return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError): return None

    def load_lap_setup(self, lap_id):
        lap = self.load_lap(lap_id)
        setup_id = (lap or {}).get("setupId")
        if not isinstance(setup_id, str) or len(setup_id) != 12 or any(c not in "0123456789abcdef" for c in setup_id):
            return None
        path = (self.root / lap_id).resolve().parent.parent / "setups" / f"setup-{setup_id}.json"
        if self.root.resolve() not in path.resolve().parents:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def update_lap_note(self, lap_id, note):
        path = (self.root / lap_id).resolve()
        if self.root.resolve() not in path.parents or not path.is_file():
            return None
        with self._lock:
            try: lap = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError): return None
            lap["note"] = note
            lap["noteUpdatedAt"] = datetime.now(timezone.utc).isoformat()
            self._write(path, lap)
            self._laps_cache = None
            return lap

    def session_laps(self, lap_id):
        """Load laps from the selected lap's session directory, newest first."""
        selected = (self.root / lap_id).resolve()
        if self.root.resolve() not in selected.parents or not selected.is_file(): return []
        values = []
        for path in selected.parent.glob("lap_*.json"):
            try: values.append((path, json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError): pass
        values.sort(key=lambda item: item[0].stat().st_mtime, reverse=True)
        return values

    def session_reference(self, lap_id):
        valid = [lap for _, lap in self.session_laps(lap_id) if lap.get("validLap")]
        return min(valid, key=lambda lap: lap.get("lapTimeMs", float("inf")), default=None)

    def previous_lap(self, lap_id):
        selected = (self.root / lap_id).resolve()
        laps = self.session_laps(lap_id)
        for index, (path, _) in enumerate(laps):
            if path == selected and index + 1 < len(laps): return laps[index + 1][1]
        return None

    def hierarchy(self):
        """Return session -> track -> laps metadata for navigation clients."""
        sessions = {}
        for lap in self.list_laps():
            session_id = lap["session"]
            if session_id not in sessions:
                metadata = {}
                try:
                    metadata = json.loads((self.root / session_id / "session.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pass
                session_type = metadata.get("sessionType", lap.get("sessionType"))
                game_mode = metadata.get("gameMode")
                sessions[session_id] = {
                    "id": session_id, "tracks": {}, "sessionUid": metadata.get("sessionUid", lap.get("sessionUid")),
                    "sessionUidHex": metadata.get("sessionUidHex"), "sessionType": session_type,
                    "sessionTypeName": metadata.get("sessionTypeName") or session_type_name(session_type),
                    "gameMode": game_mode,
                    "gameModeName": metadata.get("gameModeName") or game_mode_name(game_mode),
                    "seasonLinkIdentifier": metadata.get("seasonLinkIdentifier"),
                    "weekendLinkIdentifier": metadata.get("weekendLinkIdentifier"),
                    "sessionLinkIdentifier": metadata.get("sessionLinkIdentifier"),
                }
            session = sessions[session_id]
            key = str(lap.get("trackId"))
            track = session["tracks"].setdefault(key, {"trackId": lap.get("trackId"),
                                                        "trackName": lap["trackName"], "laps": []})
            track["laps"].append(lap)
        result = []
        for session in sessions.values():
            tracks = list(session["tracks"].values())
            # Older folders may contain several session types. Prefer lap evidence
            # over the parent metadata and expose all types without moving files.
            types = list(dict.fromkeys(lap["sessionType"] for track in tracks for lap in track["laps"]
                                       if lap.get("sessionType") not in (None, 0)))
            names = [session_activity_name(value) for value in types] or [
                session_activity_name(session["sessionType"], session["gameMode"])]
            result.append(session | {"tracks": tracks, "sessionTypes": types,
                                    "sessionActivityName": " / ".join(names)})
        return result
