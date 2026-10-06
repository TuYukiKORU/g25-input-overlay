import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from qualifying_optimizer import analyze_qualifying
from race_optimizer import analyze_race
from storage import LapStorage
from strategy_model import build_strategy_model
from strategy_scenarios import compare_strategy_scenarios, optimize_multi_lap_strategy


def strategy_lap(number, active=False):
    samples, elapsed, soc = [], 0.0, 90.0
    for distance in range(0, 2001, 25):
        braking = 650 <= distance < 850 or 1450 <= distance < 1600
        overtake = active and 1000 <= distance < 1350
        boost = active and (250 <= distance < 550 or overtake)
        speed = 135 if braking else 220 + min(60, distance / 50)
        elapsed += 370 if (boost and not braking) else 400 if not braking else 620
        soc += .04 if braking else -.10 if overtake else -.06 if boost else -.01
        samples.append({
            "lap_distance": distance, "lap_time_ms": elapsed,
            "position": {"x": distance / 10, "z": 80 * math.sin(distance / 300)},
            "speed": speed, "throttle": .15 if braking else 1.0, "brake": .7 if braking else 0,
            "longitudinal_g": -1.5 if braking else .5, "ers_soc": soc,
            "ers_percent": round(soc), "ers_mguk_power": 115000,
            "boost_active": int(boost), "overtake_active": int(overtake),
            "active_aero": not braking, "fuel_in_tank_kg": 40 - distance / 10000,
            "wheel_slip_ratio": {"rear_left": .06 if boost else .02, "rear_right": .05 if boost else .02},
            "tyre_wear": {"rear_left": 5 + number / 10, "rear_right": 5 + number / 10},
        })
    return {"packetFormat": 2026, "gameYear": 26, "trackId": 11, "lapNumber": number,
            "lapTimeMs": round(elapsed), "validLap": True, "pitLaneUsed": False,
            "createdAt": f"2026-01-01T00:00:{number:02d}Z", "totalLaps": 20,
            "tyreCompound": "Soft (C3)", "samples": samples}


def model():
    entries = []
    for number in range(1, 7):
        session = "s1" if number <= 3 else "s2"
        entries.append((f"{session}/track/laps/lap_{number}.json",
                        strategy_lap(number, active=number % 2 == 0)))
    return build_strategy_model(entries, selected_session_id="s1",
                                selected_lap_id="s1/track/laps/lap_3.json", pace_window_percent=15)


def test_shared_model_and_qualifying_dp_produce_soc_allocation():
    value = model()
    assert value["analyzable"] is True
    assert value["sections"]
    assert value["personal"]["status"] == "available"
    assert value["ideal_lap"]["analyzable"] is True
    assert value["ideal_lap"]["predicted_lap_time_ms"] <= value["ideal_lap"]["session_best_lap_time_ms"]
    assert value["ideal_lap"]["source_lap_count"] == 3
    result = analyze_qualifying(value, start_soc=None, minimum_finish_soc=5)
    assert result["general"]["analyzable"] is True
    assert result["general"]["predicted_finish_soc"] >= 0
    assert result["general"]["target_finish_soc"] == 0
    assert result["deployment_mode"] == "overtake"
    assert result["general"]["battery_before_runup_soc"] == 100
    assert result["general"]["start_line_soc"] == 100
    assert all(row["action"] != "boost" for row in result["general"]["allocations"])
    assert len(result["general"]["allocations"]) == len(value["sections"])
    assert result["personal"]["analyzable"] is True


def test_shared_section_action_model_exposes_uniform_lift_and_deployment_predictions():
    value = model()
    assert value["schema_version"] == 5
    assert value["model_version"] == "condition-matched-section-actions-v5"
    assert value["action_catalog"]["lift_20"]["can_fund_follow_up"] == ["boost", "overtake"]
    required_actions = {"none", "lift_10", "lift_20", "lift_30", "boost", "overtake"}
    required_metrics = {
        "predicted_time_ms", "gain_ms", "soc_delta", "soc_cost", "soc_recovery",
        "exit_speed", "exit_speed_delta", "clipping_probability",
        "super_clipping_probability", "peak_slip", "tyre_delta", "tyre_cost", "fuel_delta_kg",
        "fuel_saving_kg", "samples", "evidence", "confidence",
    }
    for section in value["sections"]:
        assert set(section["actions"]) == required_actions
        assert all(required_metrics <= set(prediction) for prediction in section["actions"].values())
        assert section["actions"]["lift_30"]["soc_recovery"] >= section["actions"]["lift_10"]["soc_recovery"]
        assert section["actions"]["lift_30"]["predicted_time_ms"] >= section["actions"]["lift_10"]["predicted_time_ms"]


