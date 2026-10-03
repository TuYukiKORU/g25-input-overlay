"""Offline, deterministic session analysis built from persisted lap JSON files."""
from bisect import bisect_left
from datetime import datetime, timezone
from math import hypot, sqrt
from statistics import median

from lap_analyzer import detect_events
from comparison_context import comparison_context
from analysis_config import ANALYSIS_CONFIG
from workspace_insights import wear_estimate
from track_sections import analyze_track_sections
from telemetry_quality import number, geometry_quality


SECTION_M = 10.0
MIN_POSITION_POINTS = 20
WHEELS = ("front_left", "front_right", "rear_left", "rear_right")


def _number(value, default=None):
    try:
        value = float(value)
        return value if number(value) is not None else default
    except (TypeError, ValueError):
        return default


def _mean(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def _position(sample, planar=False):
    position = sample.get("position") or {}
    values = (_number(position.get("x")), 0.0 if planar else _number(position.get("y")),
              _number(position.get("z")))
    return values if all(value is not None for value in values) else None


def _reference_line(lap, planar=None):
    if planar is None:
        planar = geometry_quality(lap.get("samples", [])).get("dimensions") != "3D"
    points = []
    for sample in sorted(lap.get("samples", []), key=lambda row: _number(row.get("lap_distance"), 0)):
        position = _position(sample, planar)
        if position is None:
            continue
        if not points or sum((position[i] - points[-1]["xyz"][i]) ** 2 for i in range(3)) >= 1.0:
            points.append({"xyz": position, "source_distance": _number(sample.get("lap_distance"), 0)})
    if len(points) < MIN_POSITION_POINTS:
        return None, "XYZ座標を持つ基準ラップのサンプルが不足しています"
    cumulative = [0.0]
    for before, after in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + sqrt(sum((after["xyz"][i] - before["xyz"][i]) ** 2 for i in range(3))))
    geometry_length = cumulative[-1]
    source_length = max(point["source_distance"] for point in points)
    if geometry_length < 500 or source_length < 500:
        return None, "基準走行ラインの距離を確定できません"
    scale = source_length / geometry_length
    for point, distance in zip(points, cumulative):
        point["s"] = distance * scale
    return points, None


def _project(position, line, candidate_start=0, candidate_end=None):
    """Project XYZ onto the nearest reference polyline segment and return Frenet s,d."""
    best = None
    candidate_end = min(len(line) - 1, candidate_end if candidate_end is not None else len(line) - 1)
    for index in range(max(0, candidate_start), candidate_end):
        a, b = line[index], line[index + 1]
        av, bv = a["xyz"], b["xyz"]
        vector = tuple(bv[i] - av[i] for i in range(3))
        length2 = sum(value * value for value in vector)
        if length2 <= 1e-9:
            continue
        offset = tuple(position[i] - av[i] for i in range(3))
        fraction = max(0.0, min(1.0, sum(offset[i] * vector[i] for i in range(3)) / length2))
        projected = tuple(av[i] + fraction * vector[i] for i in range(3))
        error2 = sum((position[i] - projected[i]) ** 2 for i in range(3))
        if best is None or error2 < best[0]:
            segment_s = a["s"] + fraction * (b["s"] - a["s"])
            # Signed horizontal cross product; magnitude remains true 3-D deviation.
            cross = vector[0] * offset[2] - vector[2] * offset[0]
            sign = -1.0 if cross < 0 else 1.0
            best = (error2, segment_s, sign * sqrt(error2), index)
    return best[1:] if best else None


def _interp(rows, distance, key):
    points = [(row["s"], row.get(key)) for row in rows if row.get(key) is not None]
    if not points or distance < points[0][0] or distance > points[-1][0]:
        return None
    xs = [point[0] for point in points]
    index = bisect_left(xs, distance)
    if index == 0 or points[index][0] == distance:
        return points[index][1]
    x0, y0 = points[index - 1]; x1, y1 = points[index]
    if x1 - x0 > ANALYSIS_CONFIG["maximum_comparison_gap_m"]:
        return None
    return y0 if x1 == x0 else y0 + (y1 - y0) * (distance - x0) / (x1 - x0)


def _wear(lap):
    values = []
    for source in (lap.get("tyreWearAtStart"), lap.get("tyreWearAtEnd")):
        values.extend(_number((source or {}).get(wheel)) for wheel in WHEELS)
    return _mean(values)


