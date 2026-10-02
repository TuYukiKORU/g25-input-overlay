"""Distance-based lap comparison and rule-based driving event detection."""
from bisect import bisect_left
from analysis_config import ANALYSIS_CONFIG
from comparison_context import comparison_context, recording_gaps


def _interp(samples, distance, field="lap_time_ms"):
    points = [(float(s["lap_distance"]), float(s[field])) for s in samples
              if s.get("lap_distance") is not None and s.get(field) is not None]
    points.sort()
    if not points or distance < points[0][0] or distance > points[-1][0]:
        return None
    xs = [p[0] for p in points]
    i = bisect_left(xs, distance)
    if i == 0 or points[i][0] == distance:
        return points[i][1]
    x0, y0 = points[i - 1]; x1, y1 = points[i]
    if x1 - x0 > ANALYSIS_CONFIG["maximum_comparison_gap_m"]:
        return None
    return y0 if x1 == x0 else y0 + (y1 - y0) * (distance - x0) / (x1 - x0)


def compare_laps(current, reference, step_m=None):
    """Interpolate lap times by distance and return cumulative delta and segment loss."""
    step = float(step_m or ANALYSIS_CONFIG["comparison_step_m"])
    a, b = current.get("samples", []), reference.get("samples", [])
    if not a or not b:
        return []
    end = min(max(float(s.get("lap_distance", 0)) for s in a),
              max(float(s.get("lap_distance", 0)) for s in b))
    result, previous = [], None
    distance = 0.0
    while distance <= end:
        ct, rt = _interp(a, distance), _interp(b, distance)
        if ct is not None and rt is not None:
            delta = ct - rt
            result.append({"distance": distance, "delta_ms": round(delta, 2),
                           "loss_ms": round(delta - previous, 2) if previous is not None else 0.0})
            previous = delta
        else:
            previous = None
        distance += step
    return result


def _severity(peak, threshold):
    return min(3, max(0, int(peak / max(threshold, .001))))


