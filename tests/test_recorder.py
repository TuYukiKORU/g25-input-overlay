import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from lap_recorder import LapRecorder

class MemoryStorage:
    def __init__(self): self.laps=[]
    def save_lap(self, lap): self.laps.append(lap)

def state(lap, distance, time_ms):
    return {"lap_number":lap,"lap_distance":distance,"current_lap_time_ms":time_ms,"last_lap_time_ms":time_ms,
            "session_uid":1,"track_id":0,"packet_format":2025,"game_version":"F1 25","session_type":1,"speed":100,"throttle_raw":.5,
            "brake_raw":0,"tyres_wear":[1,1,1,1],"wheel_speed":[1]*4,"wheel_slip_ratio":[0]*4}

def test_distance_sampling_and_lap_switch():
    storage=MemoryStorage(); rec=LapRecorder(storage)
    for distance in range(0, 2100, 100): rec.observe(state(1,distance,distance * 20))
    assert len(rec.current["samples"]) == 21
    rec.observe(state(2,0,1000)); rec._queue.join()
    assert storage.laps[0]["lapNumber"] == 1


def test_session_type_transition_does_not_mix_samples_with_same_uid_and_lap_number():
    storage = MemoryStorage()
    rec = LapRecorder(storage)
    for distance in range(0, 2100, 100):
        rec.observe(state(1, distance, distance * 20))
    qualifying = state(1, 0, 0) | {"session_type": 5}
    rec.observe(qualifying)
    assert rec.current["sessionType"] == 5
    assert [s["lap_distance"] for s in rec.current["samples"]] == [0]
    assert rec.flush() and storage.laps == []

def test_longitudinal_g_is_saved_with_samples():
    rec=LapRecorder(MemoryStorage()); value=state(1,0,0); value["longitudinal_g"] = .85
    rec.observe(value)
    assert rec.current["samples"][0]["longitudinal_g"] == .85

def test_backward_distance_without_clock_rollback_abandons_attempt():
    rec=LapRecorder(MemoryStorage()); rec.observe(state(1,200,100)); rec.observe(state(1,20,120))
    assert rec.current["samples"][0]["lap_distance"] == 20

def test_same_number_start_line_crossing_finishes_attempt():
    storage=MemoryStorage(); rec=LapRecorder(storage)
    for distance in range(0, 2100, 100): rec.observe(state(1,distance,distance * 20))
    rec.observe(state(1,10,20))
    rec._queue.join()
    assert storage.laps[0]["lapNumber"] == 1
    assert rec.current["samples"][0]["lap_distance"] == 10

def test_paused_state_does_not_add_samples():
    rec=LapRecorder(MemoryStorage()); value=state(1,0,0); value["paused"] = True
    rec.observe(value)
    assert rec.current is None

def test_partial_lap_started_away_from_line_is_not_saved():
    storage=MemoryStorage(); rec=LapRecorder(storage)
    for distance in range(3000, 5100, 100): rec.observe(state(1,distance,distance * 20))
    rec.observe(state(2,0,1000)); rec._queue.join()
    assert storage.laps == []

def test_f1_25_drs_is_not_saved_as_active_aero():
    storage=MemoryStorage(); rec=LapRecorder(storage)
    for distance in range(0, 2100, 100):
        value = state(1,distance,distance * 20)
        value["drs"] = int(300 <= distance <= 600 or 1300 <= distance <= 1600)
        rec.observe(value)
    rec.observe(state(2,0,1000)); rec._queue.join()
    assert storage.laps[0]["activeAeroUses"] == 0
    assert not any(sample["active_aero"] for sample in storage.laps[0]["samples"])
    assert any(sample["drs"] for sample in storage.laps[0]["samples"])

