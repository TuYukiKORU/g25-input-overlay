"""Empirical F1 26 ERS mode comparison and placement recommendations."""
from bisect import bisect_left
from collections import Counter
from statistics import median


MODE_META = {
    "boost": {"label": "Boost mode", "color": "#ffd84d"},
    "overtake": {"label": "Overtake mode", "color": "#35a7ff"},
    "none": {"label": "操作なし", "color": "#89959b"},
    "clipping": {"label": "操作なし＋クリッピング", "color": "#ff5f78"},
}


def _number(value, default=None):
    try:
        value = float(value)
        return value if value == value else default
    except (TypeError, ValueError):
        return default


def _is_f1_26(lap):
    return (lap.get("packetFormat") == 2026 or lap.get("gameYear") == 26
            or lap.get("gameVersion") == "F1 26")


def _rows(lap):
    result = []
    for sample in lap.get("samples", []):
        position = sample.get("position") or {}
        distance = _number(sample.get("lap_distance"))
        elapsed = _number(sample.get("lap_time_ms"))
        speed = _number(sample.get("speed"))
        if None in (distance, elapsed, speed):
            continue
        result.append({
            "s": distance, "t": elapsed, "speed": speed,
            "throttle": max(0.0, min(1.0, _number(sample.get("throttle"), 0.0))),
            "brake": max(0.0, min(1.0, _number(sample.get("brake"), 0.0))),
            "boost": bool(sample.get("boost_active")),
            "overtake": bool(sample.get("overtake_active")),
            "telemetry2": bool(sample.get("telemetry2_received")),
            "ers_mode": round(_number(sample.get("ers_mode"), 0)),
            "mguk_power": _number(sample.get("ers_mguk_power")),
            "battery": _number(sample.get("ers_soc"), _number(sample.get("ers_percent"))),
            "x": _number(position.get("x")), "z": _number(position.get("z")),
        })
    result.sort(key=lambda row: row["s"])
    return result


def _interpolate(rows, distance, key):
    distances = [row["s"] for row in rows]
    index = bisect_left(distances, distance)
    if index <= 0:
        return rows[0][key]
    if index >= len(rows):
        return rows[-1][key]
    before, after = rows[index - 1], rows[index]
    left, right = before[key], after[key]
    if left is None or right is None:
        return left if left is not None else right
    ratio = (distance - before["s"]) / max(after["s"] - before["s"], 1e-9)
    return left + (right - left) * ratio


def _clipping_threshold(rows):
    powers = [row["mguk_power"] for row in rows
              if row["mguk_power"] is not None and row["mguk_power"] > 0
              and row["throttle"] >= .95 and row["brake"] < .05]
    return max(20000.0, median(powers) * .20) if powers else None


def _sample_mode(row, threshold, legacy):
    if row["boost"] and row["overtake"]:
        return "overtake"
    if row["boost"]:
        return "boost"
    # Recordings made before Telemetry2 support still contain the F1 26
    # deploy mode. Mode 3 is the only reliable historical Overtake evidence;
    # historical Boost cannot be reconstructed and is deliberately not guessed.
    if legacy and row["ers_mode"] == 3:
        return "overtake"
    if (threshold is not None and row["throttle"] >= .95 and row["brake"] < .05
            and row["speed"] >= 180 and row["mguk_power"] is not None
            and row["mguk_power"] <= threshold):
        return "clipping"
    return "none"


def _window_mode(rows, start, end, threshold, legacy):
    local = [row for row in rows if start <= row["s"] <= end]
    if not local:
        return None, {}
    counts = Counter(_sample_mode(row, threshold, legacy) for row in local)
    total = len(local)
    if counts["overtake"] / total >= .20:
        mode = "overtake"
    elif counts["boost"] / total >= .20:
        mode = "boost"
    elif counts["clipping"] / total >= .30:
        mode = "clipping"
    else:
        mode = "none"
    return mode, {key: counts[key] for key in MODE_META}


