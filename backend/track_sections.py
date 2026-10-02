"""Experimental curvature-based track corner segmentation."""
from bisect import bisect_left
from math import sqrt


def _number(value, default=None):
    try:
        value = float(value)
        return value if value == value else default
    except (TypeError, ValueError):
        return default


def _raw_line(lap):
    rows = []
    for sample in lap.get("samples", []):
        position = sample.get("position") or {}
        s = _number(sample.get("lap_distance"))
        x, z = _number(position.get("x")), _number(position.get("z"))
        if s is not None and x is not None and z is not None:
            rows.append((s, x, z))
    rows.sort(key=lambda row: row[0])
    unique = []
    for row in rows:
        if not unique or row[0] > unique[-1][0] + .01:
            unique.append(row)
    return unique


def _course_rotation(rows):
    """Return the course winding in the same X/Z orientation used by the map.

    Corner direction is deliberately not derived from this value. A circuit
    can contain both left and right turns; each turn is classified from the
    ordered trajectory in the car's direction of travel.
    """
    if len(rows) < 3:
        return "unknown"
    area_twice = 0.0
    for current, following in zip(rows, rows[1:] + rows[:1]):
        area_twice += current[1] * following[2] - following[1] * current[2]
    span_x = max(row[1] for row in rows) - min(row[1] for row in rows)
    span_z = max(row[2] for row in rows) - min(row[2] for row in rows)
    if abs(area_twice) < max(1.0, span_x * span_z * .01):
        return "unknown"
    # The browser map draws +Z downwards, so positive shoelace area is a
    # clockwise path as displayed.
    return "clockwise" if area_twice > 0 else "counterclockwise"


def _interpolate(rows, distance):
    distances = [row[0] for row in rows]
    index = bisect_left(distances, distance)
    if index <= 0:
        return rows[0][1], rows[0][2]
    if index >= len(rows):
        return rows[-1][1], rows[-1][2]
    before, after = rows[index - 1], rows[index]
    ratio = (distance - before[0]) / max(after[0] - before[0], 1e-9)
    return (before[1] + (after[1] - before[1]) * ratio,
            before[2] + (after[2] - before[2]) * ratio)


def _moving_average(values, radius):
    if radius <= 0:
        return values[:]
    prefix = [0.0]
    for value in values:
        prefix.append(prefix[-1] + value)
    result = []
    for index in range(len(values)):
        start, end = max(0, index - radius), min(len(values), index + radius + 1)
        result.append((prefix[end] - prefix[start]) / (end - start))
    return result


def _curvature(a, b, c):
    """Signed Menger curvature through three points, in 1/metre."""
    ab = sqrt((b["x"] - a["x"]) ** 2 + (b["z"] - a["z"]) ** 2)
    bc = sqrt((c["x"] - b["x"]) ** 2 + (c["z"] - b["z"]) ** 2)
    ac = sqrt((c["x"] - a["x"]) ** 2 + (c["z"] - a["z"]) ** 2)
    denominator = ab * bc * ac
    if denominator < 1e-8:
        return 0.0
    cross = ((b["x"] - a["x"]) * (c["z"] - a["z"])
             - (b["z"] - a["z"]) * (c["x"] - a["x"]))
    return 2.0 * cross / denominator


def _corner_groups(points, threshold, min_length_m):
    groups, active = [], None
    for index, point in enumerate(points):
        above = point["curvature_abs"] >= threshold
        if above and active is None:
            active = [index, index]
        elif above:
            active[1] = index
        elif active is not None:
            groups.append(active); active = None
    if active is not None:
        groups.append(active)

    corners = []
    for start_index, end_index in groups:
        start, end = points[start_index]["s"], points[end_index]["s"]
        if end - start < min_length_m:
            continue
        peak_index = max(range(start_index, end_index + 1), key=lambda index: points[index]["curvature_abs"])
        peak = points[peak_index]
        corners.append({
            "label": f"T{len(corners) + 1}", "start_distance": round(start, 1),
            "end_distance": round(end, 1), "apex_distance": round(peak["s"], 1),
            "peak_curvature": round(peak["curvature_abs"], 6),
            # F1 world coordinates use the opposite handedness from the
            # conventional X/Y plotting plane: positive X/Z curvature is a
            # right-hand turn in the car's direction of travel.
            "direction": "right" if peak["curvature"] > 0 else "left",
            "radius_m": round(1.0 / peak["curvature_abs"], 1) if peak["curvature_abs"] > 1e-9 else None,
        })
    return corners


