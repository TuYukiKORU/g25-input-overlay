"""Practice suggestions must represent real gaps and improve as evidence arrives."""
from copy import deepcopy
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from strategy_learning import summarize_learning_evidence, suggest_ers_experiments
from strategy_model import build_strategy_model
from telemetry_quality import select_strategy_laps
from test_strategy_analysis import strategy_lap, model
from test_strategy_workspace import workspace_api


def observation(lap_id, action="none", soc=60, delta=-1, speed=220, recorded=True):
    return {"lap_id": lap_id, "action": action, "start_soc": soc, "soc_delta": delta,
            "entry_speed": speed, "deployment_recorded": recorded}


def section(number, observations, **changes):
    return {"number": number, "kind": "flat_out", "start_distance": number * 300,
            "end_distance": number * 300 + 250, "average_throttle": 1,
            "average_brake": 0, "peak_slip": .02,
            "learning_evidence": summarize_learning_evidence(observations), **changes}


def test_missing_activation_is_not_a_control_and_one_lap_is_one_observation():
    valid = observation("one")
    evidence = summarize_learning_evidence([valid, valid, observation("unknown", recorded=False)])
    assert evidence["actions"]["none"]["count"] == 1
    assert evidence["unknown_activation_laps"] == 1
    value = {"analyzable": True, "sections": [section(1, [observation("bad", recorded=False)])]}
    assert suggest_ers_experiments(value)["targets"] == []


def test_ranks_missing_controls_and_mode_before_repeated_comparisons():
    off = [observation(f"off{i}") for i in range(3)]
    on = [observation(f"on{i}", "boost", delta=-3) for i in range(3)]
    value = {"analyzable": True, "sections": [section(1, off + on[:1]), section(2, off),
                                               section(3, on), section(4, off + on)]}
    before = deepcopy(value)
    plan = suggest_ers_experiments(value)
    assert [row["section_number"] for row in plan["targets"]] == [2, 3, 1]
    assert plan["targets"][0]["action"] == "boost"
    assert plan["targets"][1]["action"] == "none"
    assert plan["targets"][1]["baseline_laps"] == 0
    assert plan["targets"][2]["matched_entry_laps"] == 1
    assert value == before
    # Collecting the missing repetitions retires that section from the map.
    value["sections"] = [section(1, off + on)]
    assert suggest_ers_experiments(value)["targets"] == []


def test_charge_and_speed_mismatch_keeps_a_well_sampled_section_as_a_target():
    off = [observation(f"off{i}", soc=90) for i in range(3)]
    on = [observation(f"on{i}", "boost", soc=30) for i in range(3)]
    plan = suggest_ers_experiments({"analyzable": True, "sections": [section(1, off + on)]})
    target = plan["targets"][0]
    assert target["reason"] == "unmatched_entry"
    assert target["suggested_entry_soc"] == 90
    assert target["matched_entry_laps"] == 0


def test_mode_isolation_and_braking_slip_and_short_section_exclusions():
    rows = [observation("boost", "boost")]
    value = {"analyzable": True, "sections": [section(1, rows),
        section(2, rows, kind="braking"), section(3, rows, peak_slip=.4),
        section(4, rows, end_distance=1250)]}
    plan = suggest_ers_experiments(value, "overtake")
    assert len(plan["targets"]) == 1
    assert plan["targets"][0]["reason"] == "missing_pair"
    assert plan["targets"][0]["action"] == "none"
    assert plan["targets"][0]["deployment_laps"] == 0
    assert plan["targets"][0]["soc_delta_mad"] is None


def test_practice_keeps_slow_laps_and_excludes_known_race_length_mismatches():
    reference = strategy_lap(1)
    slow = strategy_lap(2)
    slow["lapTimeMs"] *= 1.3
    other_length = strategy_lap(3)
    other_length["totalLaps"] = 60
    entries = [("s/one", reference), ("s/slow", slow), ("other/long", other_length)]
    selected, info = select_strategy_laps(entries, "s", "s/one", max_laps=1, learning=True)
    assert {i for i, _ in selected} == {"s/one", "s/slow"}
    assert info["excluded"]["different_totalLaps"] == 1
    assert info["excluded"]["outside_pace_window"] == 0
    value = build_strategy_model(entries[:1], "s", "s/one", learning=True)
    assert value["analyzable"]
    assert suggest_ers_experiments(value)["targets"]


def test_missing_flags_in_saved_laps_do_not_create_fake_baselines():
    entries = []
    for n in (1, 2):
        lap = strategy_lap(n)
        for sample in lap["samples"]:
            sample.pop("boost_active")
        entries.append((f"s/{n}", lap))
    value = build_strategy_model(entries, "s", "s/1", learning=True)
    assert value["analyzable"]
    assert not suggest_ers_experiments(value)["targets"]


def test_practice_job_and_context_use_one_recording_and_cache_the_map(workspace_api):
    client, storage, worker, session = workspace_api
    selected = storage.list_laps()[0]["id"]
    body = {"track_id": 11, "selected_lap_id": selected, "goal": "practice", "deployment_mode": "boost"}
    base = f"/api/sessions/{session}/analysis/workspace"
    response = client.post(base, json=body)
    assert response.status_code == 202
    params = {"track_id": 11, "analysis_id": response.get_json()["analysis_id"]}
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = client.get(base + "/status", query_string=params).get_json()
        if status["state"] in ("completed", "failed"):
            break
        time.sleep(.02)
    assert status["state"] == "completed", status
    result = client.get(base + "/result", query_string=params).get_json()
    assert result["goal"] == "practice" and result["plan"]["targets"]
    assert "trajectory" not in result["plan"]  # Suggestions do not invent battery forecasts.
    assert client.post(base, json=body).get_json()["cached"]
    for lap in storage.list_laps()[1:]:
        (storage.root / lap["id"]).unlink()
    storage._laps_cache = None
    context = client.get(f"/api/sessions/{session}/strategy-context", query_string=body).get_json()
    assert context["readiness"]["ready"] and context["comparable_lap_count"] == 1