def test_udp_mode_is_saved_with_lap():
    storage=MemoryStorage(); rec=LapRecorder(storage)
    for distance in range(0, 2100, 100):
        value=state(1,distance,distance * 20); value["packet_format"]=2026; value["game_version"]="F1 26"; rec.observe(value)
    value=state(2,0,1000); value["packet_format"]=2026; value["game_version"]="F1 26"; rec.observe(value); rec._queue.join()
    assert storage.laps[0]["gameVersion"] == "F1 26"
    assert storage.laps[0]["udpMode"] == "2026 Season Pack"

def test_game_year_26_is_saved_as_season_pack_metadata():
    storage=MemoryStorage(); rec=LapRecorder(storage)
    for distance in range(0, 2100, 100):
        value=state(1,distance,distance * 20); value["game_year"]=26; value["game_version"]="F1 26"; rec.observe(value)
    value=state(2,0,1000); value["game_year"]=26; value["game_version"]="F1 26"; rec.observe(value); rec._queue.join()
    assert storage.laps[0]["gameYear"] == 26
    assert storage.laps[0]["udpMode"] == "2026 Season Pack"

def test_pit_entry_is_saved_and_counted():
    storage=MemoryStorage(); rec=LapRecorder(storage)
    for distance in range(0, 2100, 100):
        value=state(1,distance,distance * 20); value["pit_status"] = 1 if 1500 <= distance <= 1900 else 0; rec.observe(value)
    rec.observe(state(2,0,1000)); rec._queue.join()
    assert storage.laps[0]["pitEntryCount"] == 1
    assert storage.laps[0]["pitLaneUsed"] is True
    assert any(sample["pit_status"] for sample in storage.laps[0]["samples"])

def test_ers_usage_is_saved_and_counted():
    storage=MemoryStorage(); rec=LapRecorder(storage)
    for distance in range(0, 2100, 100):
        value=state(1,distance,distance * 20); value["ers"] = int(500 <= distance <= 900 or 1500 <= distance <= 1800); value["ers_mode"] = 3 if value["ers"] else 0; rec.observe(value)
    rec.observe(state(2,0,1000)); rec._queue.join()
    assert storage.laps[0]["ersUsageCount"] == 2
    assert any(sample["ers_usage"] for sample in storage.laps[0]["samples"])

def test_f1_25_medium_and_hotlap_are_not_counted_as_overtake_usage():
    storage=MemoryStorage(); rec=LapRecorder(storage)
    for distance in range(0, 2100, 100):
        value=state(1,distance,distance * 20); value["ers"] = 1; value["ers_mode"] = 1 if distance < 1000 else 2; rec.observe(value)
    rec.observe(state(2,0,1000)); rec._queue.join()
    assert storage.laps[0]["ersUsageCount"] == 0
    assert not any(sample["ers_usage"] for sample in storage.laps[0]["samples"])

def test_2026_boost_is_counted_with_or_without_overtake_mode():
    storage=MemoryStorage(); rec=LapRecorder(storage)
    for distance in range(0, 2100, 100):
        value=state(1,distance,distance * 20); value["packet_format"] = 2026
        value["boost_active"] = int(500 <= distance <= 900 or 1500 <= distance <= 1800)
        value["overtake_active"] = int(1500 <= distance <= 1800); rec.observe(value)
    value=state(2,0,1000); value["packet_format"] = 2026; rec.observe(value); rec._queue.join()
    assert storage.laps[0]["ersUsageCount"] == 2

def test_2026_sample_saves_availability_separately_from_active_modes():
    storage=MemoryStorage(); rec=LapRecorder(storage)
    value=state(1,0,0); value.update({"packet_format":2026,"game_year":26,
        "boost_active":0,"overtake_available":1,"overtake_active":0,
        "active_aero_available":1,"active_aero_activation_distance":250,
        "overtake_activation_distance":120,"regulations_2026":1,
        "telemetry2_received":True})
    rec.observe(value)
    sample=rec.current["samples"][0]
    assert sample["overtake_available"] == 1
    assert sample["overtake_active"] == 0
    assert sample["boost_active"] == 0
    assert sample["active_aero_activation_distance"] == 250
    assert sample["telemetry2_received"] is True