def _prepare_lap(lap_id, lap, line, track_length, planar=False):
    projected = []
    source_distances = [point["source_distance"] for point in line]
    ordered_samples = sorted(lap.get("samples", []), key=lambda row: (_number(row.get("lap_time_ms"), float("inf")), _number(row.get("lap_distance"), 0)))
    for sample in ordered_samples:
        position = _position(sample, planar)
        hint = _number(sample.get("lap_distance"))
        if position and hint is not None:
            center = bisect_left(source_distances, hint)
            projection = _project(position, line, center - 16, center + 16)
        else:
            projection = _project(position, line) if position else None
        if not projection:
            continue
        s, d, _ = projection
        projected.append({
            "s": s, "d": d, "time": _number(sample.get("lap_time_ms")),
            "speed": _number(sample.get("speed")), "throttle": _number(sample.get("throttle")),
            "brake": _number(sample.get("brake")), "ers": bool(sample.get("ers_usage")),
            "aero": bool(sample.get("active_aero") or sample.get("drs")),
            "ers_percent": _number(sample.get("ers_percent")),
            "acceleration_g": _number(sample.get("longitudinal_g")),
            "max_slip": max([abs(_number(value, 0)) for value in (sample.get("wheel_slip_ratio") or {}).values()] or [0]),
        })
    # Nearest-line projection can briefly go backwards; retain the most progressive sequence.
    monotonic = []
    for row in projected:
        if not monotonic or row["s"] >= monotonic[-1]["s"] - 2:
            if monotonic and row["s"] < monotonic[-1]["s"]:
                row["s"] = monotonic[-1]["s"]
            monotonic.append(row)
    sections = []
    for start in range(0, int(track_length // SECTION_M) * int(SECTION_M), int(SECTION_M)):
        end = start + SECTION_M
        t0, t1 = _interp(monotonic, start, "time"), _interp(monotonic, end, "time")
        local = [row for row in monotonic if start <= row["s"] < end]
        if t0 is None or t1 is None or t1 <= t0:
            sections.append(None)
            continue
        sections.append({
            "time_ms": t1 - t0, "mean_d": _mean([row["d"] for row in local]),
            "speed": _mean([row["speed"] for row in local]),
            "throttle": _mean([row["throttle"] for row in local]),
            "brake": _mean([row["brake"] for row in local]),
            "ers_used": any(row["ers"] for row in local), "aero_used": any(row["aero"] for row in local),
        })
    events = detect_events(lap.get("samples", []), "active_aero" if lap.get("packetFormat") == 2026 else "drs")
    contaminated_sections = set()
    for event in events:
        if event["type"] not in ("wheel_spin", "tyre_lock", "pit_lane", "lap_invalidated"):
            continue
        start = max(0, int(_number(event.get("start_distance"), 0) // SECTION_M))
        end = max(start, int(_number(event.get("end_distance"), start * SECTION_M) // SECTION_M))
        contaminated_sections.update(range(start, end + 1))
    disqualifying = any(event["type"] in ("pit_lane", "lap_invalidated") for event in events)
    return {
        "id": lap_id, "lap": lap, "lap_number": lap.get("lapNumber"), "sections": sections,
        "wear": _wear(lap), "ers_end": _number((lap.get("samples") or [{}])[-1].get("ers_percent")),
        "events": events, "eligible": bool(lap.get("validLap") and not lap.get("pitLaneUsed") and not disqualifying),
        "contaminated_sections": contaminated_sections,
        "samples": monotonic,
        "projected_samples": len(monotonic),
    }


def _confidence(sample_count, coverage, comparable_count):
    score = min(1.0, sample_count / 6.0) * min(1.0, coverage / .9) * min(1.0, comparable_count / 3.0)
    label = "high" if score >= .75 else "medium" if score >= .45 else "low"
    return {"score": round(score, 2), "label": label}


def _reason_and_suggestion(selected, compared, delta, event_types, ers_effect, aero_difference):
    reasons = []
    if "wheel_spin" in event_types:
        reasons.append("ホイールスピン")
    if "tyre_lock" in event_types:
        reasons.append("タイヤロック")
    if selected and compared:
        if (selected.get("brake") or 0) > (compared.get("brake") or 0) + .12:
            reasons.append("ブレーキ量が多い")
        if (selected.get("throttle") or 0) + .12 < (compared.get("throttle") or 0):
            reasons.append("スロットル復帰が遅い")
        if (selected.get("speed") or 0) + 6 < (compared.get("speed") or 0):
            reasons.append("区間平均速度が低い")
    if ers_effect == "faster_with_ers" and selected and not selected.get("ers_used"):
        reasons.append("ERS未使用")
    if aero_difference and selected and not selected.get("aero_used"):
        reasons.append("Active Aero/DRS未使用")
    if not reasons:
        reasons.append("走行ラインまたは複合操作差")
    primary = reasons[0]
    suggestions = {
        "ホイールスピン": "立ち上がりのスロットルを滑らかにする",
        "タイヤロック": "制動初期のピークを抑える",
        "ブレーキ量が多い": "比較ラップの制動開始とリリースを確認する",
        "スロットル復帰が遅い": "旋回後のスロットル復帰を早める",
        "区間平均速度が低い": "進入速度と走行ラインを比較する",
        "ERS未使用": "出口加速でERS配分を検討する",
        "Active Aero/DRS未使用": "使用可能条件と作動タイミングを確認する",
    }
    return ", ".join(reasons[:3]), suggestions.get(primary, "比較ラップのラインと操作を重ねて確認する")


def _linear_slope(xs, ys):
    if len(xs) < 3:
        return None
    xbar, ybar = _mean(xs), _mean(ys)
    denominator = sum((x - xbar) ** 2 for x in xs)
    return None if denominator <= 1e-9 else sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denominator


def _turn_metrics(item, corner):
    rows = item.get("samples", [])
    start, end, apex = (float(corner[key]) for key in ("start_distance", "end_distance", "apex_distance"))
    if any(b["s"] - a["s"] > ANALYSIS_CONFIG["maximum_comparison_gap_m"] and a["s"] < end and b["s"] > start for a, b in zip(rows, rows[1:])):
        return None
    start_time, end_time = _interp(rows, start, "time"), _interp(rows, end, "time")
    if start_time is None or end_time is None or end_time <= start_time:
        return None
    entry_speed = _interp(rows, start, "speed")
    apex_speed = _interp(rows, apex, "speed")
    exit_rows = [row for row in rows if end <= row["s"] <= end + 80]
    exit_acceleration = _mean([row.get("acceleration_g") for row in exit_rows])
    if exit_acceleration is None and len(exit_rows) >= 2:
        elapsed = (exit_rows[-1]["time"] - exit_rows[0]["time"]) / 1000 if exit_rows[-1].get("time") is not None and exit_rows[0].get("time") is not None else 0
        if elapsed > 0 and exit_rows[-1].get("speed") is not None and exit_rows[0].get("speed") is not None:
            exit_acceleration = ((exit_rows[-1]["speed"] - exit_rows[0]["speed"]) / 3.6) / elapsed / 9.80665
    exit_speed = _interp(rows, min(end + 80, rows[-1]["s"]), "speed") if rows else None
    local = [row for row in rows if start <= row["s"] <= end + 40]
    events = [event for event in item["events"] if _number(event.get("start_distance"), -1) <= end + 40 and _number(event.get("end_distance"), -1) >= start]
    event_types = sorted({event["type"] for event in events if event["type"] in ("wheel_spin", "tyre_lock")})
    return {
        "time_ms": end_time - start_time,
        "entry_speed_kph": entry_speed, "apex_speed_kph": apex_speed,
        "exit_speed_kph": exit_speed, "exit_acceleration_g": exit_acceleration,
        "peak_slip": max([row.get("max_slip", 0) for row in local] or [0]),
        "events": event_types,
    }


def _turn_reason(selected, compared):
    reasons, suggestions = [], []
    if "tyre_lock" in selected.get("events", []):
        reasons.append("Tyre lock"); suggestions.append("Reduce the initial brake peak and release progressively")
    if "wheel_spin" in selected.get("events", []):
        reasons.append("Wheel spin"); suggestions.append("Use a smoother throttle ramp at corner exit")
    if compared:
        if selected.get("entry_speed_kph") is not None and compared.get("entry_speed_kph") is not None and selected["entry_speed_kph"] + 5 < compared["entry_speed_kph"]:
            reasons.append("Low entry speed"); suggestions.append("Carry more speed into the braking phase")
        if selected.get("apex_speed_kph") is not None and compared.get("apex_speed_kph") is not None and selected["apex_speed_kph"] + 4 < compared["apex_speed_kph"]:
            reasons.append("Low apex speed"); suggestions.append("Review line and brake release near the apex")
        if selected.get("exit_acceleration_g") is not None and compared.get("exit_acceleration_g") is not None and selected["exit_acceleration_g"] + .08 < compared["exit_acceleration_g"]:
            reasons.append("Weak exit acceleration"); suggestions.append("Prioritize rotation and earlier progressive throttle")
    return (", ".join(reasons) or "No dominant issue", "; ".join(dict.fromkeys(suggestions)) or "Compare line and control traces")


def _analyze_turns(prepared, eligible, selected, compared, reference_lap, settings, turn_definition=None):
    definition = turn_definition or analyze_track_sections(reference_lap, **settings)
    if not definition.get("analyzable"):
        return [], definition
    turns = []
    for corner in definition.get("corners", []):
        selected_metrics = _turn_metrics(selected, corner)
        compared_metrics = _turn_metrics(compared, corner) if compared else None
        if selected_metrics is None:
            continue
        samples = []
        for item in eligible:
            metrics = _turn_metrics(item, corner)
            if metrics and not metrics["events"]:
                samples.append((item, metrics))
        best_item, best_metrics = min(samples, key=lambda row: row[1]["time_ms"], default=(selected, selected_metrics))
        delta = selected_metrics["time_ms"] - compared_metrics["time_ms"] if compared_metrics else None
        potential = max(0.0, selected_metrics["time_ms"] - best_metrics["time_ms"])
        cause, suggestion = _turn_reason(selected_metrics, compared_metrics)
        turns.append({
            "label": corner["label"], "direction": corner["direction"],
            "complex_type": corner.get("complex_type"), "complex_id": corner.get("complex_id"),
            "start_distance": corner["start_distance"], "end_distance": corner["end_distance"],
            "apex_distance": corner["apex_distance"], "radius_m": corner.get("radius_m"),
            "time_delta_ms": round(delta, 2) if delta is not None else None,
            "outcome": "loss" if delta is not None and delta > 0 else "gain" if delta is not None and delta < 0 else "neutral",
            "potential_loss_ms": round(potential, 2), "best_lap_number": best_item["lap_number"],
            "selected": {key: round(value, 3) if isinstance(value, float) else value for key, value in selected_metrics.items()},
            "comparison": {key: round(value, 3) if isinstance(value, float) else value for key, value in compared_metrics.items()} if compared_metrics else None,
            "primary_cause": cause, "suggestion": suggestion,
            "confidence": _confidence(len(samples), 1.0, max(1, len(eligible) - 1)),
            "sample_count": len(samples),
        })
    return turns, definition


def analyze_session(lap_entries, selected_lap_id=None, progress=None, section_settings=None,
                    turn_definition=None):
    """Analyze one session/track. This function performs no network or global-state I/O."""
    report = progress or (lambda percent, current: None)
    report(5, "ラップデータを検証中")
    if len(lap_entries) < 2:
        return _unavailable("比較に必要なラップが2周未満です", len(lap_entries))
    valid = [(lap_id, lap) for lap_id, lap in lap_entries if lap.get("validLap") and lap.get("samples")]
    if not valid:
        return _unavailable("有効な完走ラップがありません", len(lap_entries))
    reference_id, reference_lap = min(valid, key=lambda item: _number(item[1].get("lapTimeMs"), float("inf")))
    planar = any(geometry_quality(lap.get("samples", [])).get("dimensions") != "3D" for _, lap in valid)
    line, reason = _reference_line(reference_lap, planar)
    if line is None:
        return _unavailable(reason, len(lap_entries))
    track_length = line[-1]["s"]
    report(18, "XYZ座標から基準走行ラインを生成中")
    prepared = []
    for index, entry in enumerate(lap_entries):
        prepared.append(_prepare_lap(entry[0], entry[1], line, track_length, planar))
        report(18 + int(32 * (index + 1) / len(lap_entries)), f"ラップ {entry[1].get('lapNumber', '?')} を10m間隔へ変換中")
    eligible = [item for item in prepared if item["eligible"]]
    if len(eligible) < 2:
        return _unavailable("ピット周回と無効周を除くと比較可能なラップが2周未満です", len(lap_entries))
    selected = next((item for item in prepared if item["id"] == selected_lap_id), None) or min(eligible, key=lambda item: item["lap"].get("lapTimeMs", float("inf")))
    candidates = [item for item in eligible if item["id"] != selected["id"]]
    def similarity(item):
        return (comparison_context(selected["lap"], item["lap"])["score"], item["lap"].get("lapTimeMs", 0))
    compared = min(candidates, key=similarity) if candidates else selected
    settings = {"threshold": .0066, "smoothing_m": 20.0, "min_length_m": 15.0}
    settings.update(section_settings or {})
    turns, turn_definition = _analyze_turns(
        prepared, eligible, selected, compared, reference_lap, settings, turn_definition)
    report(58, "区間タイムと理論最速を計算中")
    section_count = min(len(item["sections"]) for item in eligible)
    best_sections, theoretical_ms, contaminated_fallbacks = [], 0.0, 0
    for index in range(section_count):
        all_values = [(item, item["sections"][index]) for item in eligible if item["sections"][index]]
        values = [(item, section) for item, section in all_values if index not in item["contaminated_sections"]]
        if not values and all_values:
            values = all_values
            contaminated_fallbacks += 1
        if not values:
            best_sections.append(None); continue
        typical = median(section["time_ms"] for _, section in values)
        plausible = [(item, section) for item, section in values if typical * .65 <= section["time_ms"] <= typical * 1.8]
        values = plausible or values
        owner, best = min(values, key=lambda value: value[1]["time_ms"])
        theoretical_ms += best["time_ms"]
        best_sections.append((owner, best))
    usable_best = sum(value is not None for value in best_sections)
    if usable_best < max(20, section_count * .95):
        return _unavailable("共通距離軸で有効な区間が不足しています", len(lap_entries))

    # Cross-lap ERS/aero evidence, computed only where both usage groups exist.
    effects = []
    for index in range(section_count):
        rows = [(item, item["sections"][index]) for item in eligible if item["sections"][index] and index not in item["contaminated_sections"]]
        with_ers = [row[1]["time_ms"] for row in rows if row[1]["ers_used"]]
        without_ers = [row[1]["time_ms"] for row in rows if not row[1]["ers_used"]]
        ers_delta = median(with_ers) - median(without_ers) if with_ers and without_ers else None
        effects.append({"ers_delta_ms": ers_delta, "samples_with_ers": len(with_ers), "samples_without_ers": len(without_ers)})

    event_losses = {"wheel_spin": 0.0, "tyre_lock": 0.0}
    sections = []
    cumulative = 0.0
    selected_loss = 0.0
    selected_resampled_ms = 0.0
    for index, best_value in enumerate(best_sections):
        if best_value is None:
            continue
        owner, best = best_value
        current = selected["sections"][index] if index < len(selected["sections"]) else None
        comparison = compared["sections"][index] if index < len(compared["sections"]) else None
        if current is None:
            continue
        delta = current["time_ms"] - (comparison["time_ms"] if comparison else best["time_ms"])
        loss = max(0.0, current["time_ms"] - best["time_ms"])
        selected_loss += loss
        selected_resampled_ms += current["time_ms"]
        cumulative += delta
        start, end = index * SECTION_M, (index + 1) * SECTION_M
        event_types = {event["type"] for event in selected["events"] if _number(event.get("start_distance"), -1) < end and _number(event.get("end_distance"), -1) >= start}
        for event_type in event_losses:
            if event_type in event_types:
                event_losses[event_type] += loss
        effect = effects[index]
        ers_class = None
        if effect["ers_delta_ms"] is not None:
            ers_class = "faster_with_ers" if effect["ers_delta_ms"] < -5 else "possibly_better_saved" if effect["ers_delta_ms"] > 5 else "neutral"
        aero_difference = bool(comparison and current["aero_used"] != comparison["aero_used"])
        cause, suggestion = _reason_and_suggestion(current, comparison, delta, event_types, ers_class, aero_difference)
        section_confidence = _confidence(len(eligible), 1.0 if comparison else .6, len(candidates))
        sections.append({
            "index": index, "name": f"{int(start)}–{int(end)} m", "start_distance": start, "end_distance": end,
            "selected_time_ms": round(current["time_ms"], 2), "comparison_time_ms": round(comparison["time_ms"], 2) if comparison else None,
            "segment_delta_ms": round(delta, 2), "cumulative_delta_ms": round(cumulative, 2),
            "estimated_loss_ms": round(loss, 2), "best_time_ms": round(best["time_ms"], 2), "best_lap_number": owner["lap_number"],
            "primary_cause": cause, "suggestion": suggestion, "confidence": section_confidence,
            "ers_effect": ers_class, "ers_effect_ms": round(effect["ers_delta_ms"], 2) if effect["ers_delta_ms"] is not None else None,
            "active_aero_difference": aero_difference, "selected_mean_d": round(current["mean_d"], 3) if current["mean_d"] is not None else None,
            "sample_count": len(eligible),
        })
    report(82, "タイヤ摩耗とERS/Aero影響を集計中")
    wear_result = wear_estimate(lap_entries, selected["lap"])
    top = sorted(sections, key=lambda row: row["estimated_loss_ms"], reverse=True)[:5]
    faster_ers = [row for row in sections if row["ers_effect"] == "faster_with_ers"]
    saved_ers = [row for row in sections if row["ers_effect"] == "possibly_better_saved"]
    aero_differences = [row for row in sections if row["active_aero_difference"]]
    coverage = len(sections) / max(section_count, 1)
    confidence = _confidence(len(eligible), coverage, len(candidates))
    # Net loss to the stitched lap; section-level positive losses remain available for coaching/event attribution.
    selected_loss = max(0.0, selected_resampled_ms - theoretical_ms)
    report(96, "分析結果を保存中")
    return {
        "schema_version": 1, "status": "completed", "analyzable": True,
        "generated_at": datetime.now(timezone.utc).isoformat(), "section_size_m": SECTION_M,
        "track_length_m": round(track_length, 1), "reference_line_points": len(line),
        "coordinate_mode": "planar_xz" if planar else "measured_xyz",
        "selected_lap_id": selected["id"], "selected_lap_number": selected["lap_number"],
        "comparison_lap_id": compared["id"], "comparison_lap_number": compared["lap_number"],
        "comparison_reason": "Closest recorded compound, setup, starting fuel, wear and ERS conditions; missing values penalized",
        "comparison_context": comparison_context(selected["lap"], compared["lap"]),
        "theoretical_fastest_ms": round(theoretical_ms, 2), "selected_estimated_loss_ms": round(selected_loss, 2),
        "top_improvement_sections": top, "sections": sections,
        "turns": turns, "turn_definition": {
            "settings": turn_definition.get("settings", settings), "corners": turn_definition.get("corners", []),
            "chicanes": turn_definition.get("chicanes", []), "reason": turn_definition.get("reason"),
            "profile": turn_definition.get("profile"),
        },
        "turn_summary": {
            "total_delta_ms": round(sum(turn["time_delta_ms"] or 0 for turn in turns), 2),
            "total_potential_loss_ms": round(sum(turn["potential_loss_ms"] for turn in turns), 2),
            "loss_count": sum(turn["outcome"] == "loss" for turn in turns),
            "gain_count": sum(turn["outcome"] == "gain" for turn in turns),
        },
        "ers_faster_sections": faster_ers, "ers_save_candidate_sections": saved_ers,
        "active_aero_differences": aero_differences,
        "tyre_wear_estimate": wear_result,
        "event_loss_estimates": {key: round(value, 2) for key, value in event_losses.items()},
        "confidence": confidence,
        "sample_counts": {"recorded_laps": len(lap_entries), "eligible_laps": len(eligible), "comparison_laps": len(candidates),
                          "usable_sections": len(sections), "event_affected_fallback_sections": contaminated_fallbacks},
        "excluded_laps": [{"lap_number": item["lap_number"], "reason": "無効またはピット周回"}
                          for item in prepared if not item["eligible"]],
    }


def _unavailable(reason, lap_count):
    return {
        "schema_version": 1, "status": "completed", "analyzable": False,
        "generated_at": datetime.now(timezone.utc).isoformat(), "reason": reason,
        "confidence": {"score": 0.0, "label": "unavailable"},
        "sample_counts": {"recorded_laps": lap_count, "eligible_laps": 0, "comparison_laps": 0, "usable_sections": 0},
        "sections": [], "top_improvement_sections": [],
    }
