import math
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import analysis_worker as worker_module
from analysis_worker import AnalysisWorker
from session_analysis import analyze_session
from storage import LapStorage
from session_analysis import _interp, _turn_metrics


def session_lap(number, extra_per_section=0, positions=True, ers=False):
    samples = []
    elapsed = 0
    for distance in range(0, 1210, 10):
        elapsed += 500 + (extra_per_section if 500 <= distance < 600 else 0)
        sample = {
            "lap_distance": distance, "lap_time_ms": elapsed, "speed": 180,
            "throttle": .8, "brake": 0, "ers_usage": bool(ers and 500 <= distance < 600),
            "ers_percent": 60 - distance / 100, "drs": 0, "pit_status": 0,
            "wheel_slip_ratio": {}, "wheel_speed": {},
        }
        if positions:
            sample["position"] = {"x": distance, "y": 0, "z": 0}
        samples.append(sample)
    return {
        "sessionUid": 1, "trackId": 7, "lapNumber": number, "lapTimeMs": elapsed,
        "validLap": True, "sampleCount": len(samples), "samples": samples,
        "tyreWearAtStart": {wheel: 10 + number for wheel in ("front_left", "front_right", "rear_left", "rear_right")},
        "tyreWearAtEnd": {wheel: 11 + number for wheel in ("front_left", "front_right", "rear_left", "rear_right")},
    }


def test_comparison_prefers_matching_compound_setup_and_starting_fuel():
    selected, wrong, matched = [session_lap(i) for i in (1, 2, 3)]
    for lap in (selected, wrong, matched):
        lap.update(tyreCompound="Soft", setupId="same", fuelInTankKgAtStart=10)
    wrong.update(tyreCompound="Hard", setupId="other", fuelInTankKgAtStart=40)
    result = analyze_session([("selected", selected), ("wrong", wrong), ("matched", matched)], "selected")
    assert result["comparison_lap_id"] == "matched"
    assert result["comparison_context"]["unknown_fields"] == 0


def test_session_gap_is_not_interpolated_or_used_for_turn_coaching():
    rows = [{"s": 0, "time": 0}, {"s": 100, "time": 1000}]
    assert _interp(rows, 50, "time") is None
    assert _turn_metrics({"samples": rows}, {"start_distance": 0, "end_distance": 100, "apex_distance": 50}) is None


def corner_session_lap(number, slower=False):
    points, distance = [], 0.0
    for x in range(0, 201, 5):
        points.append((distance, x, 0)); distance += 5
    for degree in range(-90, 1, 5):
        angle = math.radians(degree)
        points.append((distance, 200 + 50 * math.cos(angle), 50 + 50 * math.sin(angle)))
        distance += math.radians(5) * 50
    for degree in range(180, 89, -5):
        angle = math.radians(degree)
        points.append((distance, 300 + 50 * math.cos(angle), 50 + 50 * math.sin(angle)))
        distance += math.radians(5) * 50
    for x in range(305, 901, 5):
        points.append((distance, x, 100)); distance += 5
    elapsed, samples = 0.0, []
    for index, (lap_distance, x, z) in enumerate(points):
        speed = 118 if slower and 190 <= lap_distance <= 390 else 145
        if index:
            elapsed += (lap_distance - points[index - 1][0]) / (speed / 3.6) * 1000
        samples.append({
            "lap_distance": lap_distance, "lap_time_ms": elapsed, "speed": speed,
            "position": {"x": x, "y": 0, "z": z}, "throttle": .7, "brake": .1,
            "ers_usage": False, "ers_percent": 55, "drs": 0, "pit_status": 0,
            "wheel_slip_ratio": {}, "wheel_speed": {},
        })
    return {
        "sessionUid": 2, "trackId": 8, "lapNumber": number, "lapTimeMs": elapsed,
        "validLap": True, "sampleCount": len(samples), "samples": samples,
    }