def test_in_progress_lap_is_promoted_when_season_pack_is_detected_late():
    rec=LapRecorder(MemoryStorage()); rec.observe(state(1,0,0))
    detected=state(1,100,100); detected["packet_format"]=2026; detected["game_year"]=26; detected["game_version"]="F1 26"
    rec.observe(detected)
    assert rec.current["packetFormat"] == 2026
    assert rec.current["gameYear"] == 26
    assert rec.current["udpMode"] == "2026 Season Pack"

def test_legacy_udp_is_recorded_as_unconfirmed_instead_of_certain_2025_content():
    rec=LapRecorder(MemoryStorage()); value=state(1,0,0)
    value["raw_packet_format"]=2025; value["raw_game_year"]=25
    value["edition_detection"]="legacy_udp_unconfirmed"
    value["udp_configuration_warning"]="Select 2026 UDP"
    rec.observe(value)
    assert rec.current["editionDetection"] == "legacy_udp_unconfirmed"
    assert rec.current["sourcePacketFormat"] == 2025
    assert rec.current["udpConfigurationWarning"] == "Select 2026 UDP"

def test_in_progress_f1_25_lap_updates_when_identification_arrives_late():
    rec=LapRecorder(MemoryStorage()); value=state(1,0,0)
    value.update(edition_detection="legacy_udp_unconfirmed", udp_configuration_warning="Waiting")
    rec.observe(value)
    value=state(1,100,100); value.update(edition_detection="session_formula_2025", formula=0)
    rec.observe(value)
    assert rec.current["editionDetection"] == "session_formula_2025"
    assert rec.current["udpConfigurationWarning"] is None
    assert rec.current["formula"] == 0

def test_samples_only_store_analysis_inputs():
    rec=LapRecorder(MemoryStorage()); rec.observe(state(1,0,0))
    sample=rec.current["samples"][0]
    removed={"timestamp","lap_number","gear","rpm","steer","aero_mode","aero_available",
             "aero_distance","ers_active","tyre_compound","tyre_temperature"}
    assert removed.isdisjoint(sample)
    assert "ers_mguk_power" in sample
    assert "ers_mode" in sample
    assert "ers_soc" in sample
    assert "fuel_in_tank_kg" in sample

def test_session_link_change_starts_a_fresh_lap_even_on_same_track_and_uid():
    rec=LapRecorder(MemoryStorage()); first=state(1,0,0); first["session_link_identifier"]=10
    rec.observe(first)
    second=state(1,100,100); second["session_link_identifier"]=11
    rec.observe(second)
    assert rec.current["sessionLinkIdentifier"] == 11
    assert rec.current["samples"][0]["lap_distance"] == 100


def race_state(lap, distance, time_ms):
    return state(lap, distance, time_ms) | {"session_type": 15,
        "lap_packet_session_time": (lap - 1) * 42 + time_ms / 1000,
        "ers_store_energy_j": 4000000 - distance * 100,
        "fuel_in_tank_kg": 30 - distance / 1000}


def test_repeated_flashbacks_save_one_lap_with_only_final_timeline():
    store = MemoryStorage(); rec = LapRecorder(store)
    for distance in range(0, 1601, 5):
        value = race_state(1, distance, distance * 20)
        if distance >= 1000:
            value.update(lap_invalid=True, ers_mode=3, fuel_in_tank_kg=0)
        rec.observe(value)
    rec.observe(race_state(1, 903, 18060))
    for distance in range(908, 1409, 5):
        rec.observe(race_state(1, distance, distance * 20))
    rec.observe(race_state(1, 1001, 20020))
    for distance in range(1006, 2107, 5):
        rec.observe(race_state(1, distance, distance * 20))
    rec.observe(race_state(2, 0, 0) | {"last_lap_time_ms": 42140})
    assert rec.flush()
    assert len(store.laps) == 1
    lap = store.laps[0]
    assert lap["validLap"] and lap["rewindCount"] == 2
    assert lap["ersUsageCount"] == 0 and lap["fuelInTankKgAtEnd"] > 0
    assert [event["toDistanceM"] for event in lap["rewindSplices"]] == [903, 1001]
    assert all(b["lap_distance"] > a["lap_distance"] and b["lap_time_ms"] > a["lap_time_ms"]
               for a, b in zip(lap["samples"], lap["samples"][1:]))
    assert "_invalid_at_ms" not in lap and "_session_key" not in lap
    from telemetry_quality import lap_quality
    assert lap_quality(lap)["energy"]["available"]


