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

def test_longitudinal_g_is_saved_with_samples():
    rec=LapRecorder(MemoryStorage()); value=state(1,0,0); value["longitudinal_g"] = .85
    rec.observe(value)
    assert rec.current["samples"][0]["longitudinal_g"] == .85

def test_rewind_marks_flashback_invalid():
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