def identify_chicanes(corners, max_transition_m=40.0, max_total_m=350.0):
    """Group closely spaced alternating turns while preserving individual T labels."""
    chicanes = []
    index = 0
    while index < len(corners) - 1:
        members = [corners[index]]
        cursor = index
        while cursor + 1 < len(corners):
            current, following = corners[cursor], corners[cursor + 1]
            transition = following["start_distance"] - current["end_distance"]
            total = following["end_distance"] - members[0]["start_distance"]
            if (current["direction"] == following["direction"]
                    or transition > max_transition_m or total > max_total_m):
                break
            members.append(following)
            cursor += 1
        if len(members) >= 2:
            chicane_id = f"C{len(chicanes) + 1}"
            for member in members:
                member["complex_type"] = "chicane"
                member["complex_id"] = chicane_id
            chicanes.append({
                "id": chicane_id, "type": "chicane",
                "label": f"{members[0]['label']}–{members[-1]['label']}",
                "turn_labels": [member["label"] for member in members],
                "directions": [member["direction"] for member in members],
                "start_distance": members[0]["start_distance"],
                "end_distance": members[-1]["end_distance"],
                "transition_gap_m": round(max(
                    members[position + 1]["start_distance"] - members[position]["end_distance"]
                    for position in range(len(members) - 1)), 1),
            })
            index = cursor + 1
        else:
            index += 1
    return chicanes


def analyze_track_sections(lap, threshold=.0066, smoothing_m=20.0,
                           min_length_m=15.0, step_m=5.0):
    """Return a smoothed reference line, curvature samples, and T1..Tn labels."""
    rows = _raw_line(lap)
    if len(rows) < 20:
        return {"analyzable": False, "reason": "XYZ座標を持つサンプルが不足しています", "points": [], "corners": [], "chicanes": []}
    start, finish = max(0.0, rows[0][0]), rows[-1][0]
    if finish - start < 500:
        return {"analyzable": False, "reason": "コース全体を構成できる距離データがありません", "points": [], "corners": [], "chicanes": []}
    distances = []
    distance = start
    while distance <= finish:
        distances.append(distance); distance += step_m
    coordinates = [_interpolate(rows, distance) for distance in distances]
    smooth_radius = max(0, round(smoothing_m / step_m / 2))
    xs = _moving_average([coordinate[0] for coordinate in coordinates], smooth_radius)
    zs = _moving_average([coordinate[1] for coordinate in coordinates], smooth_radius)
    points = [{"s": distance, "x": x, "z": z} for distance, x, z in zip(distances, xs, zs)]

    derivative_span = max(1, round(10.0 / step_m))
    raw_curvature = []
    for index in range(len(points)):
        before = points[max(0, index - derivative_span)]
        after = points[min(len(points) - 1, index + derivative_span)]
        raw_curvature.append(_curvature(before, points[index], after))
    curvature_radius = max(1, round(smoothing_m / step_m / 2))
    # Smooth the signed signal. At a left/right transition it must pass through
    # zero, allowing the two lobes of a chicane to become separate turns.
    signed = _moving_average(raw_curvature, curvature_radius)
    for point, curvature in zip(points, signed):
        point["curvature"] = round(curvature, 7)
        point["curvature_abs"] = round(abs(curvature), 7)
        point["is_straight"] = abs(curvature) < threshold
        point["s"] = round(point["s"], 1)
        point["x"] = round(point["x"], 3); point["z"] = round(point["z"], 3)
    corners = _corner_groups(points, threshold, min_length_m)
    chicanes = identify_chicanes(corners)
    return {
        "analyzable": True, "reason": None, "track_length_m": round(finish, 1),
        "course_rotation": _course_rotation(rows),
        "corner_direction_basis": "vehicle_travel_direction",
        "source_lap_number": lap.get("lapNumber"), "sample_count": len(points),
        "settings": {"threshold": threshold, "smoothing_m": smoothing_m,
                     "min_length_m": min_length_m, "step_m": step_m},
        "points": points, "corners": corners, "chicanes": chicanes,
    }