def test_invalidity_in_retained_prefix_stays_invalid_even_if_resumed_flag_clears():
    rec = LapRecorder(MemoryStorage())
    for distance in range(0, 1601, 100):
        rec.observe(race_state(1, distance, distance * 20) | {"lap_invalid": distance == 500})
    rec.observe(race_state(1, 900, 18000))
    assert rec.current["validLap"] is False


def test_unsampled_invalidity_is_removed_when_rewound_before_it():
    rec = LapRecorder(MemoryStorage())
    rec.observe(race_state(1, 0, 0))
    rec.observe(race_state(1, 2, 40) | {"lap_invalid": True})
    rec.observe(race_state(1, 1, 20))
    assert rec.current["validLap"] and rec.current["rewindCount"] == 1
    assert [s["lap_distance"] for s in rec.current["samples"]] == [0, 1]


def test_race_rewind_to_start_is_not_mistaken_for_a_completed_lap():
    store = MemoryStorage(); rec = LapRecorder(store)
    for distance in range(0, 2100, 100):
        rec.observe(race_state(1, distance, distance * 20))
    rec.observe(race_state(1, 10, 200))
    assert rec.flush() and store.laps == []
    assert rec.current["rewindCount"] == 1
    assert [s["lap_distance"] for s in rec.current["samples"]] == [0, 10]


def test_time_trial_same_number_crossing_with_forward_session_clock_finishes():
    store = MemoryStorage(); rec = LapRecorder(store)
    for distance in range(0, 2100, 100):
        rec.observe(state(1, distance, distance * 20) | {"lap_packet_session_time": distance / 50,
                                                      "session_type": 18})
    rec.observe(state(1, 10, 200) | {"lap_packet_session_time": 42, "session_type": 18})
    assert rec.flush() and len(store.laps) == 1
    assert rec.current["rewindCount"] == 0


def test_rewind_before_first_sample_does_not_invent_missing_prefix():
    store = MemoryStorage(); rec = LapRecorder(store)
    for distance in range(1500, 2100, 100):
        rec.observe(race_state(1, distance, distance * 20))
    for distance in range(500, 2100, 100):
        rec.observe(race_state(1, distance, distance * 20))
    rec.observe(race_state(2, 0, 0))
    assert rec.flush() and store.laps == []


def test_rewind_to_older_unrecorded_lap_does_not_finish_current_lap():
    store = MemoryStorage(); rec = LapRecorder(store)
    for distance in range(0, 2100, 100):
        rec.observe(race_state(5, distance, distance * 20))
    rec.observe(race_state(4, 1500, 30000))
    assert rec.flush() and store.laps == []
    assert rec.current["lapNumber"] == 4
    assert rec.current["samples"][0]["lap_distance"] == 1500


