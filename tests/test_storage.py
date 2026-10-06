import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from storage import LapStorage
import json

def lap(number, duration, valid=True):
    return {"lapNumber": number, "lapTimeMs": duration, "validLap": valid, "sampleCount": 20, "samples": []}

def identified_lap(number, track_id, setup=None):
    value = lap(number, 90000 - number)
    value.update({"sessionUid": 123, "trackId": track_id, "sessionType": 18,
                  "sessionTypeName": "Time Trial", "gameMode": 5,
                  "gameModeName": "Time Trial", "seasonLinkIdentifier": 40,
                  "weekendLinkIdentifier": 50, "sessionLinkIdentifier": 60})
    if setup is not None:
        value["_carSetup"] = setup
    return value

def test_best_lap_ignores_invalid(tmp_path):
    store=LapStorage(tmp_path); store.start_session({"trackId":1})
    store.save_lap(lap(1,90000)); store.save_lap(lap(2,80000,False))
    lap_id=next(item["id"] for item in store.list_laps() if item["lapNumber"] == 1)
    assert store.session_reference(lap_id)["lapNumber"] == 1

def test_safe_ids_and_missing_file(tmp_path):
    store=LapStorage(tmp_path)
    assert store.load_lap("missing.json") is None
    assert store.load_lap("../outside.json") is None

def test_lap_note_can_be_saved(tmp_path):
    store=LapStorage(tmp_path); store.start_session({"sessionUid":1})
    store.save_lap(lap(1,90000))
    lap_id=store.list_laps()[0]["id"]
    updated=store.update_lap_note(lap_id,"Turn 1: brake later")
    assert updated["note"] == "Turn 1: brake later"
    assert store.load_lap(lap_id)["note"] == "Turn 1: brake later"

def test_note_update_rejects_unsafe_id(tmp_path):
    assert LapStorage(tmp_path).update_lap_note("../outside.json", "no") is None


def test_replayed_lap_replaces_best_preserves_note_and_is_not_a_second_attempt(tmp_path):
    store = LapStorage(tmp_path)
    first = identified_lap(1, 12) | {"lapTimeMs": 80000, "recordingId": "record-a", "recordingRevision": 1}
    store.save_lap(first)
    store.save_lap(identified_lap(2, 12) | {"lapTimeMs": 85000, "recordingId": "record-b"})
    lap_id = next(item["id"] for item in store.list_laps() if item["lapNumber"] == 1)
    store.update_lap_note(lap_id, "Keep this note")
    store.save_lap(first | {"lapTimeMs": 90000, "recordingRevision": 2, "rewindCount": 1})
    assert len(store.list_laps()) == 2
    assert store.load_lap(lap_id)["note"] == "Keep this note"
    best = json.loads(next(tmp_path.rglob("best_lap.json")).read_text())
    assert best["lapNumber"] == 2
    backups = list(tmp_path.rglob("revision-*.json"))
    assert len(backups) == 1 and json.loads(backups[0].read_text())["lapTimeMs"] == 80000
    fresh = LapStorage(tmp_path)
    assert len(fresh.list_laps()) == 2  # Revision backups never enter navigation.
    assert next(item for item in fresh.list_laps() if item["lapNumber"] == 1)["rewindCount"] == 1


def test_replayed_invalid_lap_removes_obsolete_best_and_next_valid_lap_can_become_best(tmp_path):
    store = LapStorage(tmp_path)
    first = identified_lap(1, 12) | {"recordingId": "record-a", "recordingRevision": 1}
    store.save_lap(first)
    store.save_lap(first | {"validLap": False, "recordingRevision": 2})
    assert not list(tmp_path.rglob("best_lap.json"))
    store.save_lap(identified_lap(2, 12))
    assert json.loads(next(tmp_path.rglob("best_lap.json")).read_text())["lapNumber"] == 2


def test_distinct_same_number_attempts_are_not_overwritten(tmp_path):
    store = LapStorage(tmp_path)
    store.save_lap(identified_lap(1, 12) | {"recordingId": "attempt-a"})
    store.save_lap(identified_lap(1, 12) | {"recordingId": "attempt-b"})
    assert len(store.list_laps()) == 2

