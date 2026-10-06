"""Readiness, condition isolation, planner constraints and shared job API."""
from copy import deepcopy
from pathlib import Path
import sys
import time
import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from analysis_routes import create_analysis_blueprint
from operation_sections import analyze_operation_sections
from race_optimizer import optimize_race
from qualifying_optimizer import optimize_qualifying
from session_analysis import analyze_session
from storage import LapStorage
from strategy_model import build_strategy_model, _observation, _rows, _clip_threshold, _qualifying_power_calibration, _qualifying_overtake
from strategy_scenarios import compare_strategy_scenarios, optimize_multi_lap_strategy, _options
from strategy_worker import StrategyWorker
from telemetry_quality import lap_quality
from test_strategy_analysis import strategy_lap, model
from test_session_analysis import session_lap


@pytest.mark.parametrize("position", [None, {"x": 0, "z": 0}])
def test_energy_planning_survives_missing_or_collapsed_geometry(position):
    entries = []
    for number in (1, 2, 3):
        lap = strategy_lap(number, active=number % 2 == 0)
        for sample in lap["samples"]:
            sample["position"] = position
        entries.append((f"session/lap{number}", lap))
    value = build_strategy_model(entries, selected_session_id="session", pace_window_percent=15)
    assert value["analyzable"]
    assert not value["geometry"]["available"]
    assert value["track_points"] == []
    assert optimize_multi_lap_strategy(value, horizon=3, start_soc=70)["analyzable"]
    assert analyze_operation_sections(entries[0][1])["sections"]


@pytest.mark.parametrize("missing", ["ers_soc", "lap_time_ms", "throttle"])
def test_actual_energy_readiness_rejects_metadata_only_laps(missing):
    lap = strategy_lap(1)
    for sample in lap["samples"]:
        sample.pop(missing, None)
        if missing == "ers_soc":
            sample.pop("ers_percent", None)
    assert not lap_quality(lap)["energy"]["available"]


def test_selected_edition_and_known_conditions_cannot_mix_in_strategy_sources():
    reference = strategy_lap(1)
    entries = [("s/lap1", reference), ("s/lap2", strategy_lap(2))]
    for field, value in (("gameYear", 25), ("tyreCompound", "Hard (C1)"), ("setupId", "other")):
        lap = strategy_lap(len(entries)+1)
        lap[field] = value
        if field == "gameYear":
            lap["packetFormat"] = 2025
        if field == "setupId":
            reference["setupId"] = entries[1][1]["setupId"] = "matching"
        entries.append((f"other/{field}", lap))
    result = build_strategy_model(entries, selected_session_id="s", selected_lap_id="s/lap1", pace_window_percent=15)
    assert result["source"]["lap_ids"] == ["s/lap1", "s/lap2"]
    assert result["selection"]["excluded"]["different_track_or_edition"] == 1
    assert result["selection"]["excluded"]["different_compound"] == 1
    assert result["selection"]["excluded"]["different_setup"] == 1
    old = build_strategy_model(entries, selected_session_id="other", selected_lap_id="other/gameYear")
    assert not old["analyzable"]
    assert old["selection"]["reference_quality"]["edition"] == 2025


def test_session_review_uses_a_shared_planar_frame_for_older_xz_recordings():
    a, b = session_lap(1), session_lap(2, extra_per_section=10)
    for sample in a["samples"]:
        sample["position"].pop("y")
    result = analyze_session([("a", a), ("b", b)])
    assert result["analyzable"]
    assert result["coordinate_mode"] == "planar_xz"


def simple_model():
    predictions = {"none": (1000, -1), "boost": (800, -3), "overtake": (750, -4),
                   "lift_10": (1100, 0), "lift_20": (1200, 1), "lift_30": (1300, 2)}
    actions = {name: {"predicted_time_ms": time_ms, "soc_delta": soc, "evidence": "observed", "confidence": 1,
                      "clipping_probability": 0, "super_clipping_probability": 0, "tyre_cost": 0}
               for name, (time_ms, soc) in predictions.items()}
    return {"analyzable": True, "initial_soc": 50, "current_state": {"soc": 50},
            "sections": [{"number": 1, "kind": "flat_out", "start_distance": 0, "end_distance": 1000, "actions": actions}]}


def test_contradictory_lift_associations_are_not_turned_into_recharge_instructions():
    value = simple_model()
    for action in ("lift_10", "lift_20", "lift_30"):
        value["sections"][0]["actions"][action].update(predicted_time_ms=10, soc_delta=-10)
    result = optimize_multi_lap_strategy(value, horizon=3, remaining_laps=3, start_soc=50)
    assert result["analyzable"]
    assert all(not allocation["action"].startswith("lift") for allocation in result["allocations"])


def test_reserve_is_never_silently_lowered_and_empty_battery_is_not_borrowed():
    value = simple_model()
    assert not optimize_multi_lap_strategy(value, start_soc=5, minimum_finish_soc=10)["analyzable"]
    for action in value["sections"][0]["actions"].values():
        action["soc_delta"] = -10
    assert not compare_strategy_scenarios(value, start_soc=5)["analyzable"]