def test_qualifying_optimizer_supports_all_lift_and_deployment_actions():
    result = analyze_qualifying(model(), start_soc=90, minimum_finish_soc=5)
    assert all(row["action"] in {"none", "lift_10", "lift_20", "lift_30", "boost", "overtake"}
               for row in result["general"]["allocations"])
    assert all("soc_recovered" in row for row in result["general"]["allocations"])


def test_three_scenarios_share_start_and_finish_soc_without_borrowing_energy():
    comparison = compare_strategy_scenarios(model(), start_soc=90)
    assert comparison["analyzable"] is True
    assert comparison["is_optimized"] is True
    assert comparison["method"] == "same-finish-soc-section-dp-v2"
    assert [row["id"] for row in comparison["scenarios"]] == [
        "no_deployment", "deployment_only", "lift_and_deploy",
    ]
    assert all(row["start_soc"] == 90 for row in comparison["scenarios"])
    assert all(abs(row["predicted_finish_soc"] - comparison["common_finish_soc"]) <= .25
               for row in comparison["scenarios"])
    lift = comparison["scenarios"][2]
    assert all(row["action"] != "none" for row in lift["allocations"])


def test_single_lap_scenarios_never_mix_boost_and_overtake():
    for mode, forbidden in (("boost", "overtake"), ("overtake", "boost")):
        comparison = compare_strategy_scenarios(model(), start_soc=90,
                                                deployment_mode=mode)
        assert comparison["deployment_mode"] == mode
        for scenario in comparison["scenarios"]:
            assert all(row["action"] != forbidden for row in scenario["allocations"])


def test_low_start_soc_scenario_comparison_remains_renderable():
    for mode in ("boost", "overtake"):
        comparison = compare_strategy_scenarios(model(), start_soc=4.0,
                                                deployment_mode=mode)
        assert comparison["analyzable"] is True
        assert all(row["analyzable"] for row in comparison["scenarios"])
        assert all(row["predicted_finish_soc"] >= 0 for row in comparison["scenarios"])


def test_multi_lap_section_dp_exposes_receding_horizon_soc_trajectory():
    result = optimize_multi_lap_strategy(model(), horizon=4, remaining_laps=10,
                                         start_soc=70, minimum_finish_soc=5)
    assert result["analyzable"] is True
    assert result["horizon_laps"] == 4
    assert len(result["trajectory"]) == 4
    assert result["current_lap_recommendation"] == result["trajectory"][0]
    assert result["recalculate_next_lap"] is True
    assert result["soc_target_trajectory"] == [row["soc_end"] for row in result["trajectory"]]
    assert all(row["level"] in {"attack", "fast", "sustainable", "save"}
               for row in result["trajectory"])
    assert all(row["minimum_soc"] >= 5 for row in result["trajectory"])
    assert all(row["soc_trace"] for row in result["trajectory"])
    assert all(row["action"] != "overtake" or row["evidence"] == "observed"
               for row in result["allocations"])


def test_multi_lap_variants_use_only_the_selected_deployment_mode():
    for mode, forbidden in (("boost", "overtake"), ("overtake", "boost")):
        result = optimize_multi_lap_strategy(model(), horizon=3, remaining_laps=10,
                                             start_soc=70, deployment_mode=mode)
        assert result["deployment_mode"] == mode
        assert all(row["action"] != forbidden for row in result["allocations"])


def test_multi_lap_section_dp_uses_minimum_soc_when_finish_is_in_horizon():
    result = optimize_multi_lap_strategy(model(), horizon=5, remaining_laps=3,
                                         start_soc=70, minimum_finish_soc=5)
    assert result["analyzable"] is True
    assert result["horizon_laps"] == 3
    assert result["finishing_race"] is True
    assert result["minimum_soc_unreachable"] is True
    assert abs(result["predicted_finish_soc"] - result["minimum_reachable_soc"]) <= .5
    assert result["predicted_finish_soc"] >= result["requested_minimum_finish_soc"]


def test_race_mpc_returns_only_current_lap_as_adopted_recommendation():
    result = analyze_race(model(), horizon=5, current_soc=70, minimum_soc=5, remaining_laps=4)
    general = result["general"]
    assert general["analyzable"] is True
    assert len(general["trajectory"]) == 4
    assert general["current_lap_recommendation"] == general["trajectory"][0]
    assert all("kind" in row and "action" in row for row in general["current_lap_recommendation"]["allocations"])
    assert general["finishing_race"] is True


def test_strategy_artifact_path_is_scoped_and_atomic(tmp_path):
    store = LapStorage(tmp_path)
    store.start_session({"sessionUid": 1, "trackId": 11})
    session_id = store.session_dir.name
    store.save_strategy_artifact(session_id, 11, "qualifying", "abcdef0123456789", {"ok": True})
    assert store.load_strategy_artifact(session_id, 11, "qualifying", "abcdef0123456789") == {"ok": True}
    assert store.strategy_path(session_id, 11, "unknown", "abcdef0123456789") is None
    assert store.strategy_path(session_id, 11, "race", "../bad") is None
