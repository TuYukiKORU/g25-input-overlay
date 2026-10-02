"""Experimental segmentation of a lap by the driver's longitudinal inputs."""
from bisect import bisect_left
from collections import Counter
from statistics import median


SECTION_META = {
    "braking": {"label": "減速", "color": "#ff5263"},
    "lift": {"label": "リフト", "color": "#ffd166"},
    "acceleration": {"label": "加速", "color": "#45d98a"},
    "flat_out": {"label": "フラットアウト", "color": "#39b8ff"},
}


def _number(value, default=None):
    try:
        value = float(value)
        return value if value == value else default
    except (TypeError, ValueError):
        return default


def _input(value):
    value = _number(value, 0.0)
    if value > 1.5:  # Be tolerant of sources that store pedal position as 0..100.
        value /= 100.0
    return max(0.0, min(1.0, value))


def _raw_rows(lap):
    rows = []
    for sample in lap.get("samples", []):
        position = sample.get("position") or {}
        distance = _number(sample.get("lap_distance"))
        speed = _number(sample.get("speed"))
        x, z = _number(position.get("x")), _number(position.get("z"))
        if None in (distance, speed, x, z):
            continue
        rows.append({
            "s": distance, "t": _number(sample.get("lap_time_ms")),
            "x": x, "z": z, "speed": speed,
            "throttle": _input(sample.get("throttle")),
            "brake": _input(sample.get("brake")),
        })
    rows.sort(key=lambda row: row["s"])
    unique = []
    for row in rows:
        if not unique or row["s"] > unique[-1]["s"] + .01:
            unique.append(row)
    return unique


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


def _moving_average(values, radius):
    if radius <= 0:
        return values[:]
    prefix = [0.0]
    for value in values:
        prefix.append(prefix[-1] + value)
    return [
        (prefix[min(len(values), index + radius + 1)] - prefix[max(0, index - radius)])
        / (min(len(values), index + radius + 1) - max(0, index - radius))
        for index in range(len(values))
    ]


def _runs(kinds):
    runs = []
    for index, kind in enumerate(kinds):
        if not runs or runs[-1]["kind"] != kind:
            runs.append({"kind": kind, "start": index, "end": index})
        else:
            runs[-1]["end"] = index
    return runs


def _merge_short_runs(kinds, step_m, minimum_m):
    """Suppress pedal jitter without moving the boundaries of meaningful runs."""
    kinds = kinds[:]
    for _ in range(8):
        runs = _runs(kinds)
        changed = False
        for position, run in enumerate(runs):
            length = (run["end"] - run["start"] + 1) * step_m
            if length >= minimum_m or len(runs) == 1:
                continue
            before = runs[position - 1] if position else None
            after = runs[position + 1] if position + 1 < len(runs) else None
            if before and after and before["kind"] == after["kind"]:
                replacement = before["kind"]
            elif before and after:
                before_length = before["end"] - before["start"]
                after_length = after["end"] - after["start"]
                replacement = before["kind"] if before_length >= after_length else after["kind"]
            else:
                replacement = (before or after)["kind"]
            for index in range(run["start"], run["end"] + 1):
                kinds[index] = replacement
            changed = True
            break
        if not changed:
            break
    return kinds


def _classify(point, braking_threshold, flat_threshold, lift_threshold):
    # Brake takes priority. A strong measured deceleration with no throttle also
    # catches engine-braking or a slightly noisy brake channel.
    if point["brake"] >= braking_threshold or (
            point["accel"] <= -1.5 and point["throttle"] < .20):
        return "braking"
    if point["throttle"] >= flat_threshold:
        return "flat_out"
    if point["throttle"] <= lift_threshold or (
            point["accel"] < -.25 and point["throttle"] < flat_threshold):
        return "lift"
    return "acceleration"


