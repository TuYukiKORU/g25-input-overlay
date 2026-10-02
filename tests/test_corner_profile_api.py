import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import app as app_module
from storage import LapStorage


def test_manual_profile_is_renumbered_and_chicanes_are_rebuilt(tmp_path, monkeypatch):
    store = LapStorage(tmp_path)
    monkeypatch.setattr(app_module, "storage", store)
    client = app_module.app.test_client()
    response = client.put("/api/tracks/9/corner-profile", json={
        "track_length_m": 4300,
        "settings": {"threshold": .0066, "smoothing_m": 20, "min_length_m": 15},
        "corners": [
            {"label": "wrong", "start_distance": 100, "apex_distance": 130,
             "end_distance": 160, "direction": "left"},
            {"label": "wrong", "start_distance": 180, "apex_distance": 210,
             "end_distance": 240, "direction": "right"},
        ],
    })
    assert response.status_code == 200
    profile = response.get_json()
    assert [corner["label"] for corner in profile["corners"]] == ["T1", "T2"]
    assert [corner["complex_id"] for corner in profile["corners"]] == ["C1", "C1"]
    assert profile["chicanes"][0]["turn_labels"] == ["T1", "T2"]
    assert client.get("/api/tracks/9/corner-profile").get_json()["corners"] == profile["corners"]
    listed = client.get("/api/track-corner-profiles").get_json()
    assert [(item["track_id"], item["track_name"]) for item in listed] == [("9", "Hungaroring")]


def test_manual_profile_rejects_overlapping_corners(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "storage", LapStorage(tmp_path))
    response = app_module.app.test_client().put("/api/tracks/9/corner-profile", json={
        "track_length_m": 4300,
        "corners": [
            {"start_distance": 100, "apex_distance": 140, "end_distance": 180},
            {"start_distance": 170, "apex_distance": 200, "end_distance": 230},
        ],
    })
    assert response.status_code == 400
    assert "overlapping" in response.get_json()["error"]


def test_three_tab_pages_are_available():
    client = app_module.app.test_client()
    assert client.get("/analysis").status_code == 200
    assert client.get("/session-analysis").status_code == 200
    assert client.get("/map-corners").status_code == 200