def detect_events(samples, aero_event_type="active_aero"):
    """Detect sustained wheel spin and lock-up; isolated threshold crossings are ignored."""
    events = []
    for kind, cfg_name in (("wheel_spin", "wheel_spin"), ("tyre_lock", "lockup")):
        cfg = ANALYSIS_CONFIG[cfg_name]
        if not cfg["enabled"]:
            continue
        active = None
        for sample in samples + [None]:
            match, affected, peak = False, [], 0.0
            if sample:
                slip = sample.get("wheel_slip_ratio") or {}
                wheels = ("rear_left", "rear_right") if kind == "wheel_spin" else tuple(slip)
                if kind == "wheel_spin":
                    affected = [w for w in wheels if abs(float(slip.get(w) or 0)) > cfg["slip_threshold"]]
                    peak = max([abs(float(slip.get(w) or 0)) for w in wheels] or [0])
                    match = float(sample.get("throttle") or 0) > cfg["min_throttle"] and float(sample.get("speed") or 0) > cfg["min_speed_kph"] and bool(affected)
                else:
                    speeds = sample.get("wheel_speed") or {}
                    body = float(sample.get("speed") or 0) / 3.6
                    affected = [w for w in wheels if (body and float(speeds.get(w) or body) / body < cfg["speed_ratio"]) or float(slip.get(w) or 0) < cfg["slip_threshold"]]
                    peak = max([abs(float(slip.get(w) or 0)) for w in affected] or [0])
                    match = float(sample.get("brake") or 0) > cfg["min_brake"] and float(sample.get("speed") or 0) > cfg["min_speed_kph"] and bool(affected)
            if match and active is None:
                active = {"first": sample, "last": sample, "peak": peak, "wheels": set(affected)}
            elif match:
                active["last"] = sample; active["peak"] = max(active["peak"], peak); active["wheels"].update(affected)
            elif active:
                duration = int(active["last"].get("lap_time_ms", 0) - active["first"].get("lap_time_ms", 0))
                if duration >= cfg["min_duration_ms"]:
                    events.append({"type": kind, "start_distance": active["first"].get("lap_distance"), "end_distance": active["last"].get("lap_distance"), "start_time_ms": active["first"].get("lap_time_ms"), "duration_ms": duration, "peak_slip": round(active["peak"], 3), "affected_wheels": sorted(active["wheels"]), "severity": _severity(active["peak"], cfg.get("slip_threshold", .15))})
                active = None
    previous_invalid = False
    for sample in samples:
        invalid = bool(sample.get("lap_invalid", False))
        if invalid and not previous_invalid:
            events.append({"type": "lap_invalidated", "start_distance": sample.get("lap_distance"),
                           "end_distance": sample.get("lap_distance"), "start_time_ms": sample.get("lap_time_ms"),
                           "duration_ms": 0, "peak_slip": 0, "affected_wheels": [], "severity": 3})
        previous_invalid = invalid
    active = None
    for sample in samples + [None]:
        enabled = bool(sample and sample.get("active_aero" if aero_event_type == "active_aero" else "drs"))
        if enabled and active is None:
            active = {"first": sample, "last": sample}
        elif enabled:
            active["last"] = sample
        elif active:
            duration = int((active["last"].get("lap_time_ms") or 0) - (active["first"].get("lap_time_ms") or 0))
            events.append({"type": aero_event_type, "start_distance": active["first"].get("lap_distance"),
                           "end_distance": active["last"].get("lap_distance"), "start_time_ms": active["first"].get("lap_time_ms"),
                           "duration_ms": duration, "peak_slip": 0, "affected_wheels": [], "severity": 0})
            active = None
    active = None
    for sample in samples + [None]:
        in_pit = bool(sample and int(sample.get("pit_status") or 0) > 0)
        if in_pit and active is None:
            active = {"first": sample, "last": sample, "statuses": {int(sample.get("pit_status") or 0)}}
        elif in_pit:
            active["last"] = sample; active["statuses"].add(int(sample.get("pit_status") or 0))
        elif active:
            duration = int((active["last"].get("lap_time_ms") or 0) - (active["first"].get("lap_time_ms") or 0))
            events.append({"type": "pit_lane", "start_distance": active["first"].get("lap_distance"),
                           "end_distance": active["last"].get("lap_distance"), "start_time_ms": active["first"].get("lap_time_ms"),
                           "duration_ms": duration, "pit_statuses": sorted(active["statuses"]),
                           "peak_slip": 0, "affected_wheels": [], "severity": 0})
            active = None
    return events


def _onset(samples, field, start, end):
    rows = sorted(samples, key=lambda row: row.get("lap_distance", 0))
    for before, after in zip(rows, rows[1:]):
        a, b = before.get(field), after.get(field)
        x, y = before.get("lap_distance"), after.get("lap_distance")
        if a is None or b is None or x is None or y is None:
            continue
        if start <= y <= end and 0 < y - x <= ANALYSIS_CONFIG["maximum_comparison_gap_m"] and a < .2 <= b:
            return x + (.2 - a) / (b - a) * (y - x)
    return None


def _loss_reasons(lap, reference, events, start, end):
    related = [event for event in events
               if event["type"] not in ("active_aero", "drs", "pit_lane")
               and event["start_distance"] <= end and event["end_distance"] >= start]
    reasons = [{"type": related[0]["type"].upper(), "confidence": .9}] if related else []
    current = [sample for sample in lap.get("samples", [])
               if start <= float(sample.get("lap_distance", -1)) <= end]
    compared = [sample for sample in reference.get("samples", [])
                if start <= float(sample.get("lap_distance", -1)) <= end]
    for field, kind, sign in (("brake", "EARLY_BRAKING", -1), ("throttle", "LATE_THROTTLE", 1)):
        a = _onset(lap.get("samples", []), field, start, end)
        b = _onset(reference.get("samples", []), field, start, end)
        if a is not None and b is not None and (a - b) * sign >= 5:
            reasons.append({"type": kind, "confidence": .65, "distance_difference_m": round(abs(a - b), 1)})
    if current and compared:
        speeds = [row["speed"] for row in current if row.get("speed") is not None]
        other = [row["speed"] for row in compared if row.get("speed") is not None]
        if speeds and other and min(speeds) + 8 < min(other):
            reasons.append({"type": "LOW_MINIMUM_SPEED", "confidence": .7})
    if not reasons:
        reasons = [{"type": "LARGE_TIME_LOSS", "confidence": .5}]
    return sorted(reasons, key=lambda reason: reason["confidence"], reverse=True)