def analyze_operation_sections(lap, step_m=5.0, smoothing_m=15.0,
                               min_section_m=20.0, braking_threshold=.05,
                               flat_threshold=.95, lift_threshold=.20):
    """Return a distance-resampled racing line and exclusive input sections."""
    rows = _raw_rows(lap)
    if len(rows) < 20:
        return {"analyzable": False, "reason": "入力とXYZ座標を持つサンプルが不足しています", "points": [], "sections": []}
    start, finish = max(0.0, rows[0]["s"]), rows[-1]["s"]
    if finish - start < 500:
        return {"analyzable": False, "reason": "コース全体を構成できる距離データがありません", "points": [], "sections": []}

    distances, distance = [], start
    while distance <= finish:
        distances.append(distance)
        distance += step_m
    keys = ("t", "x", "z", "speed", "throttle", "brake")
    values = {key: [_interpolate(rows, distance, key) for distance in distances] for key in keys}
    radius = max(0, round(smoothing_m / step_m / 2))
    for key in ("speed", "throttle", "brake"):
        values[key] = _moving_average(values[key], radius)

    points = []
    for index, distance in enumerate(distances):
        before, after = max(0, index - 1), min(len(distances) - 1, index + 1)
        elapsed = ((values["t"][after] or 0) - (values["t"][before] or 0)) / 1000.0
        acceleration = 0.0 if elapsed <= 1e-4 else (
            (values["speed"][after] - values["speed"][before]) / 3.6 / elapsed)
        points.append({
            "s": round(distance, 1), "t": round(values["t"][index] or 0),
            "x": round(values["x"][index], 3), "z": round(values["z"][index], 3),
            "speed": round(values["speed"][index], 1),
            "throttle": round(values["throttle"][index], 3),
            "brake": round(values["brake"][index], 3),
            "accel": round(max(-12.0, min(12.0, acceleration)), 2),
        })
    kinds = [_classify(point, braking_threshold, flat_threshold, lift_threshold) for point in points]
    kinds = _merge_short_runs(kinds, step_m, min_section_m)
    for point, kind in zip(points, kinds):
        point["kind"] = kind

    sections = []
    for number, run in enumerate(_runs(kinds), 1):
        group = points[run["start"]:run["end"] + 1]
        first, last = group[0], group[-1]
        sections.append({
            "number": number, "kind": run["kind"],
            "label": SECTION_META[run["kind"]]["label"],
            "color": SECTION_META[run["kind"]]["color"],
            "start_distance": first["s"], "end_distance": last["s"],
            "length_m": round(max(step_m, last["s"] - first["s"] + step_m), 1),
            "duration_ms": max(0, last["t"] - first["t"]),
            "entry_speed": first["speed"], "exit_speed": last["speed"],
            "min_speed": min(point["speed"] for point in group),
            "max_speed": max(point["speed"] for point in group),
            "average_throttle": round(sum(point["throttle"] for point in group) / len(group), 3),
            "average_brake": round(sum(point["brake"] for point in group) / len(group), 3),
        })
    totals = {kind: round(sum(section["length_m"] for section in sections if section["kind"] == kind), 1)
              for kind in SECTION_META}
    return {
        "analyzable": True, "reason": None, "track_length_m": round(finish, 1),
        "source_lap_number": lap.get("lapNumber"), "lap_time_ms": lap.get("lapTimeMs"),
        "sample_count": len(points), "settings": {
            "step_m": step_m, "smoothing_m": smoothing_m, "min_section_m": min_section_m,
            "braking_threshold": braking_threshold, "flat_threshold": flat_threshold,
            "lift_threshold": lift_threshold,
        }, "legend": SECTION_META, "totals_m": totals,
        "points": points, "sections": sections,
    }


