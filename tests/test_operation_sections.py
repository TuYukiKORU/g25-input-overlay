import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from operation_sections import analyze_operation_sections, build_operation_library


def synthetic_lap():
    samples = []
    for distance in range(0, 1001, 5):
        if distance < 200:
            throttle, brake, speed = 1.0, 0.0, 250
        elif distance < 350:
            throttle, brake, speed = 0.0, .8, 250 - (distance - 200) * .8
        elif distance < 500:
            throttle, brake, speed = 0.0, 0.0, 130 - (distance - 350) * .1
        elif distance < 700:
            throttle, brake, speed = .65, 0.0, 115 + (distance - 500) * .45
        else:
            throttle, brake, speed = 1.0, 0.0, 205 + (distance - 700) * .15
        samples.append({
            "lap_distance": distance, "lap_time_ms": distance * 20,
            "position": {"x": distance, "z": distance % 200},
            "speed": speed, "throttle": throttle, "brake": brake,
        })
    return {"lapNumber": 3, "lapTimeMs": 20000, "samples": samples}


def test_sections_follow_driver_inputs_in_order():
    result = analyze_operation_sections(synthetic_lap(), smoothing_m=0, min_section_m=15)
    assert result["analyzable"] is True
    kinds = [section["kind"] for section in result["sections"]]
    assert kinds == ["flat_out", "braking", "lift", "acceleration", "flat_out"]
    assert result["sections"][1]["entry_speed"] > result["sections"][1]["exit_speed"]
    assert result["sections"][3]["exit_speed"] > result["sections"][3]["entry_speed"]


def test_short_pedal_jitter_is_merged_into_surrounding_section():
    lap = synthetic_lap()
    lap["samples"][20]["throttle"] = 0
    result = analyze_operation_sections(lap, smoothing_m=0, min_section_m=20)
    early = [section for section in result["sections"] if section["start_distance"] < 150]
    assert len(early) == 1
    assert early[0]["kind"] == "flat_out"


def test_missing_inputs_return_reason():
    result = analyze_operation_sections({"samples": [{"lap_distance": n * 5, "speed": 100}
                                                       for n in range(200)]})
    assert result["analyzable"] is False
    assert "input" in result["reason"]


def test_library_uses_fast_valid_non_pit_laps_and_reports_consensus():
    laps = []
    for number, lap_time in enumerate((20000, 20200, 20400, 23000), 1):
        lap = synthetic_lap()
        lap.update({"lapNumber": number, "lapTimeMs": lap_time, "trackId": 7,
                    "validLap": True, "pitLaneUsed": False})
        laps.append((f"session/lap_{number}.json", lap))
    laps[2][1]["samples"][45]["brake"] = 0
    laps[3][1]["pitLaneUsed"] = True
    result = build_operation_library(laps, pace_window_percent=3, smoothing_m=0)
    assert result["analyzable"] is True
    assert result["compared_lap_count"] == 3
    assert result["sample_quality"] == "medium"
    assert result["source_laps"][-1]["gap_percent"] == 2.0
    assert result["overall_confidence"] > .95
    assert [section["kind"] for section in result["sections"]] == [
        "flat_out", "braking", "lift", "acceleration", "flat_out"]


def test_library_requires_two_competitive_laps():
    lap = synthetic_lap()
    lap.update({"lapTimeMs": 20000, "validLap": True, "trackId": 7})
    result = build_operation_library([("session/lap.json", lap)])
    assert result["analyzable"] is False
    assert "2周" in result["reason"]