def test_session_analysis_builds_theoretical_lap_and_section_output():
    result = analyze_session([
        ("session/lap_001.json", session_lap(1, 0, ers=True)),
        ("session/lap_002.json", session_lap(2, 20, ers=False)),
        ("session/lap_003.json", session_lap(3, 10, ers=True)),
    ], "session/lap_002.json")
    assert result["analyzable"] is True
    assert result["theoretical_fastest_ms"] > 0
    assert result["selected_estimated_loss_ms"] > 0
    assert len(result["top_improvement_sections"]) == 5
    assert all("best_lap_number" in section for section in result["sections"])
    assert result["sample_counts"]["eligible_laps"] == 3


def test_session_analysis_reports_reason_instead_of_guessing_without_xyz():
    result = analyze_session([("a", session_lap(1, positions=False)), ("b", session_lap(2, positions=False))])
    assert result["analyzable"] is False
    assert "XYZ" in result["reason"]
    assert result["confidence"]["label"] == "unavailable"


def test_session_analysis_reports_turn_metrics_and_chicane_membership():
    result = analyze_session([
        ("session/lap_001.json", corner_session_lap(1)),
        ("session/lap_002.json", corner_session_lap(2, slower=True)),
        ("session/lap_003.json", corner_session_lap(3)),
    ], "session/lap_002.json")
    assert result["analyzable"] is True
    assert [turn["label"] for turn in result["turns"]] == ["T1", "T2"]
    assert all(turn["complex_type"] == "chicane" for turn in result["turns"])
    assert all(turn["time_delta_ms"] > 0 for turn in result["turns"])
    assert all(turn["selected"]["entry_speed_kph"] is not None for turn in result["turns"])


def test_session_analysis_reuses_supplied_track_corner_profile():
    profile = {
        "analyzable": True, "reason": None,
        "settings": {"threshold": .0066, "smoothing_m": 20, "min_length_m": 15},
        "corners": [{"label": "T1", "direction": "left", "start_distance": 205,
                     "apex_distance": 245, "end_distance": 275, "radius_m": 50}],
        "chicanes": [], "profile": {"track_id": 8, "updated_at": "test"},
    }
    result = analyze_session([
        ("session/lap_001.json", corner_session_lap(1)),
        ("session/lap_002.json", corner_session_lap(2, slower=True)),
        ("session/lap_003.json", corner_session_lap(3)),
    ], "session/lap_002.json", turn_definition=profile)
    assert [(turn["label"], turn["start_distance"], turn["end_distance"])
            for turn in result["turns"]] == [("T1", 205, 275)]
    assert result["turn_definition"]["profile"]["track_id"] == 8


def test_worker_deduplicates_active_job_and_persists_result(tmp_path, monkeypatch):
    store = LapStorage(tmp_path)
    store.start_session({"sessionUid": 1})
    store.save_lap(session_lap(1))
    store.save_lap(session_lap(2, 20))
    session_id = store.session_dir.name
    selected_id = store.list_laps()[0]["id"]
    entered, release = threading.Event(), threading.Event()
    original = worker_module.analyze_session

    def delayed(*args, **kwargs):
        entered.set(); release.wait(2)
        return original(*args, **kwargs)

    monkeypatch.setattr(worker_module, "analyze_session", delayed)
    worker = AnalysisWorker(store)
    first, started = worker.start(session_id, 7, selected_id)
    assert started and first["state"] == "queued"
    assert entered.wait(1)
    duplicate, duplicate_started = worker.start(session_id, 7, selected_id)
    assert duplicate_started is False
    assert duplicate["state"] == "running"
    release.set()
    deadline = time.time() + 3
    while time.time() < deadline and worker.status(session_id, 7)["state"] != "completed":
        time.sleep(.02)
    assert worker.status(session_id, 7)["state"] == "completed"
    assert store.load_session_analysis(session_id, 7)["analyzable"] is True