def _median_or_none(values, digits=1):
    values = [value for value in values if value is not None]
    return round(median(values), digits) if values else None


def _select_non_overlapping(candidates, limit=8):
    selected = []
    for candidate in sorted(candidates, key=lambda row: row["rank_score"], reverse=True):
        if any(candidate["start_distance"] < row["end_distance"]
               and candidate["end_distance"] > row["start_distance"] for row in selected):
            continue
        selected.append(candidate)
        if len(selected) >= limit:
            break
    for rank, candidate in enumerate(selected, 1):
        candidate["priority_rank"] = rank
    return sorted(selected, key=lambda row: row["start_distance"])


def _downstream_clipping_loss(windows, index, lookahead_m):
    """Observed no-input clipping loss shortly after a deployment candidate."""
    origin = windows[index]["end_distance"]
    values = []
    for following in windows[index + 1:]:
        if following["start_distance"] >= origin + lookahead_m:
            break
        stat = following["mode_stats"].get("clipping")
        delta = stat.get("gain_vs_none_ms") if stat else None
        if delta is not None and delta > 0:
            values.append(delta)
    return round(max(values), 1) if values else 0.0


def analyze_ers_strategy(lap_entries, pace_window_percent=5.0, max_laps=16,
                         window_m=200.0, stride_m=50.0):
    """Compare normalized traversal times for F1 26 ERS modes by track window."""
    eligible = []
    for lap_id, lap in lap_entries:
        lap_time = _number(lap.get("lapTimeMs"))
        rows = _rows(lap)
        if (not _is_f1_26(lap) or not lap.get("validLap") or lap.get("pitLaneUsed")
                or not lap_time or len(rows) < 50):
            continue
        eligible.append({"id": lap_id, "lap": lap, "lap_time": lap_time,
                         "rows": rows, "length": rows[-1]["s"]})
    eligible.sort(key=lambda item: item["lap_time"])
    if len(eligible) < 2:
        return {"analyzable": False, "reason": "比較できる26 edition有効ラップが2周以上ありません",
                "windows": [], "recommendations": {}, "source_laps": []}
    best_time = eligible[0]["lap_time"]
    cutoff = best_time * (1 + pace_window_percent / 100)
    reference_length = eligible[0]["length"]
    selected = [item for item in eligible
                if item["lap_time"] <= cutoff
                and abs(item["length"] - reference_length) <= max(100.0, reference_length * .03)][:max_laps]
    if len(selected) < 2:
        return {"analyzable": False, "reason": "指定タイム差内に比較可能な26 editionラップが2周以上ありません",
                "windows": [], "recommendations": {}, "source_laps": []}
    for item in selected:
        item["clip_threshold"] = _clipping_threshold(item["rows"])
        item["legacy"] = not any(row["telemetry2"] for row in item["rows"])

    windows = []
    start = 0.0
    while start + window_m <= reference_length:
        observations = []
        for item in selected:
            scale = item["length"] / reference_length
            local_start, local_end = start * scale, (start + window_m) * scale
            mode, counts = _window_mode(item["rows"], local_start, local_end,
                                        item["clip_threshold"], item["legacy"])
            if mode is None:
                continue
            raw_time = _interpolate(item["rows"], local_end, "t") - _interpolate(item["rows"], local_start, "t")
            normalized_time = raw_time * best_time / item["lap_time"]
            local = [row for row in item["rows"] if local_start <= row["s"] <= local_end]
            observations.append({
                "lap_id": item["id"], "mode": mode, "counts": counts,
                "time_ms": raw_time, "normalized_time_ms": normalized_time,
                "speed": median(row["speed"] for row in local),
                "entry_speed": _interpolate(item["rows"], local_start, "speed"),
                "exit_speed": _interpolate(item["rows"], local_end, "speed"),
                "throttle": median(row["throttle"] for row in local),
                "battery_delta": ((_interpolate(item["rows"], local_end, "battery") or 0)
                                  - (_interpolate(item["rows"], local_start, "battery") or 0)),
            })
        stats = {}
        none_times = [row["normalized_time_ms"] for row in observations if row["mode"] == "none"]
        none_median = median(none_times) if none_times else None
        none_battery = _median_or_none(
            [row["battery_delta"] for row in observations if row["mode"] == "none"], 3)
        for mode in MODE_META:
            group = [row for row in observations if row["mode"] == mode]
            if not group:
                continue
            normalized = [row["normalized_time_ms"] for row in group]
            value = {
                "samples": len(group),
                "median_time_ms": round(median(row["time_ms"] for row in group), 1),
                "normalized_time_ms": round(median(normalized), 1),
                "range_ms": round(max(normalized) - min(normalized), 1),
                "median_battery_delta": _median_or_none([row["battery_delta"] for row in group], 1),
            }
            value["gain_vs_none_ms"] = (round(median(normalized) - none_median, 1)
                                         if none_median is not None and mode != "none" else 0 if mode == "none" else None)
            mode_battery = _median_or_none([row["battery_delta"] for row in group], 3)
            value["baseline_battery_delta"] = none_battery
            value["incremental_soc_cost"] = (round(max(0.0, none_battery - mode_battery), 3)
                                               if none_battery is not None and mode_battery is not None else None)
            value["soc_recovery_vs_none"] = (round(max(0.0, mode_battery - none_battery), 3)
                                               if none_battery is not None and mode_battery is not None else None)
            time_gain = (max(0.0, -value["gain_vs_none_ms"])
                         if value["gain_vs_none_ms"] is not None else None)
            cost = value["incremental_soc_cost"]
            value["time_gain_ms"] = round(time_gain, 1) if time_gain is not None else None
            value["value_ms_per_soc"] = (round(time_gain / cost, 1)
                                          if time_gain is not None and cost is not None and cost > .01 else None)
            stats[mode] = value
        speed = median(row["speed"] for row in observations)
        throttle = median(row["throttle"] for row in observations)
        speed_gain = median(row["exit_speed"] - row["entry_speed"] for row in observations)
        windows.append({
            "start_distance": round(start, 1), "end_distance": round(start + window_m, 1),
            "center_distance": round(start + window_m / 2, 1), "mode_stats": stats,
            "median_speed": round(speed, 1), "median_throttle": round(throttle, 3),
            "speed_gain": round(speed_gain, 1), "observations": len(observations),
        })
        start += stride_m

    candidate_groups = {}
    for mode in ("boost", "overtake"):
        candidates = []
        for window_index, window in enumerate(windows):
            stat = window["mode_stats"].get(mode)
            direct = stat and stat.get("gain_vs_none_ms") is not None
            gain = stat.get("gain_vs_none_ms") if direct else None
            soc_cost = stat.get("incremental_soc_cost") if direct else None
            efficiency = stat.get("value_ms_per_soc") if direct else None
            downstream_loss = _downstream_clipping_loss(windows, window_index, window_m * 2)
            clipping_penalty = (round(downstream_loss * min(1.0, soc_cost / 3.0), 1)
                                if soc_cost is not None else 0.0)
            net_gain = (round(max(0.0, -gain) - clipping_penalty, 1) if gain is not None else None)
            speed = window["median_speed"]
            throttle = window["median_throttle"]
            acceleration = max(-.2, min(1.0, window["speed_gain"] / 80.0))
            if mode == "boost":
                opportunity = throttle * (1.0 + max(0, acceleration)) * max(.15, 1 - abs(speed - 210) / 230)
                reason = "全開加速が長く、電力を速度上昇へ変えやすい"
            else:
                opportunity = throttle * max(.15, min(1.25, (speed - 150) / 130))
                reason = "高速全開区間で、追加電力を最高速側まで維持しやすい"
            evidence_weight = 1.0 if direct else .55
            observed_bonus = .75 if direct and gain is not None and gain < 0 else 0.0
            rank_score = (opportunity * evidence_weight + observed_bonus
                          + (max(0, net_gain) / 120 if net_gain is not None else 0)
                          + (min(250, efficiency) / 250 if efficiency is not None else 0))
            if throttle < .72:
                continue
            candidates.append({
                "mode": mode, "start_distance": window["start_distance"],
                "end_distance": window["end_distance"], "expected_gain_ms": gain,
                "time_gain_ms": round(max(0.0, -gain), 1) if gain is not None else None,
                "incremental_soc_cost": soc_cost, "value_ms_per_soc": efficiency,
                "downstream_clipping_loss_ms": downstream_loss,
                "clipping_risk_penalty_ms": clipping_penalty,
                "net_time_gain_ms": net_gain,
                "evidence": "observed" if direct else "inferred",
                "mode_samples": stat["samples"] if stat else 0,
                "baseline_samples": window["mode_stats"].get("none", {}).get("samples", 0),
                "median_speed": speed, "speed_gain": window["speed_gain"],
                "reason": reason, "rank_score": round(rank_score, 4),
            })
        candidate_groups[mode] = candidates

    # A single plan resolves overlap across Boost and Overtake. Moving windows
    # remain available for diagnostics, but are never summed as independent gains.
    recommended_plan = _select_non_overlapping(
        candidate_groups["boost"] + candidate_groups["overtake"], limit=8)
    recommendations = {
        mode: [row for row in recommended_plan if row["mode"] == mode]
        for mode in ("boost", "overtake")
    }

    mode_summary = {}
    for mode in MODE_META:
        comparable = [window["mode_stats"][mode]["gain_vs_none_ms"] for window in windows
                      if mode in window["mode_stats"]
                      and window["mode_stats"][mode].get("gain_vs_none_ms") is not None]
        observed = sum(window["mode_stats"].get(mode, {}).get("samples", 0) for window in windows)
        mode_summary[mode] = {
            "observed_windows": sum(1 for window in windows if mode in window["mode_stats"]),
            "observations": observed, "comparable_windows": len(comparable),
            "median_gain_vs_none_ms": _median_or_none(comparable, 1),
            "median_incremental_soc_cost": _median_or_none([
                window["mode_stats"][mode].get("incremental_soc_cost") for window in windows
                if mode in window["mode_stats"] and window["mode_stats"][mode].get("gain_vs_none_ms") is not None
            ], 3),
            "median_value_ms_per_soc": _median_or_none([
                window["mode_stats"][mode].get("value_ms_per_soc") for window in windows
                if mode in window["mode_stats"]
            ], 1),
        }
    source_laps = [{
        "id": item["id"], "session": str(item["id"]).split("/", 1)[0],
        "lap_number": item["lap"].get("lapNumber"), "lap_time_ms": item["lap_time"],
        "gap_percent": round((item["lap_time"] / best_time - 1) * 100, 3),
        "legacy_mode_data": item["legacy"], "clipping_available": item["clip_threshold"] is not None,
    } for item in selected]
    track_points = [{"s": round(row["s"], 1), "x": round(row["x"], 3), "z": round(row["z"], 3)}
                    for row in selected[0]["rows"] if row["x"] is not None and row["z"] is not None]
    return {
        "analyzable": True, "reason": None, "schema_version": 2,
        "evaluation_model": "soc-efficient-non-overlap-v2",
        "track_id": selected[0]["lap"].get("trackId"),
        "track_length_m": round(reference_length, 1), "best_lap_time_ms": best_time,
        "compared_lap_count": len(selected), "eligible_lap_count": len(eligible),
        "settings": {"pace_window_percent": pace_window_percent, "max_laps": max_laps,
                     "window_m": window_m, "stride_m": stride_m,
                     "clipping_rule": "full_throttle_no_input_mguk_below_20_percent",
                     "ranking": "time_gain_per_incremental_soc_with_downstream_clipping_penalty",
                     "recommendations_are_non_overlapping": True},
        "mode_meta": MODE_META, "mode_summary": mode_summary,
        "recommendations": recommendations, "recommended_plan": recommended_plan,
        "windows": windows, "source_laps": source_laps,
        "track_points": track_points,
    }