def build_operation_library(lap_entries, pace_window_percent=3.0, max_laps=8,
                            step_m=5.0, smoothing_m=15.0, min_section_m=20.0,
                            braking_threshold=.05, flat_threshold=.95,
                            lift_threshold=.20):
    """Build one representative operation map from several competitive laps.

    ``lap_entries`` contains ``(lap_id, lap)`` pairs. Only valid, complete,
    non-pit laps close to the fastest time are used. Every selected lap is
    normalized by track progress before voting, so small telemetry distance
    differences do not move a braking zone around the map.
    """
    eligible = []
    for lap_id, lap in lap_entries:
        lap_time = _number(lap.get("lapTimeMs"))
        if (not lap.get("validLap") or lap.get("pitLaneUsed") or not lap_time
                or lap_time <= 0 or len(lap.get("samples", [])) < 20):
            continue
        eligible.append((lap_id, lap, lap_time))
    eligible.sort(key=lambda item: item[2])
    if not eligible:
        return {"analyzable": False, "reason": "比較できる有効ラップがありません", "points": [], "sections": [], "source_laps": []}

    best_time = eligible[0][2]
    cutoff = best_time * (1.0 + pace_window_percent / 100.0)
    selected = [item for item in eligible if item[2] <= cutoff]
    analyses = []
    reference_length = None
    for lap_id, lap, lap_time in selected:
        analysis = analyze_operation_sections(
            lap, step_m=step_m, smoothing_m=smoothing_m,
            min_section_m=min_section_m, braking_threshold=braking_threshold,
            flat_threshold=flat_threshold, lift_threshold=lift_threshold)
        if not analysis.get("analyzable"):
            continue
        if reference_length is None:
            reference_length = analysis["track_length_m"]
        if abs(analysis["track_length_m"] - reference_length) > max(100.0, reference_length * .03):
            continue
        analyses.append({"id": lap_id, "lap": lap, "lap_time": lap_time, "analysis": analysis})
        if len(analyses) >= max_laps:
            break
    if len(analyses) < 2:
        return {"analyzable": False, "reason": "十分速い比較可能なラップが2周以上ありません", "points": [], "sections": [],
                "source_laps": [], "eligible_lap_count": len(eligible)}

    reference = analyses[0]["analysis"]
    points = []
    priority = {kind: len(SECTION_META) - index for index, kind in enumerate(SECTION_META)}
    for index, reference_point in enumerate(reference["points"]):
        progress = index / max(1, len(reference["points"]) - 1)
        samples = []
        for item in analyses:
            source_points = item["analysis"]["points"]
            samples.append(source_points[round(progress * (len(source_points) - 1))])
        votes = Counter(sample["kind"] for sample in samples)
        kind = max(votes, key=lambda value: (votes[value], priority[value]))
        point = {
            "s": reference_point["s"], "x": reference_point["x"], "z": reference_point["z"],
            "t": round(median(sample["t"] for sample in samples)),
            "speed": round(median(sample["speed"] for sample in samples), 1),
            "speed_low": round(min(sample["speed"] for sample in samples), 1),
            "speed_high": round(max(sample["speed"] for sample in samples), 1),
            "throttle": round(median(sample["throttle"] for sample in samples), 3),
            "brake": round(median(sample["brake"] for sample in samples), 3),
            "accel": round(median(sample["accel"] for sample in samples), 2),
            "kind": kind, "confidence": round(votes[kind] / len(samples), 3),
            "votes": {value: votes.get(value, 0) for value in SECTION_META},
        }
        points.append(point)

    consensus_kinds = _merge_short_runs([point["kind"] for point in points], step_m, min_section_m)
    for point, kind in zip(points, consensus_kinds):
        point["kind"] = kind
        point["confidence"] = round(point["votes"].get(kind, 0) / len(analyses), 3)

    sections = []
    for number, run in enumerate(_runs(consensus_kinds), 1):
        group = points[run["start"]:run["end"] + 1]
        first, last = group[0], group[-1]
        sections.append({
            "number": number, "kind": run["kind"],
            "label": SECTION_META[run["kind"]]["label"],
            "color": SECTION_META[run["kind"]]["color"],
            "start_distance": first["s"], "end_distance": last["s"],
            "length_m": round(max(step_m, last["s"] - first["s"] + step_m), 1),
            "duration_ms": max(0, last["t"] - first["t"]),
            "entry_speed": first["speed"], "exit_speed": last["speed"],
            "min_speed": min(point["speed"] for point in group),
            "max_speed": max(point["speed"] for point in group),
            "speed_spread": round(max(point["speed_high"] - point["speed_low"] for point in group), 1),
            "average_throttle": round(median(point["throttle"] for point in group), 3),
            "average_brake": round(median(point["brake"] for point in group), 3),
            "confidence": round(sum(point["confidence"] for point in group) / len(group), 3),
            "minimum_confidence": min(point["confidence"] for point in group),
        })
    totals = {kind: round(sum(section["length_m"] for section in sections if section["kind"] == kind), 1)
              for kind in SECTION_META}
    source_laps = []
    for item in analyses:
        lap = item["lap"]
        source_laps.append({
            "id": item["id"], "session": str(item["id"]).split("/", 1)[0],
            "lap_number": lap.get("lapNumber"), "lap_time_ms": item["lap_time"],
            "gap_ms": round(item["lap_time"] - best_time),
            "gap_percent": round((item["lap_time"] / best_time - 1) * 100, 3),
            "tyre_compound": lap.get("tyreCompound"),
        })
    overall_confidence = sum(point["confidence"] for point in points) / len(points)
    return {
        "analyzable": True, "reason": None,
        "track_id": analyses[0]["lap"].get("trackId"),
        "track_length_m": reference["track_length_m"], "best_lap_time_ms": best_time,
        "compared_lap_count": len(analyses), "eligible_lap_count": len(eligible),
        "overall_confidence": round(overall_confidence, 3),
        "sample_quality": "high" if len(analyses) >= 5 else "medium" if len(analyses) >= 3 else "limited",
        "settings": {"step_m": step_m, "smoothing_m": smoothing_m,
                     "min_section_m": min_section_m, "braking_threshold": braking_threshold,
                     "flat_threshold": flat_threshold, "lift_threshold": lift_threshold,
                     "pace_window_percent": pace_window_percent, "max_laps": max_laps},
        "legend": SECTION_META, "totals_m": totals, "source_laps": source_laps,
        "points": points, "sections": sections,
    }
