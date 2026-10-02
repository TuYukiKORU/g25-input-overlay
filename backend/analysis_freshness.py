"""Snapshot identities for persisted analysis results."""
import hashlib
import json
import sys
from pathlib import Path
from runtime_paths import resource_root


def rules_signature():
    # Frozen modules have no .py source files. The build records the same
    # fingerprint so cached analyses still become stale when rules change.
    if getattr(sys, "frozen", False):
        return json.loads((resource_root() / "build-info.json").read_text(encoding="utf-8"))["rules_signature"]
    root = Path(__file__).parent
    names = ("analysis_config.py", "lap_analyzer.py", "comparison_context.py", "session_analysis.py",
             "workspace_insights.py", "track_sections.py", "strategy_model.py", "strategy_scenarios.py",
             "qualifying_optimizer.py", "race_optimizer.py", "operation_sections.py", "ers_strategy.py")
    digest = hashlib.sha256()
    for name in names:
        digest.update((root / name).read_bytes())
    return digest.hexdigest()[:16]


def source_signature(storage, track_id, session_id=None):
    records = []
    for item in storage.list_laps(refresh=True):
        if str(item.get("trackId")) != str(track_id) or (session_id is not None and item.get("session") != session_id):
            continue
        path = storage.root / item["id"]
        try:
            stat = path.stat()
            records.append((item["id"], stat.st_size, stat.st_mtime_ns))
        except OSError:
            records.append((item["id"], "missing"))
        setup_id = item.get("setupId")
        if isinstance(setup_id, str) and len(setup_id) == 12 and all(c in "0123456789abcdef" for c in setup_id):
            setup_path = path.parent.parent / "setups" / f"setup-{setup_id}.json"
            try:
                setup_stat = setup_path.stat()
                records.append((str(setup_path.relative_to(storage.root)), setup_stat.st_size, setup_stat.st_mtime_ns))
            except OSError:
                records.append((item["id"] + "/setup", "missing"))
    payload = {"laps": sorted(records), "profile": storage.load_track_profile(track_id), "rules": rules_signature()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def freshness(storage, result, track_id, session_id=None):
    current = source_signature(storage, track_id, session_id)
    stale = result.get("source_signature") != current
    return {"stale": stale, "freshness_reason": "Recordings, corner definitions or analysis rules changed; reanalyse to refresh" if stale else None}
