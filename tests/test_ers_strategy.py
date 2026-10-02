import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from ers_strategy import analyze_ers_strategy


def ers_lap(number, variant):
    samples, elapsed, soc = [], 0, 70.0
    for distance in range(0, 1401, 25):
        boost = variant == "active" and distance < 400
        overtake = variant == "active" and 500 <= distance < 850
        clipping = variant == "active" and 950 <= distance < 1250
        increment = 500
        if boost: increment = 445
        if overtake: increment = 425
        if clipping: increment = 565
        elapsed += increment
        soc -= .16 if overtake else .10 if boost else .025
        samples.append({
            "lap_distance": distance, "lap_time_ms": elapsed,
            "speed": 210 + distance / 20, "throttle": 1.0, "brake": 0,
            "boost_active": int(boost or overtake), "overtake_active": int(overtake),
            "ers_mode": 1, "ers_mguk_power": 0 if clipping else 120000,
            "ers_soc": soc, "ers_percent": round(soc),
        })
    return {"packetFormat": 2026, "gameVersion": "F1 26", "trackId": 9,
            "lapNumber": number, "lapTimeMs": elapsed, "validLap": True,
            "pitLaneUsed": False, "samples": samples}


def test_strategy_compares_modes_and_detects_clipping():
    entries = [("s/lap_1.json", ers_lap(1, "normal")),
               ("s/lap_2.json", ers_lap(2, "normal")),
               ("s/lap_3.json", ers_lap(3, "active")),
               ("s/lap_4.json", ers_lap(4, "active"))]
    result = analyze_ers_strategy(entries, pace_window_percent=12, window_m=200, stride_m=50)
    assert result["analyzable"] is True
    assert result["compared_lap_count"] == 4
    assert result["mode_summary"]["boost"]["observations"] > 0
    assert result["mode_summary"]["overtake"]["observations"] > 0
    assert result["mode_summary"]["clipping"]["observations"] > 0
    assert result["mode_summary"]["boost"]["median_gain_vs_none_ms"] < 0
    assert result["mode_summary"]["clipping"]["median_gain_vs_none_ms"] > 0
    assert result["recommendations"]["boost"]
    assert result["recommendations"]["overtake"]
    assert result["mode_summary"]["boost"]["median_incremental_soc_cost"] > 0
    assert result["mode_summary"]["boost"]["median_value_ms_per_soc"] > 0
    plan = result["recommended_plan"]
    assert plan
    assert all(left["end_distance"] <= right["start_distance"]
               for left, right in zip(plan, plan[1:]))
    assert all("net_time_gain_ms" in row and "clipping_risk_penalty_ms" in row for row in plan)


def test_strategy_rejects_non_2026_laps():
    first, second = ers_lap(1, "normal"), ers_lap(2, "normal")
    first["packetFormat"] = second["packetFormat"] = 2025
    first["gameVersion"] = second["gameVersion"] = "F1 25"
    result = analyze_ers_strategy([("s/a.json", first), ("s/b.json", second)])
    assert result["analyzable"] is False
    assert "26 edition" in result["reason"]