def test_qualifying_always_starts_full_and_targets_empty_with_honest_feasibility():
    value = simple_model()
    # Existing actions cannot consume a full battery in this lap.
    plan = optimize_qualifying(value, start_soc=40, minimum_finish_soc=25, minimum_start_line_soc=80)
    assert plan["analyzable"] and plan["start_soc"] == plan["start_line_soc"] == 100
    assert plan["target_finish_soc"] == plan["minimum_finish_soc"] == 0
    assert plan["predicted_finish_soc"] == 96
    assert not plan["finish_target_reached"]
    assert plan["pre_start_runup"]["predicted_soc_cost"] == 0
    value["sections"][0]["actions"]["overtake"]["soc_delta"] = -100
    exact = optimize_qualifying(value)
    assert exact["finish_target_reached"] and exact["predicted_finish_soc"] == 0
    assert all(row["soc"] >= 0 for row in exact["soc_trace"])


def test_qualifying_does_not_borrow_battery_to_manufacture_the_empty_finish():
    value = simple_model()
    value["sections"][0]["actions"]["overtake"]["soc_delta"] = -101
    plan = optimize_qualifying(value)
    assert plan["predicted_finish_soc"] > 0 and not plan["finish_target_reached"]
    assert all(row["action"] != "overtake" or row["applied_fraction"] < 1 for row in plan["allocations"])
    assert all(row["soc"] >= 0 for row in plan["soc_trace"])


def test_qualifying_ignores_a_legacy_boost_mode_request():
    plan = optimize_qualifying(simple_model(), deployment_mode="boost")
    assert plan["deployment_mode"] == plan["pre_start_runup"]["action"] == "overtake"
    assert plan["predicted_finish_soc"] == 96
    assert all(a["action"] != "boost" for a in plan["allocations"])


def test_qualifying_calibration_integrates_power_headroom_without_assuming_capacity():
    value = simple_model()
    section = value["sections"][0]
    inferred = dict(section["actions"]["overtake"], evidence="inferred", confidence=.2,
                    clipping_probability=1, super_clipping_probability=1)
    # Two seconds at a measured 100 kW versus an observed 300 kW envelope:
    # 400 kJ extra energy is 10% of the measured 4 MJ battery.
    items = [{"rows": [{"s": i * 100, "t": i * 200, "speed": 220, "throttle": 1,
                         "brake": 0, "mguk": power, "soc": 50, "store_j": 2_000_000}
                        for i in range(11)], "clip_threshold": 20_000}
             for power in (100_000, 300_000)]
    calibration = _qualifying_power_calibration(items)
    prediction = _qualifying_overtake(section, inferred, section["actions"]["none"], items, calibration)
    assert calibration["capacity_j"] == 4_000_000
    # Median headroom across the two laps is 5% (one lap already at the envelope).
    assert prediction["soc_cost"] == pytest.approx(5)
    assert prediction["soc_delta"] == pytest.approx(-6)
    assert prediction["clipping_probability"] == prediction["super_clipping_probability"] == 0
    section["actions"]["overtake"] = inferred
    section["qualifying_overtake"] = prediction
    before = deepcopy(value)
    plan = optimize_qualifying(value)
    assert plan["predicted_finish_soc"] == 94
    assert plan["energy_estimation"] and plan["calibrated_overtake_sections"] == [1]
    assert value == before  # Race predictions retain their evidence and clipping gates.
    assert not any(a == "overtake" for a, _, _ in _options(section, "deployment_only", "overtake"))
    for item in items:
        for row in item["rows"]:
            row["store_j"] = None
    assert _qualifying_power_calibration(items) is None


def test_qualifying_calibration_preserves_observed_actions_and_speed_clipping():
    value = simple_model()
    section = value["sections"][0]
    observed = section["actions"]["overtake"]
    assert _qualifying_overtake(section, observed, section["actions"]["none"], [], {}) is None
    section["qualifying_overtake"] = dict(observed, evidence="inferred", confidence=.2,
                                         energy_method="measured_power_envelope", clipping_probability=.8)
    plan = optimize_qualifying(value)
    assert all(a["action"] != "overtake" for a in plan["allocations"])


def test_endpoint_tolerance_excludes_unmatched_scenarios_from_the_ranking():
    value = simple_model()
    # Coarse action fractions cannot make every alternative hit this terminal reserve.
    value["sections"][0]["actions"]["boost"]["soc_delta"] = -.3
    result = compare_strategy_scenarios(value, start_soc=50)
    ranked = [r for r in result["scenarios"] if r["comparable"]]
    assert all(abs(r["predicted_finish_soc"] - result["common_finish_soc"]) <= .25 for r in ranked)
    assert next(r for r in result["scenarios"] if r["id"] == result["fastest_scenario"])["comparable"]


def test_old_race_api_and_workspace_use_identical_race_energy_predictions():
    value = model()
    old = optimize_race(value, horizon=3, remaining_laps=8, current_soc=60, minimum_soc=10)
    shared = optimize_multi_lap_strategy(value, horizon=3, remaining_laps=8, start_soc=60, minimum_finish_soc=10)
    assert old["trajectory"] == shared["trajectory"]
    assert old["predicted_finish_soc"] == shared["predicted_finish_soc"]


