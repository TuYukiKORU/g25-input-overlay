import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from workspace_insights import consistency, stints, wear_estimate, setup_changes
from recording_health import RecordingHealth
from storage import LapStorage
from analysis_freshness import source_signature, freshness
from analysis_worker import AnalysisWorker


def lap(n=1, wear=5, fuel=10, time=10000):
    return {"sessionUid": 123, "trackId": 7, "lapNumber": n, "validLap": True,
            "lapTimeMs": time, "tyreCompound": "Soft", "setupId": "a" * 12,
            "fuelInTankKgAtStart": fuel, "tyreAgeLapsAtStart": n,
            "tyreWearAtStart": {"front_left": wear}, "tyreWearAtEnd": {"front_left": wear + 1},
            "samples": [{"lap_distance": d, "lap_time_ms": d * time / 200, "speed": 100 + n,
                         "ers_percent": 80, "throttle": 0 if d < 110 + n * 5 else .8,
                         "brake": 0 if d < 20 + n * 5 else .8} for d in range(0, 205, 5)]}


def test_consistency_filters_unknown_conditions_and_measures_onset_ranges():
    entries = [(str(n), lap(n, wear=5)) for n in (1, 2, 3)]
    unknown = lap(4); unknown.pop("setupId")
    invalid = lap(5); invalid["validLap"] = False
    entries += [("unknown", unknown), ("invalid", invalid), ("fuel", lap(6, fuel=80))]
    profile = {"corners": [{"label": "T1", "start_distance": 10, "apex_distance": 100, "end_distance": 190}]}
    result = consistency(entries, entries[0][1], profile)
    assert result["eligible_laps"] == 3
    assert result["rows"][0]["brake_m_range"] == 10
    assert result["rows"][0]["throttle_m_range"] == 10
    assert result["rows"][0]["lap_count"] == 3


def test_consistency_requires_three_uninterrupted_laps():
    a, b, c = lap(1), lap(2), lap(3)
    c["samples"] = [s for s in c["samples"] if s["lap_distance"] < 50 or s["lap_distance"] > 150]
    profile = {"corners": [{"label": "T1", "start_distance": 10, "apex_distance": 100, "end_distance": 190}]}
    result = consistency([("a", a), ("b", b), ("c", c)], a, profile)
    assert result["rows"] == []
    assert result["reason"]


def test_stints_split_at_resets_and_keep_invalid_laps_identified():
    a, b, c = lap(1, wear=20), lap(2, wear=22), lap(3, wear=0)
    b["validLap"] = False
    c["tyreAgeLapsAtStart"] = 0
    result = stints([("c", c), ("a", a), ("b", b)])
    assert len(result) == 2
    assert result[0]["laps"][1]["eligible"] is False
    assert "reset" in result[1]["reason"]


def test_stint_boundary_after_pit_is_explicitly_unconfirmed():
    a, b, c = lap(1), lap(2), lap(3)
    b["pitLaneUsed"] = True
    result = stints([("a", a), ("b", b), ("c", c)])
    assert len(result) == 2
    assert "unconfirmed" in result[1]["reason"]


def test_wear_estimate_does_not_fit_unmatched_fuel_or_unknown_setup():
    a = lap(1, wear=5)
    rows = [("a", a), ("b", lap(2, wear=10, fuel=20)), ("c", lap(3, wear=15, fuel=30))]
    assert wear_estimate(rows, a)["estimated_loss_ms"] is None
    for _, value in rows:
        value.pop("setupId")
    assert wear_estimate(rows, a)["sample_count"] == 0


def test_wear_estimate_uses_matched_pairs_and_reports_association():
    rows = [(str(n), lap(n, wear=5 + n * 3, time=10000 + n * 300)) for n in (1, 2, 3)]
    result = wear_estimate(rows, rows[0][1])
    assert result["sample_count"] == 3
    assert result["pair_count"] == 3
    assert result["ms_per_wear_percent"] == 100
    assert result["estimated_loss_ms"] == 100
    assert "association" in result["reason"]


def test_negative_wear_relationship_is_not_a_fake_positive_penalty():
    rows = [(str(n), lap(n, wear=5 + n * 3, time=10000 - n * 300)) for n in (1, 2, 3)]
    assert wear_estimate(rows, rows[0][1])["estimated_loss_ms"] is None


def test_health_ages_and_resets_per_session():
    now = [0]
    health = RecordingHealth(lambda: now[0])
    assert health.snapshot()["state"] == "waiting"
    health.received(6, 1)
    assert health.snapshot()["state"] == "receiving"
    now[0] = 4
    assert health.snapshot()["state"] == "stale"
    health.received(2, 2)
    groups = {row["packet_id"]: row for row in health.snapshot()["groups"]}
    assert groups[6]["state"] == "missing"
    assert groups[2]["state"] == "receiving"
    assert 16 not in groups
    assert any(row["packet_id"] == 16 for row in health.snapshot(True)["groups"])


def test_setup_snapshots_are_scoped_and_differences_readable(tmp_path):
    store = LapStorage(tmp_path)
    value = lap(); value.pop("setupId"); value["_carSetup"] = {"frontWing": 20, "brakeBias": 55}
    store.save_lap(value)
    lap_id = store.list_laps()[0]["id"]
    setup = store.load_lap_setup(lap_id)
    assert setup["frontWing"] == 20
    assert store.load_lap_setup("../outside.json") is None
    assert setup_changes(setup, dict(setup, frontWing=25))["rows"] == [{"field": "frontWing", "selected": 20, "comparison": 25}]
    assert setup_changes(None, setup)["available"] is False


