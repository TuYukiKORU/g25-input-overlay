import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from track_sections import analyze_track_sections


def lap_from_points(points):
    samples = [{"lap_distance": distance, "position": {"x": x, "y": 0, "z": z}}
               for distance, x, z in points]
    return {"lapNumber": 4, "samples": samples}


def synthetic_two_corner_lap():
    points, distance = [], 0.0
    for x in range(0, 201, 5):
        points.append((distance, x, 0)); distance += 5
    for degree in range(-90, 1, 5):
        angle = math.radians(degree)
        points.append((distance, 200 + 50 * math.cos(angle), 50 + 50 * math.sin(angle)))
        distance += math.radians(5) * 50
    for z in range(55, 251, 5):
        points.append((distance, 250, z)); distance += 5
    for degree in range(180, 89, -5):
        angle = math.radians(degree)
        points.append((distance, 300 + 50 * math.cos(angle), 250 + 50 * math.sin(angle)))
        distance += math.radians(5) * 50
    for x in range(305, 551, 5):
        points.append((distance, x, 300)); distance += 5
    return lap_from_points(points)


def synthetic_chicane_lap():
    points, distance = [], 0.0
    for x in range(0, 201, 5):
        points.append((distance, x, 0)); distance += 5
    for degree in range(-90, 1, 5):
        angle = math.radians(degree)
        points.append((distance, 200 + 50 * math.cos(angle), 50 + 50 * math.sin(angle)))
        distance += math.radians(5) * 50
    for degree in range(180, 89, -5):
        angle = math.radians(degree)
        points.append((distance, 300 + 50 * math.cos(angle), 50 + 50 * math.sin(angle)))
        distance += math.radians(5) * 50
    for x in range(305, 901, 5):
        points.append((distance, x, 100)); distance += 5
    return lap_from_points(points)


def test_curvature_mountains_become_numbered_corners():
    result = analyze_track_sections(synthetic_two_corner_lap(), threshold=.008,
                                    smoothing_m=10, min_length_m=15)
    assert result["analyzable"] is True
    assert [corner["label"] for corner in result["corners"]] == ["T1", "T2"]
    assert [corner["direction"] for corner in result["corners"]] == ["right", "left"]
    assert all(35 <= corner["radius_m"] <= 80 for corner in result["corners"])


def test_straight_line_gets_no_label():
    points = [(distance, distance, 0) for distance in range(0, 1001, 5)]
    result = analyze_track_sections(lap_from_points(points), threshold=.001,
                                    smoothing_m=10, min_length_m=10)
    assert result["analyzable"] is True
    assert result["corners"] == []


def test_opposite_curvature_lobes_are_split_and_linked_as_chicane():
    result = analyze_track_sections(synthetic_chicane_lap(), threshold=.0061,
                                    smoothing_m=15, min_length_m=10)
    assert [corner["label"] for corner in result["corners"]] == ["T1", "T2"]
    assert [corner["direction"] for corner in result["corners"]] == ["right", "left"]
    assert result["chicanes"] == [{
        "id": "C1", "type": "chicane", "label": "T1–T2",
        "turn_labels": ["T1", "T2"], "directions": ["right", "left"],
        "start_distance": result["corners"][0]["start_distance"],
        "end_distance": result["corners"][1]["end_distance"],
        "transition_gap_m": result["chicanes"][0]["transition_gap_m"],
    }]


def test_missing_positions_returns_explicit_reason():
    result = analyze_track_sections({"samples": [{"lap_distance": index * 5} for index in range(100)]})
    assert result["analyzable"] is False
    assert "XYZ" in result["reason"]
