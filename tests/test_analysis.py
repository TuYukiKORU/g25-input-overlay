import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from lap_analyzer import aggregate_pace_zones, analyze_lap, compare_laps, detect_events
from comparison_context import comparison_context
from lap_analyzer import _loss_reasons

def sample(distance, time_ms, slip=.0):
    return {"lap_distance": distance, "lap_time_ms": time_ms, "speed": 100, "throttle": .8, "brake": 0,
            "wheel_slip_ratio": {"rear_left": slip, "rear_right": slip, "front_left": 0, "front_right": 0}, "wheel_speed": {}}

def test_interpolation_and_segment_delta():
    ref={"samples":[sample(0,0),sample(10,1000),sample(20,2000)]}
    cur={"samples":[sample(0,0),sample(10,1100),sample(20,2300)]}
    result=compare_laps(cur,ref,10)
    assert [x["delta_ms"] for x in result] == [0,100,300]
    assert result[-1]["loss_ms"] == 200


def test_missing_conditions_are_not_treated_as_a_match():
    unknown = comparison_context({}, {})
    assert unknown["unknown_fields"] == 5
    assert len(unknown["notes"]) == 5
    known = {"tyreCompound": "Soft", "setupId": "abc", "fuelInTankKgAtStart": 10,
             "tyreWearAtStart": {"front_left": 5}, "samples": [{"ers_percent": 80}]}
    assert comparison_context(known, known)["score"] == 0
    changed = dict(known, fuelInTankKgAtStart=30, tyreCompound="Hard")
    assert len(comparison_context(known, changed)["notes"]) == 2
    notes = comparison_context(dict(known, validLap=False, pitLaneUsed=True), known)["notes"]
    assert "Selected lap: invalid" in notes
    assert "Selected lap: pit lane used" in notes


def test_gap_does_not_become_a_time_loss_or_bridged_delta():
    ref = {"samples": [sample(d, d * 10) for d in range(0, 410, 10)]}
    cur = {"samples": [sample(d, d * 10 + (1000 if d >= 200 else 0))
                       for d in range(0, 410, 10) if d <= 50 or d >= 200]}
    result = analyze_lap(cur, ref)
    assert result["recording_gaps"] == [{"start_distance": 50, "end_distance": 200}]
    assert not result["losses"]
    assert next(p for p in result["comparison"] if p["distance"] == 200)["loss_ms"] == 0


def test_braking_onset_measures_position_not_average_pressure():
    def braking(onset, pressure):
        rows = [sample(d, d * 10) for d in range(0, 100, 5)]
        for row in rows:
            row["brake"] = pressure if row["lap_distance"] >= onset else 0
        return {"samples": rows}
    reasons = _loss_reasons(braking(20, .8), braking(40, .8), [], 0, 100)
    early = next(r for r in reasons if r["type"] == "EARLY_BRAKING")
    assert early["distance_difference_m"] == 20
    reasons = _loss_reasons(braking(40, 1), braking(40, .3), [], 0, 100)
    assert not any(r["type"] == "EARLY_BRAKING" for r in reasons)


def test_braking_already_active_at_start_is_not_an_onset():
    rows = [dict(sample(d, d * 10), brake=.8) for d in range(0, 100, 5)]
    reasons = _loss_reasons({"samples": rows}, {"samples": rows}, [], 0, 100)
    assert not any(r["type"] == "EARLY_BRAKING" for r in reasons)

def test_sustained_spin_detected_but_single_frame_ignored():
    sustained=[sample(0,0),sample(5,50,.2),sample(10,160,.3),sample(15,210,0)]
    assert detect_events(sustained)[0]["type"] == "wheel_spin"
    assert detect_events([sample(0,0),sample(5,50,.3),sample(10,90,0)]) == []

def test_lap_invalidation_transition_is_located_once():
    samples=[sample(0,0),sample(5,50),sample(10,100)]
    samples[1]["lap_invalid"] = True; samples[2]["lap_invalid"] = True
    invalid=[e for e in detect_events(samples) if e["type"] == "lap_invalidated"]
    assert len(invalid) == 1
    assert invalid[0]["start_distance"] == 5

def test_active_aero_intervals_are_detected_separately():
    samples=[sample(distance,distance * 10) for distance in range(0, 55, 5)]
    for row in samples:
        row["active_aero"] = 10 <= row["lap_distance"] <= 20 or 35 <= row["lap_distance"] <= 45
    aero=[e for e in detect_events(samples) if e["type"] == "active_aero"]
    assert [(e["start_distance"], e["end_distance"]) for e in aero] == [(10,20),(35,45)]

def test_f1_25_analysis_reports_drs_instead_of_active_aero():
    samples=[sample(distance,distance * 10) for distance in range(0, 30, 5)]
    for row in samples:
        row["drs"] = 10 <= row["lap_distance"] <= 20
        row["active_aero"] = row["drs"]  # Compatibility with previously saved F1 25 laps.
    events=analyze_lap({"packetFormat":2025,"samples":samples})["events"]
    assert [event["type"] for event in events] == ["drs"]

def test_pit_lane_interval_is_detected():
    samples=[sample(distance,distance * 10) for distance in range(0, 35, 5)]
    for row in samples: row["pit_status"] = 1 if 10 <= row["lap_distance"] <= 20 else 0
    pit=[e for e in detect_events(samples) if e["type"] == "pit_lane"]
    assert len(pit) == 1
    assert (pit[0]["start_distance"], pit[0]["end_distance"]) == (10,20)
    assert pit[0]["duration_ms"] == 100

def test_gradual_losses_are_aggregated_into_a_readable_zone():
    ref={"samples":[sample(distance,distance * 10) for distance in range(0, 210, 10)]}
    cur={"samples":[sample(distance,distance * 10 + distance) for distance in range(0, 210, 10)]}
    result=analyze_lap(cur,ref)
    assert result["losses"]
    assert result["losses"][0]["start_distance"] == 0
    assert result["losses"][0]["end_distance"] >= 100
    assert result["losses"][0]["time_loss_ms"] >= 50

def test_pace_zones_report_which_lap_is_faster_in_track_order():
    comparison = [
        {"distance": 0, "loss_ms": 60},
        {"distance": 100, "loss_ms": 70},
        {"distance": 200, "loss_ms": -80},
    ]
    zones = aggregate_pace_zones(comparison)
    assert [zone["faster"] for zone in zones] == ["comparison", "selected"]
    assert zones[0]["start_distance"] == 0
    assert zones[0]["end_distance"] == 200
