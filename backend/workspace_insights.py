"""Condition-aware summaries of recorded laps. No fitted physical tyre penalties."""
from statistics import median

from analysis_config import ANALYSIS_CONFIG
from comparison_context import conditions, number, recording_gaps
from lap_analyzer import _interp, _onset
from track_sections import analyze_track_sections


def clean(lap):
    duration = number(lap.get("lapTimeMs"))
    return bool(lap.get("validLap") and not lap.get("pitLaneUsed")
                and not any(s.get("pit_status") for s in lap.get("samples", []))
                and duration is not None and duration > 0)


def comparable(a, b, fuel_limit=3, ers_limit=10, wear_limit=3):
    x, y = conditions(a), conditions(b)
    if any(x[k] is None or y[k] is None for k in ("compound", "setup", "fuel", "ers", "wear")):
        return False
    return (x["compound"] == y["compound"] and x["setup"] == y["setup"]
            and abs(x["fuel"] - y["fuel"]) <= fuel_limit
            and abs(x["ers"] - y["ers"]) <= ers_limit
            and (wear_limit is None or abs(x["wear"] - y["wear"]) <= wear_limit))


def mean_wear(value):
    values = [number(v) for v in (value or {}).values()]
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def wear_estimate(entries, selected):
    """Fit only tightly matched pairs with meaningful wear variation."""
    pool = [(lap_id, lap) for lap_id, lap in entries if clean(lap)
            and comparable(selected, lap, fuel_limit=1, ers_limit=5, wear_limit=None)]
    slopes, used = [], set()
    for i, (a_id, a) in enumerate(pool):
        for b_id, b in pool[i + 1:]:
            if not comparable(a, b, fuel_limit=1, ers_limit=5, wear_limit=None):
                continue
            gap = conditions(b)["wear"] - conditions(a)["wear"]
            if abs(gap) < 2:
                continue
            slopes.append((b["lapTimeMs"] - a["lapTimeMs"]) / gap)
            used.update((a_id, b_id))
    slope = median(slopes) if len(used) >= 3 and len(slopes) >= 3 else None
    start, end = mean_wear(selected.get("tyreWearAtStart")), mean_wear(selected.get("tyreWearAtEnd"))
    loss = max(0, end - start) * slope if slope is not None and slope > 0 and start is not None and end is not None else None
    return {"estimated_loss_ms": round(loss, 2) if loss is not None else None,
            "ms_per_wear_percent": round(slope, 2) if slope is not None else None,
            "sample_count": len(used), "pair_count": len(slopes),
            "reason": "Insufficient evidence: need 3 clean laps and 3 matched pairs with ≥2% wear variation" if slope is None else
                      "No positive wear/pace relationship observed" if slope <= 0 else
                      "Selected lap has no complete start/end wear recording" if start is None or end is None else
                      "Observed association; weather, traffic and driving differences can still affect pace",
            "method": "Same compound/setup, starting fuel within 1 kg and ERS within 5%; median pair slope"}