def test_lap_list_cache_is_invalidated_by_writes(tmp_path):
    store=LapStorage(tmp_path); store.start_session({"sessionUid":1})
    store.save_lap(lap(1,90000))
    calls=[]; original=store._lap_paths
    def counted_lap_paths():
        calls.append(1)
        return original()
    store._lap_paths=counted_lap_paths

    first=store.list_laps()
    assert [item["lapNumber"] for item in store.list_laps()] == [1]
    assert first is not store.list_laps()
    assert len(calls) == 1

    store.save_lap(lap(2,88000))
    assert sorted(item["lapNumber"] for item in store.list_laps()) == [1,2]
    assert len(calls) == 2


def test_navigation_index_reuses_metadata_across_process_instances(tmp_path, monkeypatch):
    store = LapStorage(tmp_path)
    store.save_lap(identified_lap(1, 11))
    store.save_lap(identified_lap(2, 11))
    expected = store.hierarchy()
    reads, original = [], Path.read_text
    def counted(path, *args, **kwargs):
        if path.name.startswith("lap_"):
            reads.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", counted)
    fresh = LapStorage(tmp_path)
    assert fresh.hierarchy() == expected
    assert reads == []  # No full telemetry decoding to populate navigation.
    assert "samples" not in json.loads((tmp_path / ".navigation-index.json").read_text())["entries"][expected[0]["tracks"][0]["laps"][0]["id"]]["metadata"]


def test_navigation_index_refreshes_only_changed_added_and_removed_files(tmp_path, monkeypatch):
    store = LapStorage(tmp_path)
    store.save_lap(identified_lap(1, 11))
    store.save_lap(identified_lap(2, 11))
    initial = {item["lapNumber"]: item for item in store.list_laps()}
    path = tmp_path / initial[1]["id"]
    value = json.loads(path.read_text())
    value["note"] = "Externally updated note"
    path.write_text(json.dumps(value), encoding="utf-8")
    (tmp_path / initial[2]["id"]).unlink()
    store.save_lap(identified_lap(3, 11))
    reads, original = [], Path.read_text
    def counted(path, *args, **kwargs):
        if path.name.startswith("lap_"):
            reads.append(path.name)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", counted)
    fresh = LapStorage(tmp_path)
    listed = {item["lapNumber"]: item for item in fresh.list_laps()}
    assert set(listed) == {1, 3}
    assert listed[1]["note"] == "Externally updated note"
    assert sorted(reads) == ["lap_001.json", "lap_003.json"]
    reads.clear()
    value["note"] = "Changed again"
    path.write_text(json.dumps(value), encoding="utf-8")
    assert next(item for item in fresh.list_laps(refresh=True) if item["lapNumber"] == 1)["note"] == "Changed again"
    assert reads == ["lap_001.json"]
    index = json.loads((tmp_path / ".navigation-index.json").read_text())
    assert initial[2]["id"] not in index["entries"]


def test_navigation_index_is_rebuildable_and_cache_write_failure_is_optional(tmp_path, monkeypatch):
    store = LapStorage(tmp_path)
    store.save_lap(identified_lap(1, 11))
    expected = store.list_laps()
    index = tmp_path / ".navigation-index.json"
    for bad in ("invalid json", json.dumps({"version": 999, "entries": {}}),
                json.dumps({"version": 1, "entries": {expected[0]["id"]: {"metadata": []}}})):
        index.write_text(bad, encoding="utf-8")
        assert LapStorage(tmp_path).list_laps() == expected
    index.unlink()
    import storage as module
    def denied(*args, **kwargs):
        raise PermissionError("read-only cache directory")
    monkeypatch.setattr(module.tempfile, "NamedTemporaryFile", denied)
    assert LapStorage(tmp_path).list_laps() == expected


def test_note_and_new_lap_survive_restart_without_reparsing_unchanged_laps(tmp_path):
    store = LapStorage(tmp_path)
    store.save_lap(identified_lap(1, 11))
    lap_id = store.list_laps()[0]["id"]
    store.update_lap_note(lap_id, "New note")
    store.save_lap(identified_lap(2, 11))
    expected = store.list_laps()
    assert LapStorage(tmp_path).list_laps() == expected
    assert next(item for item in expected if item["id"] == lap_id)["note"] == "New note"