def test_rewind_across_finish_line_revises_one_lap_and_preserves_old_copy(tmp_path):
    from storage import LapStorage
    store = LapStorage(tmp_path); rec = LapRecorder(store)
    for distance in range(0, 2100, 100):
        rec.observe(race_state(1, distance, distance * 20))
    rec.observe(race_state(2, 0, 0) | {"last_lap_time_ms": 42000})
    assert rec.flush()
    original = store.list_laps()[0]
    for distance in range(1800, 2100, 100):
        rec.observe(race_state(1, distance, distance * 20))
    rec.observe(race_state(2, 0, 0) | {"last_lap_time_ms": 43000})
    assert rec.flush()
    laps = store.list_laps()
    assert len(laps) == 1 and laps[0]["id"] == original["id"]
    assert laps[0]["lapTimeMs"] == 43000
    assert laps[0]["rewindCount"] == 1 and laps[0]["recordingRevision"] == 2
    assert store.session_reference(laps[0]["id"])["lapTimeMs"] == 43000
    import json
    backups = list(tmp_path.rglob("revision-*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text())["lapTimeMs"] == 42000


def test_session_change_cannot_restore_previous_session_lap():
    store = MemoryStorage(); rec = LapRecorder(store)
    for distance in range(0, 2100, 100):
        rec.observe(race_state(1, distance, distance * 20))
    rec.observe(race_state(2, 0, 0))
    rec.observe(race_state(1, 1800, 36000) | {"session_uid": 2})
    assert rec.current["rewindCount"] == 0
    assert len(rec.current["samples"]) == 1


def test_receiver_continues_while_background_finalization_is_blocked():
    import threading
    entered, release = threading.Event(), threading.Event()
    store = MemoryStorage()
    class BlockingRecorder(LapRecorder):
        def _finalize_lap(self, lap):
            assert threading.current_thread().name == "lap-writer"
            entered.set()
            assert release.wait(3)
            return super()._finalize_lap(lap)
    rec = BlockingRecorder(store)
    try:
        for distance in range(0, 2100, 100):
            rec.observe(race_state(1, distance, distance * 20))
        rec.observe(race_state(2, 0, 0))
        assert entered.wait(1)
        assert rec.persistence_status()["pending_laps"] == 1
        assert store.laps == [] and not rec.flush(timeout=.001)
        rec.observe(race_state(2, 100, 2000))
        assert rec.current["lapNumber"] == 2
        assert [s["lap_distance"] for s in rec.current["samples"]] == [0, 100]
    finally:
        release.set()
    assert rec.flush() and len(store.laps) == 1
    assert store.laps[0]["sampleCount"] == 21


def test_rewind_cannot_change_queued_samples_splices_or_setup_before_save():
    import threading
    entered, release = threading.Event(), threading.Event()
    store = MemoryStorage()
    class BlockingRecorder(LapRecorder):
        def _finalize_lap(self, lap):
            entered.set()
            assert release.wait(3)
            return super()._finalize_lap(lap)
    rec = BlockingRecorder(store)
    try:
        for distance in range(0, 2100, 100):
            rec.observe(race_state(1, distance, distance * 20) | {"car_setup": {"frontWing": 20}})
        rec.observe(race_state(1, 1000, 20000) | {"car_setup": {"frontWing": 20}})
        for distance in range(1100, 2100, 100):
            rec.observe(race_state(1, distance, distance * 20) | {"car_setup": {"frontWing": 20}})
        rec.observe(race_state(2, 0, 0))
        assert entered.wait(1)
        rec.observe(race_state(1, 1800, 36000) | {"car_setup": {"frontWing": 30}})
        rec.observe(race_state(1, 1900, 38000) | {"car_setup": {"frontWing": 30}, "speed": 200})
        rec.observe(race_state(2, 0, 0))
    finally:
        release.set()
    assert rec.flush() and len(store.laps) == 2
    old, replayed = store.laps
    assert old["rewindCount"] == 1 and len(old["rewindSplices"]) == 1
    assert replayed["rewindCount"] == 2 and len(replayed["rewindSplices"]) == 2
    assert old["sampleCount"] == 21 and old["samples"][-1]["lap_distance"] == 2000
    assert replayed["sampleCount"] == 20 and replayed["samples"][-1]["lap_distance"] == 1900
    assert old["samples"][-2]["speed"] == 100 and replayed["samples"][-1]["speed"] == 200
    assert old["_carSetup"]["frontWing"] == 20 and replayed["_carSetup"]["frontWing"] == 30