def test_freshness_detects_new_lap_and_replaced_sample_data(tmp_path):
    store = LapStorage(tmp_path)
    store.save_lap(lap())
    session = store.session_dir.name
    signature = source_signature(store, 7, session)
    result = {"source_signature": signature}
    assert freshness(store, result, 7, session)["stale"] is False
    store.save_lap(lap(2))
    assert freshness(store, result, 7, session)["stale"] is True
    lap_id = store.list_laps()[0]["id"]
    result["source_signature"] = source_signature(store, 7, session)
    value = store.load_lap(lap_id); value["samples"][0]["speed"] = 12345
    store._write(store.root / lap_id, value)
    assert freshness(store, result, 7, session)["stale"] is True


def test_saved_session_cannot_be_reused_for_different_selected_lap(tmp_path, monkeypatch):
    store = LapStorage(tmp_path)
    store.save_lap(lap())
    session = store.session_dir.name
    store.save_session_analysis(session, 7, {"source_signature": source_signature(store, 7, session),
                                            "requested_lap_id": "a", "requested_settings": {}, "requested_definition": None})
    worker = AnalysisWorker(store)
    # Leave the job queued; this test checks reuse before any analysis runs.
    monkeypatch.setattr(worker._queue, "put", lambda task: None)
    _, started = worker.start(session, 7, "a")
    assert not started
    _, started = worker.start(session, 7, "b")
    assert started


def test_freshness_detects_external_lap_setup_and_profile_changes(tmp_path):
    import json
    store = LapStorage(tmp_path)
    value = lap(); value.pop("setupId"); value["_carSetup"] = {"frontWing": 20}
    store.save_lap(value)
    session = store.session_dir.name
    result = {"source_signature": source_signature(store, 7, session), "reason": "Original analysis reason"}
    saved_id = store.list_laps()[0]["id"]
    external = dict(value, lapNumber=2)
    (store.root / saved_id).with_name("lap_002.json").write_text(json.dumps(external))
    assert freshness(store, result, 7, session)["stale"]
    assert len(store.list_laps()) == 2
    result["source_signature"] = source_signature(store, 7, session)
    setup_path = next(store.root.rglob("setup-*.json"))
    setup_path.write_text(json.dumps({"frontWing": 25}))
    assert freshness(store, result, 7, session)["stale"]
    result["source_signature"] = source_signature(store, 7, session)
    store.save_track_profile(7, {"corners": [], "track_length_m": 200})
    assert freshness(store, result, 7, session)["stale"]
    assert (result | freshness(store, result, 7, session))["reason"] == "Original analysis reason"


def test_workspace_api_is_session_scoped_and_setup_comparison_checks_track(tmp_path, monkeypatch):
    import app as app_module
    store = LapStorage(tmp_path)
    monkeypatch.setattr(app_module, "storage", store)
    for n in (1, 2, 3):
        value = lap(n); value.pop("setupId"); value["_carSetup"] = {"frontWing": 20}
        store.save_lap(value)
    ids = [item["id"] for item in store.list_laps()]
    client = app_module.app.test_client()
    response = client.get(f"/api/laps/{ids[0]}/workspace-insights")
    assert response.status_code == 200
    body = response.get_json()
    assert body["consistency"]["eligible_laps"] == 3
    assert len(body["stints"][0]["laps"]) == 3
    assert client.get(f"/api/laps/{ids[0]}/setup-comparison", query_string={"reference_id": ids[1]}).get_json()["available"]
    wrong_track = lap(4); wrong_track["trackId"] = 8
    store.save_lap(wrong_track)
    other = next(item["id"] for item in store.list_laps() if item["trackId"] == 8)
    assert client.get(f"/api/laps/{ids[0]}/setup-comparison", query_string={"reference_id": other}).status_code == 400
    assert client.get("/api/laps/missing/workspace-insights").status_code == 404


def test_udp_health_ignores_truncated_groups_and_tracks_decoded_controls(monkeypatch):
    import copy
    import struct
    import pytest
    import telemetry
    from state import latest

    def packet(packet_id, size):
        data = bytearray(telemetry.HEADER_SIZE + size)
        struct.pack_into("<H", data, 0, 2025)
        data[2] = 25; data[6] = packet_id
        struct.pack_into("<Q", data, 7, 123)
        return data

    packets = iter([packet(1, telemetry.SESSION_LINK_OFFSET + 4),
                    packet(0, 12), packet(6, 2),
                    packet(6, 60)])  # A complete 2025 player record, not just its prefix.

    class FakeSocket:
        def bind(self, address):
            pass

        def recvfrom(self, size):
            return next(packets), ("127.0.0.1", 1)

    health = RecordingHealth(lambda: 1)
    monkeypatch.setattr(telemetry.socket, "socket", lambda *args: FakeSocket())
    monkeypatch.setattr(telemetry, "recording_health", health)
    with pytest.raises(StopIteration):
        telemetry.udp_loop(copy.deepcopy(latest))
    states = {group["packet_id"]: group["state"] for group in health.snapshot()["groups"]}
    assert states[6] == "receiving"
    assert states[0] == states[1] == "missing"