def aggregate_loss_zones(comparison, lap, reference, events):
    """Aggregate gradual 10 m losses into readable braking/corner-sized zones."""
    zone_m = float(ANALYSIS_CONFIG["loss_zone_m"])
    minimum = float(ANALYSIS_CONFIG["loss_zone_min_ms"])
    buckets = {}
    for point in comparison:
        index = int(float(point["distance"]) // zone_m)
        buckets[index] = buckets.get(index, 0.0) + float(point.get("loss_ms") or 0)
    qualifying = sorted(index for index, loss in buckets.items() if loss >= minimum)
    groups = []
    for index in qualifying:
        if groups and index == groups[-1][-1] + 1:
            groups[-1].append(index)
        else:
            groups.append([index])
    losses = []
    gaps = recording_gaps(lap, ANALYSIS_CONFIG["maximum_comparison_gap_m"]) + recording_gaps(reference, ANALYSIS_CONFIG["maximum_comparison_gap_m"])
    for group in groups:
        start = group[0] * zone_m
        end = (group[-1] + 1) * zone_m
        if any(gap["start_distance"] < end and gap["end_distance"] > start for gap in gaps):
            continue
        loss_ms = sum(max(0.0, buckets[index]) for index in group)
        reasons = _loss_reasons(lap, reference, events, start, end)
        losses.append({
            "start_distance": start, "end_distance": end,
            "time_loss_ms": round(loss_ms, 1),
            "primary_reason": reasons[0]["type"], "reasons": reasons,
            "details": {"zone_size_m": zone_m},
        })
    losses.sort(key=lambda loss: loss["time_loss_ms"], reverse=True)
    return losses[:int(ANALYSIS_CONFIG["max_loss_candidates"])]


def aggregate_pace_zones(comparison):
    """Return meaningful signed pace changes in track order for both laps."""
    zone_m = float(ANALYSIS_CONFIG["loss_zone_m"])
    minimum = float(ANALYSIS_CONFIG["loss_zone_min_ms"])
    buckets = {}
    for point in comparison:
        index = int(float(point["distance"]) // zone_m)
        buckets[index] = buckets.get(index, 0.0) + float(point.get("loss_ms") or 0)
    qualifying = [(index, loss) for index, loss in sorted(buckets.items()) if abs(loss) >= minimum]
    groups = []
    for index, loss in qualifying:
        direction = 1 if loss > 0 else -1
        if groups and index == groups[-1]["last"] + 1 and direction == groups[-1]["direction"]:
            groups[-1]["last"] = index
            groups[-1]["difference"] += loss
        else:
            groups.append({"first": index, "last": index, "direction": direction, "difference": loss})
    zones = [{
        "start_distance": group["first"] * zone_m,
        "end_distance": (group["last"] + 1) * zone_m,
        "faster": "comparison" if group["difference"] > 0 else "selected",
        "time_difference_ms": round(abs(group["difference"]), 1),
    } for group in groups]
    return zones[:int(ANALYSIS_CONFIG["max_pace_zones"])]


def analyze_lap(lap, reference=None):
    season_pack = (lap.get("packetFormat") == 2026 or lap.get("gameVersion") == "F1 26"
                   or lap.get("udpMode") == "2026 Season Pack")
    events = detect_events(lap.get("samples", []), "active_aero" if season_pack else "drs")
    comparison = compare_laps(lap, reference) if reference else []
    losses = aggregate_loss_zones(comparison, lap, reference, events) if reference else []
    pace_zones = aggregate_pace_zones(comparison) if reference else []
    gaps = recording_gaps(lap, ANALYSIS_CONFIG["maximum_comparison_gap_m"])
    if reference:
        gaps += recording_gaps(reference, ANALYSIS_CONFIG["maximum_comparison_gap_m"])
    pace_zones = [zone for zone in pace_zones if not any(g["start_distance"] < zone["end_distance"] and g["end_distance"] > zone["start_distance"] for g in gaps)]
    return {"events": events, "comparison": comparison, "losses": losses, "pace_zones": pace_zones,
            "recording_gaps": gaps, "comparison_context": comparison_context(lap, reference) if reference else None}
