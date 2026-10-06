"""Independent energy/geometry checks and explicit comparison conditions."""
from collections import Counter
from math import hypot, isfinite

from comparison_context import conditions


def number(value):
    try:
        value = float(value)
        return value if isfinite(value) else None
    except (TypeError, ValueError):
        return None


def lap_edition(lap):
    if (lap.get("gameVersion") == "F1 26" or lap.get("gameYear") == 26
            or lap.get("packetFormat") == 2026 or lap.get("udpMode") == "2026 Season Pack"):
        return 2026
    if lap.get("gameVersion") == "F1 25" or lap.get("gameYear") == 25 or lap.get("packetFormat") == 2025:
        return 2025
    return None


def geometry_quality(samples):
    points = [(number((s.get("position") or {}).get("x")),
               number((s.get("position") or {}).get("z"))) for s in samples]
    points = [(x, z) for x, z in points if x is not None and z is not None]
    if len(points) < max(20, len(samples) * .8):
        return {"available": False, "reason": "Not enough recorded X/Z positions."}
    span = hypot(max(x for x, _ in points) - min(x for x, _ in points),
                 max(z for _, z in points) - min(z for _, z in points))
    if span < 10:
        return {"available": False, "reason": "Recorded positions do not form a moving track trace."}
    return {"available": True, "reason": None,
            "dimensions": "3D" if all(number((s.get("position") or {}).get("y")) is not None
                                        for s in samples) else "planar"}


def lap_quality(lap):
    samples = lap.get("samples") or []
    rows = []
    for sample in samples:
        values = [number(sample.get(k)) for k in ("lap_distance", "lap_time_ms", "speed", "throttle", "brake")]
        soc = number(sample.get("ers_soc"))
        if soc is None:
            soc = number(sample.get("ers_percent"))
        if all(v is not None for v in values) and soc is not None and 0 <= soc <= 100:
            rows.append((values[0], values[1]))
    distances = sorted({s for s, _ in rows})
    usable = (len(distances) >= 50 and distances[0] <= 100 and distances[-1] - distances[0] >= 500
              and all(b-a <= 100 for a, b in zip(distances, distances[1:])))
    covered = usable and len(rows) >= max(50, len(samples) * .8)
    monotonic = covered and all(b[1] >= a[1] for a, b in zip(sorted(rows), sorted(rows)[1:]))
    reason = None
    if not lap.get("validLap") or lap.get("pitLaneUsed") or any(s.get("pit_status") for s in samples):
        reason = "Choose a valid lap without pit-lane use."
    elif not number(lap.get("lapTimeMs")):
        reason = "Recorded lap time is missing."
    elif not monotonic:
        reason = "Insufficient valid distance, time, pedal, speed or battery samples."
    return {"edition": lap_edition(lap), "energy": {"available": reason is None, "reason": reason},
            "geometry": geometry_quality(samples), "energy_sample_count": len(rows),
            "track_length_m": distances[-1] if distances else None}


def compatible_conditions(reference, candidate, match_race_length=False):
    """Reject recorded mismatches; disclose missing fields rather than inventing them."""
    a, b = conditions(reference), conditions(candidate)
    unknown = []
    for key, tolerance in (("compound", None), ("setup", None), ("fuel", 3.0), ("wear", 5.0)):
        if a[key] in (None, "") or b[key] in (None, ""):
            unknown.append(key)
        elif (a[key] != b[key] if tolerance is None else abs(a[key] - b[key]) > tolerance):
            return False, f"different_{key}", unknown
    for key in ("weather", "sessionType", *(("totalLaps",) if match_race_length else ())):
        if reference.get(key) is None or candidate.get(key) is None:
            unknown.append(key)
        elif reference[key] != candidate[key]:
            return False, f"different_{key}", unknown
    return True, None, unknown


def select_strategy_laps(entries, selected_session_id=None, selected_lap_id=None,
                         pace_window_percent=8, max_laps=40, learning=False):
    reference = next((item for item in entries if item[0] == selected_lap_id), None)
    candidates = [item for item in entries if lap_edition(item[1]) == 2026 and lap_quality(item[1])["energy"]["available"]]
    if reference is None:
        session_candidates = [item for item in entries if str(item[0]).split("/", 1)[0] == selected_session_id
                              and number(item[1].get("lapTimeMs"))]
        reference = min(session_candidates or (candidates if not selected_session_id else []),
                        key=lambda item: item[1]["lapTimeMs"], default=None)
    if reference is None:
        return [], {"reason": "At least two valid 2026 edition laps with battery telemetry are required."}
    reference_id, lap = reference
    quality = lap_quality(lap)
    info = {"reference_lap_id": reference_id, "reference_quality": quality, "excluded": {}, "unknown_conditions": []}
    if quality["edition"] != 2026 or not quality["energy"]["available"]:
        info["reason"] = ("The selected lap is not a supported 2026 edition recording."
                          if quality["edition"] != 2026 else quality["energy"]["reason"])
        return [], info
    excluded, unknown, matched = Counter(), set(), []
    for item in entries:
        candidate = item[1]
        other = lap_quality(candidate)
        if str(candidate.get("trackId")) != str(lap.get("trackId")) or other["edition"] != quality["edition"]:
            excluded["different_track_or_edition"] += 1
            continue
        if not other["energy"]["available"]:
            excluded["unusable_energy"] += 1
            continue
        if abs(other["track_length_m"] - quality["track_length_m"]) > max(100, quality["track_length_m"] * .03):
            excluded["different_track_length"] += 1
            continue
        match, reason, missing = compatible_conditions(lap, candidate, match_race_length=learning)
        if not match:
            excluded[reason] += 1
            continue
        unknown.update(missing)
        matched.append(item)
    matched.sort(key=lambda item: item[1]["lapTimeMs"])
    cutoff = matched[0][1]["lapTimeMs"] * (1 + pace_window_percent / 100) if matched else 0
    fast = matched if learning else [item for item in matched if item[1]["lapTimeMs"] <= cutoff]
    excluded["outside_pace_window"] = len(matched) - len(fast)
    selected = fast if learning else fast[:max_laps]
    info.update(excluded=dict(excluded), unknown_conditions=sorted(unknown), comparable_lap_count=len(fast),
                learning=learning,
                reason=None if len(selected) >= (1 if learning else 2) else "At least two laps with compatible recorded conditions are required.")
    return selected, info


def prediction_is_usable(section, action):
    """Do not turn contradictory associations into energy-saving instructions."""
    baseline, prediction = section["actions"]["none"], section["actions"][action]
    values = [number(p.get(key)) for p in (baseline, prediction) for key in ("predicted_time_ms", "soc_delta")]
    if any(value is None for value in values) or values[0] <= 0 or values[2] <= 0:
        return False
    time_delta, soc_delta = values[2] - values[0], values[3] - values[1]
    if action.startswith("lift"):
        return time_delta >= 0 and soc_delta >= 0
    if action in ("boost", "overtake"):
        return time_delta <= 0 and soc_delta <= 0
    return True