def test_track_corner_profile_is_shared_outside_session_results(tmp_path):
    store = LapStorage(tmp_path)
    profile = {"track_id": "9", "track_length_m": 4381.0,
               "corners": [{"label": "T1", "start_distance": 570.0,
                            "apex_distance": 625.0, "end_distance": 690.0}]}
    store.save_track_profile(9, profile)
    assert store.load_track_profile("9") == profile
    assert store.track_profile_path(9).parent.name == "_track_profiles"

def test_same_uid_is_split_when_track_changes(tmp_path):
    store = LapStorage(tmp_path)
    store.save_lap(identified_lap(1, 11))
    first_session = store.session_dir
    store.save_lap(identified_lap(1, 12))
    assert store.session_dir != first_session
    assert len([path for path in tmp_path.iterdir() if path.is_dir() and path.name != "_track_profiles"]) == 2
    metadata = __import__("json").loads((store.session_dir / "session.json").read_text(encoding="utf-8"))
    assert metadata["sessionUid"] == 123
    assert metadata["sessionUidHex"] == "000000000000007b"
    assert metadata["trackId"] == 12
    assert metadata["sessionTypeName"] == "Time Trial"
    assert metadata["gameModeName"] == "Time Trial"
    assert metadata["sessionLinkIdentifier"] == 60

def test_session_link_change_splits_same_uid_and_track(tmp_path):
    store = LapStorage(tmp_path)
    first = identified_lap(1, 11)
    store.save_lap(first)
    first_session = store.session_dir
    second = identified_lap(1, 11)
    second["sessionLinkIdentifier"] = 61
    store.save_lap(second)
    assert store.session_dir != first_session


def test_session_type_change_splits_same_uid_track_and_link(tmp_path):
    store = LapStorage(tmp_path)
    practice = identified_lap(1, 11)
    practice.update(sessionType=1, sessionTypeName="Practice 1", gameMode=4, gameModeName="Grand Prix '23")
    store.save_lap(practice)
    first_session = store.session_dir
    qualifying = practice | {"sessionType": 5, "sessionTypeName": "Qualifying 1"}
    store.save_lap(qualifying)
    assert store.session_dir != first_session
    assert {x["sessionActivityName"] for x in store.hierarchy()} == {"Practice 1", "Qualifying 1"}
    assert {x["sessionActivityName"] for x in store.list_laps()} == {"Practice 1", "Qualifying 1"}


def test_legacy_folder_displays_all_recorded_stages_over_stale_metadata(tmp_path):
    store = LapStorage(tmp_path)
    value = identified_lap(1, 11)
    store.save_lap(value)
    path = next(store.session_dir.glob("track-*/laps/lap_*.json"))
    # Simulate an old mixed folder whose parent still says Time Trial.
    store._write(path, value | {"sessionType": 1})
    store._write(path.with_name("lap_002.json"), value | {"sessionType": 15, "lapNumber": 2})
    session = store.hierarchy()[0]
    assert set(session["sessionTypes"]) == {1, 15}
    assert set(session["sessionActivityName"].split(" / ")) == {"Practice 1", "Race"}
    assert session["id"] == store.session_dir.name

def test_car_setup_is_deduplicated_and_laps_store_only_reference(tmp_path):
    store = LapStorage(tmp_path)
    setup = {"onThrottleDifferential": 75, "brakeBias": 57}
    store.save_lap(identified_lap(1, 11, setup))
    store.save_lap(identified_lap(2, 11, setup))
    setup_files = list(store.session_dir.glob("track-*/setups/setup-*.json"))
    assert len(setup_files) == 1
    saved_laps = [value for _, value in store.session_track_laps(store.session_dir.name, 11)]
    assert saved_laps[0]["setupId"] == saved_laps[1]["setupId"]
    assert all("_carSetup" not in value and "carSetup" not in value for value in saved_laps)
    assert all("gameModeName" not in value and "sessionLinkIdentifier" not in value for value in saved_laps)
    session = store.hierarchy()[0]
    assert session["gameModeName"] == "Time Trial"
    assert session["sessionTypeName"] == "Time Trial"
    assert session["sessionLinkIdentifier"] == 60
