import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from storage import LapStorage

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