def test_section_partition_does_not_drop_boundary_time_or_battery_changes():
    value = model()
    assert value["sections"][0]["start_distance"] == 0
    assert value["sections"][-1]["end_distance"] == value["track_length_m"]
    assert all(a["end_distance"] == b["start_distance"] for a, b in zip(value["sections"], value["sections"][1:]))
    lap = strategy_lap(1)
    rows = _rows(lap)
    item = {"id": "s/lap1", "session": "s", "lap": lap, "rows": rows,
            "best_time": value["best_lap_time_ms"], "sample_elapsed_ms": rows[-1]["t"]-rows[0]["t"],
            "clip_threshold": _clip_threshold(rows)}
    observations = [_observation(item, section) for section in value["sections"]]
    assert sum(row["normalized_time_ms"] for row in observations) == pytest.approx(value["best_lap_time_ms"])
    assert sum(row["soc_delta"] for row in observations) == pytest.approx(rows[-1]["soc"]-rows[0]["soc"])


@pytest.fixture
def workspace_api(tmp_path):
    storage = LapStorage(tmp_path)
    for number in (1, 2, 3):
        lap = strategy_lap(number, active=number % 2 == 0)
        lap["sessionUid"] = 123
        storage.save_lap(lap)
    session = storage.session_dir.name
    worker = StrategyWorker(storage)
    app = Flask(__name__)
    app.register_blueprint(create_analysis_blueprint(storage, worker, {}))
    return app.test_client(), storage, worker, session


def test_shared_job_runs_caches_and_returns_one_plan_and_source_snapshot(workspace_api):
    client, storage, worker, session = workspace_api
    selected = storage.list_laps()[0]["id"]
    url = f"/api/sessions/{session}/analysis/workspace"
    settings = {"track_id": 11, "selected_lap_id": selected, "goal": "race", "start_soc": 70, "horizon": 3}
    started = client.post(url, json=settings)
    assert started.status_code == 202
    analysis_id = started.get_json()["analysis_id"]
    deadline = time.monotonic()+5
    while worker.status(session, 11, "workspace", analysis_id)["state"] in ("queued", "running"):
        assert time.monotonic() < deadline
        time.sleep(.01)
    params = {"track_id": 11, "analysis_id": analysis_id}
    result = client.get(url+"/result", query_string=params).get_json()
    assert result["analyzable"] and not result["stale"]
    assert result["plan"]["current_lap_recommendation"] == result["plan"]["trajectory"][0]
    assert result["model_summary"]["selection"]["reference_lap_id"] == selected
    assert not result["evidence"]["accuracy_validated"]
    assert client.post(url, json=settings).get_json()["cached"]
    assert client.get(f"/api/sessions/{session}/strategy-context", query_string={"track_id": 11,"selected_lap_id": selected}).get_json()["readiness"]["ready"]


@pytest.mark.parametrize("bad", [{"start_soc": float("nan")}, {"goal": "race", "start_soc": 55}, {"goal": "pits"}, {"selected_lap_id": "../other"}, ["bad"]])
def test_workspace_rejects_nonfinite_settings_and_foreign_lap_ids(workspace_api, bad):
    client, _, _, session = workspace_api
    body = {"track_id": 11, **bad} if isinstance(bad, dict) else bad
    assert client.post(f"/api/sessions/{session}/analysis/workspace", json=body).status_code == 400


@pytest.mark.parametrize("kind", ["workspace", "qualifying"])
def test_qualifying_api_canonicalizes_old_custom_battery_inputs(workspace_api, monkeypatch, kind):
    client, _, worker, session = workspace_api
    received = []
    def start(kind, session_id, track_id, settings, force):
        received.append(settings)
        return {"analysis_id": "test", "state": "queued"}, True
    monkeypatch.setattr(worker, "start", start)
    response = client.post(f"/api/sessions/{session}/analysis/{kind}", json={
        "track_id": 11, "goal": "qualifying", "start_soc": 35,
        "minimum_soc": 20, "minimum_finish_soc": 30, "minimum_start_line_soc": 70})
    assert response.status_code == 202
    assert received[0]["start_soc"] == received[0]["minimum_start_line_soc"] == 100
    assert received[0]["minimum_soc" if kind == "workspace" else "minimum_finish_soc"] == 0


def test_old_links_preserve_context_and_two_workspace_navigation_is_served():
    import app as app_module
    client = app_module.app.test_client()
    for old, target in (("/analysis/race", "goal=race"), ("/analysis/qualifying", "goal=qualifying"),
                        ("/operation-library", "panel=reference"), ("/ers-strategy", "track_id=11")):
        response = client.get(old+"?track_id=11&session=existing")
        assert response.status_code == 302
        assert response.location.startswith("/strategy?") and target in response.location
        assert "session=existing" in response.location
    html = client.get("/strategy").get_data(as_text=True)
    assert 'data-goal="race"' in html and 'data-goal="compare"' in html and 'data-goal="qualifying"' in html
    assert 'Main workspaces' in html and '/session-analysis' in html