def consistency(entries, selected, profile=None):
    eligible = [(lap_id, lap) for lap_id, lap in entries if clean(lap) and comparable(selected, lap)]
    definition = profile if profile and profile.get("corners") else analyze_track_sections(selected)
    corners = definition.get("corners", [])
    result = {"eligible_laps": len(eligible), "rows": [], "reason": None,
              "method": "Clean laps: same compound/setup, fuel ±3 kg, wear ±3%, starting ERS ±10%"}
    if len(eligible) < 3:
        result["reason"] = "Need at least 3 clean laps with known, similar conditions. Unknown conditions are excluded."
        return result
    if not corners:
        result["reason"] = "No corner definition available. Register turns in Map & Corners."
        return result
    for corner in corners:
        start, end = corner["start_distance"], corner["end_distance"]
        observations = []
        for lap_id, lap in eligible:
            if any(g["start_distance"] < end and g["end_distance"] > start
                   for g in recording_gaps(lap, ANALYSIS_CONFIG["maximum_comparison_gap_m"])):
                continue
            a, b = _interp(lap["samples"], start), _interp(lap["samples"], end)
            if a is None or b is None or b <= a:
                continue
            speeds = [number(s.get("speed")) for s in lap["samples"] if start <= (number(s.get("lap_distance")) or 0) <= end]
            speeds = [v for v in speeds if v is not None]
            observations.append({"id": lap_id, "lap_number": lap.get("lapNumber"), "time_ms": b - a,
                                 "brake_m": _onset(lap["samples"], "brake", max(0, start - 80), corner.get("apex_distance", end)),
                                 "throttle_m": _onset(lap["samples"], "throttle", corner.get("apex_distance", start), end + 40),
                                 "minimum_speed_kph": min(speeds) if speeds else None})
        if len(observations) < 3:
            continue
        typical = median(o["time_ms"] for o in observations)
        row = {"label": corner["label"], "start_distance": start, "end_distance": end,
               "lap_count": len(observations), "median_time_ms": round(typical, 1),
               "time_range_ms": round(max(o["time_ms"] for o in observations) - min(o["time_ms"] for o in observations), 1),
               "slower_than_median_count": sum(o["time_ms"] > typical + 50 for o in observations),
               "observations": observations}
        for key in ("brake_m", "throttle_m", "minimum_speed_kph"):
            values = [o[key] for o in observations if o[key] is not None]
            row[key + "_range"] = round(max(values) - min(values), 1) if len(values) >= 3 else None
            row[key + "_median"] = round(median(values), 1) if len(values) >= 3 else None
        result["rows"].append(row)
    result["rows"].sort(key=lambda row: row["time_range_ms"], reverse=True)
    if not result["rows"]:
        result["reason"] = "Not enough shared, uninterrupted corner samples."
    return result


def stints(entries):
    ordered = sorted(entries, key=lambda item: (item[1].get("createdAt") or "", item[1].get("lapNumber", 0), item[0]))
    groups, previous, after_pit = [], None, False
    for lap_id, lap in ordered:
        age = number(lap.get("tyreAgeLapsAtStart"))
        wear = mean_wear(lap.get("tyreWearAtStart"))
        compound = lap.get("tyreCompound")
        reasons = []
        if previous:
            if compound and previous["compound"] and compound != previous["compound"]:
                reasons.append("Compound changed")
            if age is not None and previous["age"] is not None and age < previous["age"]:
                reasons.append("Tyre age reset")
            if wear is not None and previous["wear"] is not None and wear < previous["wear"] - 2:
                reasons.append("Wear reset")
            if after_pit:
                reasons.append("Following pit lap; tyre change unconfirmed" if not reasons else "Following pit lap")
        if not groups or reasons:
            groups.append({"number": len(groups) + 1, "compound": compound, "reason": "; ".join(reasons) or "First recorded lap", "laps": []})
        samples = lap.get("samples") or []
        last = samples[-1] if samples else {}
        groups[-1]["laps"].append({"id": lap_id, "lap_number": lap.get("lapNumber"), "time_ms": number(lap.get("lapTimeMs")),
            "eligible": clean(lap), "valid": bool(lap.get("validLap")), "pit": bool(lap.get("pitLaneUsed") or any(s.get("pit_status") for s in samples)),
            "fuel_kg": conditions(lap)["fuel"], "wear_percent": wear, "ers_percent": conditions(lap)["ers"],
            "ers_end_percent": number(last.get("ers_percent")), "tyre_age": age})
        previous = {"age": age, "wear": wear, "compound": compound}
        after_pit = groups[-1]["laps"][-1]["pit"]
    return groups


def setup_changes(a, b):
    if not a or not b:
        return {"available": False, "reason": "Setup snapshot missing for one or both laps", "rows": []}
    rows = [{"field": key, "selected": a.get(key), "comparison": b.get(key)}
            for key in sorted((a.keys() | b.keys()) - {"setupId"}) if a.get(key) != b.get(key)]
    return {"available": True, "reason": "Identical recorded setups" if not rows else None, "rows": rows}
