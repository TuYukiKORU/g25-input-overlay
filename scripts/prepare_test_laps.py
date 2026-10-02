"""Create a reproducible laptop dataset from actual recorded laps, not simulation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

PROJECT = Path(__file__).resolve().parents[1]
SESSIONS = (
    "2026-08-25_02-55-47_session-485a70e1_track-3",
    "2026-08-14_16-52-57_session-c8f4d34b_track-15",
    "2026-09-11_20-37-10_session-736ff89d_track-42",
)


def prepare(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Test output must be separate from source recordings")
    if destination.exists():
        raise ValueError(f"Output already exists: {destination}. Choose a new output folder.")
    missing = [name for name in SESSIONS if not (source / name).is_dir()]
    if missing:
        raise ValueError(f"Source sessions missing: {', '.join(missing)}")
    destination.mkdir(parents=True)
    manifest = {"version": 1, "description": "Copies of real previous laps. Invalid laps remain invalid; no synthetic samples.",
                "sessions": [], "files": {}}
    for name in SESSIONS:
        source_session = source / name
        metadata = json.loads((source_session / "session.json").read_text(encoding="utf-8"))
        entry = {"session": name, "track_id": metadata.get("trackId"),
                 "track_name": metadata.get("trackName"), "laps": 0, "valid_laps": 0,
                 "lap_numbers": [], "samples": 0}
        # Include setup snapshots and track metadata, omit cached jobs/results.
        for path in sorted(source_session.rglob("*.json")):
            relative = path.relative_to(source_session)
            if "analysis" in relative.parts or path.name == "best_lap.json":
                continue
            if not (path.name in ("session.json", "track.json") or path.name.startswith(("lap_", "setup-"))):
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            if path.name.startswith("lap_"):
                value.pop("note", None)
                value.pop("noteUpdatedAt", None)
                entry["laps"] += 1
                entry["valid_laps"] += int(bool(value.get("validLap")))
                entry["lap_numbers"].append(value.get("lapNumber"))
                entry["samples"] += len(value.get("samples", []))
            target = destination / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            # Preserve all telemetry precision; compact whitespace only.
            target.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        # Recreate best_lap using only the actual included valid laps.
        for track in (destination / name).glob("track-*"):
            laps = [json.loads(path.read_text(encoding="utf-8")) for path in (track / "laps").glob("lap_*.json")]
            clean = [lap for lap in laps if lap.get("validLap") and lap.get("lapTimeMs", 0) > 0]
            if clean:
                (track / "best_lap.json").write_text(json.dumps(min(clean, key=lambda lap: lap["lapTimeMs"]),
                    ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        profile = source.parent / "track_profiles" / f"track-{metadata.get('trackId')}.json"
        if profile.is_file():
            profiles = destination / "_track_profiles"
            profiles.mkdir(exist_ok=True)
            shutil.copy2(profile, profiles / profile.name)
        manifest["sessions"].append(entry)
    for path in sorted(destination.rglob("*.json")):
        manifest["files"][path.relative_to(destination).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest["lap_count"] = sum(entry["laps"] for entry in manifest["sessions"])
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=PROJECT / "data" / "sessions")
    parser.add_argument("--output", type=Path, default=PROJECT / ".build-assets" / "test-laps")
    args = parser.parse_args()
    result = prepare(args.source, args.output)
    print(json.dumps({"lap_count": result["lap_count"], "sessions": result["sessions"]}, indent=2))
