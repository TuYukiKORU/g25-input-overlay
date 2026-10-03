import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import struct
import pytest
from telemetry import (CAR_DAMAGE_DATA_SIZE, CAR_SETUP_FIELDS, CAR_SETUP_STRUCT,
                       CAR_TELEMETRY2_STRUCT, HEADER_SIZE,
                       LEGACY_2026_F1_TEAM_IDS, PARTICIPANT_DATA_SIZE_2025,
                       MOTION_LONGITUDINAL_G_OFFSET, SESSION_GAME_MODE_OFFSET,
                       SESSION_LINK_OFFSET, SESSION_SEASON_LINK_OFFSET,
                       SESSION_WEEKEND_LINK_OFFSET, parse_car_setup,
                       parse_car_telemetry2, parse_participants_summary, parse_session_identity,
                       packet_indicates_season_pack, season_pack_packet_evidence,
                       ers_activity_for_wire_mode,
                       parse_car_motion,
                       telemetry_mode, tyre_compound_name)


def test_formula_compound_name_combines_visual_and_actual_values():
    assert tyre_compound_name(18, 16) == "Soft (C3)"
    assert tyre_compound_name(22, 18) == "Hard (C6)"


def test_wet_compounds_use_visual_name():
    assert tyre_compound_name(7, 7) == "Intermediate"
    assert tyre_compound_name(8, 8) == "Wet"


def test_current_car_damage_record_size_includes_tyre_blisters():
    assert CAR_DAMAGE_DATA_SIZE == 46


@pytest.mark.parametrize("wire_format,index", [(2025, 1), (2025, 21), (2026, 0), (2026, 3), (2026, 23)])
@pytest.mark.parametrize("longitudinal", [-4.375, 0, 1.525])
def test_motion_decodes_player_position_and_signed_acceleration(wire_format, index, longitudinal):
    size, cars = (54, 24) if wire_format == 2026 else (60, 22)
    packet = bytearray(HEADER_SIZE + size * cars)
    offset = HEADER_SIZE + index * size
    struct.pack_into("<3f", packet, offset, 125.5, 12.0, -834.25)
    if wire_format == 2026:
        struct.pack_into("<3h", packet, offset + 36, 1500, round(longitudinal * 1000), -900)
    else:
        struct.pack_into("<3f", packet, offset + 36, 1.5, longitudinal, -.9)
    result = parse_car_motion(packet, index, wire_format)
    assert result["world_position_x"] == 125.5
    assert result["world_position_z"] == -834.25
    assert result["longitudinal_g"] == pytest.approx(longitudinal)


@pytest.mark.parametrize("wire_format,size", [(2025, 60), (2026, 54)])
def test_motion_rejects_truncated_player_record_and_invalid_index(wire_format, size):
    packet = bytearray(HEADER_SIZE + size * 2 - 1)
    assert parse_car_motion(packet, 1, wire_format) is None
    assert parse_car_motion(packet, -1, wire_format) is None
    assert parse_car_motion(packet, 255, wire_format) is None


def test_motion_rejects_nonfinite_position():
    packet = bytearray(HEADER_SIZE + 54)
    struct.pack_into("<f", packet, HEADER_SIZE, float("nan"))
    assert parse_car_motion(packet, 0, 2026) is None


@pytest.mark.parametrize("wire_format,game_year,index", [(2025, 26, 21), (2026, 25, 23)])
def test_udp_motion_reaches_saved_lap_for_both_season_pack_wire_layouts(monkeypatch, wire_format, game_year, index):
    from types import SimpleNamespace
    import telemetry
    from lap_recorder import LapRecorder
    from test_recorder import MemoryStorage, state

    motion_size, cars = (54, 24) if wire_format == 2026 else (60, 22)
    def packet(packet_id, size):
        data = bytearray(HEADER_SIZE + size * cars)
        struct.pack_into("<H", data, 0, wire_format)
        data[2], data[6], data[27] = game_year, packet_id, index
        struct.pack_into("<Q", data, 7, 1)
        return data

    packets = []
    for distance in range(0, 2100, 100):
        motion = packet(0, motion_size)
        offset = HEADER_SIZE + index * motion_size
        struct.pack_into("<3f", motion, offset, distance + 125.5, 12, -834.25)
        if wire_format == 2026:
            struct.pack_into("<h", motion, offset + 38, -2750)
        else:
            struct.pack_into("<f", motion, offset + 40, -2.75)
        timing = packet(2, 57)
        offset = HEADER_SIZE + index * 57
        struct.pack_into("<II", timing, offset, 42000, distance * 20)
        struct.pack_into("<f", timing, offset + 20, distance)
        timing[offset + 33] = 1
        packets.extend([motion, timing])
    finish = packet(2, 57)
    offset = HEADER_SIZE + index * 57
    struct.pack_into("<II", finish, offset, 42000, 1000)
    finish[offset + 33] = 2
    packets.append(finish)
    incoming = iter([*packets, None])
    monkeypatch.setattr(telemetry, "_receive_packet", lambda *args: next(incoming))
    received = []
    monkeypatch.setattr(telemetry, "recording_health", SimpleNamespace(
        received=lambda *args: received.append(args), reset=lambda _: None))
    storage = MemoryStorage()
    recorder = LapRecorder(storage)
    telemetry.udp_loop(state(1, 0, 0), recorder, sock=SimpleNamespace(close=lambda: None))
    assert recorder.flush(2)
    samples = storage.laps[0]["samples"]
    assert samples[0]["position"] == {"x": 125.5, "y": 12.0, "z": -834.25}
    assert samples[-1]["position"]["x"] == 2125.5
    assert all(sample["longitudinal_g"] == -2.75 for sample in samples)
    assert (0, 1) in received


def test_game_year_selects_2026_season_pack_even_with_2025_packet_format():
    assert telemetry_mode(2025, 26) == (2026, "F1 26")
    assert telemetry_mode(2025, 25) == (2025, "F1 25")


def test_telemetry2_promotes_2025_header_to_2026_season_pack():
    packet = bytearray(HEADER_SIZE + 10)
    assert packet_indicates_season_pack(16, packet, 0)
    assert telemetry_mode(2025, 25, True) == (2026, "F1 26")


def test_telemetry2_fields_follow_official_2026_layout():
    packet = bytearray(HEADER_SIZE + CAR_TELEMETRY2_STRUCT.size * 2)
    CAR_TELEMETRY2_STRUCT.pack_into(
        packet, HEADER_SIZE + CAR_TELEMETRY2_STRUCT.size,
        1, 1, 320, 1, 0, 175, 1, 0,
    )
    assert parse_car_telemetry2(packet, 1) == {
        "active_aero_mode": 1,
        "active_aero_available": 1,
        "active_aero_activation_distance": 320,
        "overtake_available": 1,
        "overtake_active": 0,
        "overtake_activation_distance": 175,
        "regulations_2026": 1,
        "driving_wrong_way": 0,
    }
    assert CAR_TELEMETRY2_STRUCT.size == 10


def test_overtake_availability_is_not_treated_as_activity():
    packet = bytearray(HEADER_SIZE + CAR_TELEMETRY2_STRUCT.size)
    CAR_TELEMETRY2_STRUCT.pack_into(packet, HEADER_SIZE, 0, 1, 80, 1, 0, 40, 1, 0)
    value = parse_car_telemetry2(packet, 0)
    assert value["overtake_available"] == 1
    assert value["overtake_active"] == 0


def test_deploy_mode_three_means_boost_only_in_2026_wire_schema():
    assert ers_activity_for_wire_mode(2026, 3) == {
        "boost_active": 1, "legacy_overtake_active": 0,
    }
    assert ers_activity_for_wire_mode(2025, 3) == {
        "boost_active": 0, "legacy_overtake_active": 1,
    }
    assert ers_activity_for_wire_mode(2026, 2)["boost_active"] == 0


def test_short_or_unrelated_packet_does_not_promote_session():
    assert not packet_indicates_season_pack(16, bytearray(HEADER_SIZE + 9), 0)
    assert not packet_indicates_season_pack(6, bytearray(HEADER_SIZE + 10), 0)


def test_legacy_participants_detect_2026_team_id_low_bytes():
    packet = bytearray(HEADER_SIZE + 1 + PARTICIPANT_DATA_SIZE_2025 * 22)
    packet[HEADER_SIZE] = 22
    first_team_offset = HEADER_SIZE + 1 + 3
    packet[first_team_offset] = 229  # Audi 485 represented by legacy uint8
    summary = parse_participants_summary(packet, 2025)
    assert summary["num_active_cars"] == 22
    assert summary["team_ids"][0] in LEGACY_2026_F1_TEAM_IDS
    assert season_pack_packet_evidence(4, packet, 0, 2025) == "participants_2026_team_id"


def test_ordinary_2025_participant_grid_does_not_promote_session():
    packet = bytearray(HEADER_SIZE + 1 + PARTICIPANT_DATA_SIZE_2025 * 22)
    packet[HEADER_SIZE] = 20
    for index in range(20):
        packet[HEADER_SIZE + 1 + index * PARTICIPANT_DATA_SIZE_2025 + 3] = index % 10
    assert season_pack_packet_evidence(4, packet, 0, 2025) is None


def test_madrid_track_is_2026_content_evidence_even_with_legacy_header():
    packet = bytearray(HEADER_SIZE + SESSION_GAME_MODE_OFFSET + 1)
    struct.pack_into("<b", packet, HEADER_SIZE + 7, 42)
    assert season_pack_packet_evidence(1, packet, 0, 2025) == "2026_only_track"


def test_player_car_setup_is_decoded_from_its_own_record():
    values = (20, 18, 75, 30, -3.5, -2.0, .1, .2, 10, 8, 12, 9, 20, 45,
              100, 57, 70, 22.1, 22.2, 23.1, 23.2, 4, 5.5)
    packet = bytearray(HEADER_SIZE + CAR_SETUP_STRUCT.size * 2)
    CAR_SETUP_STRUCT.pack_into(packet, HEADER_SIZE + CAR_SETUP_STRUCT.size, *values)
    setup = parse_car_setup(packet, 1)
    assert tuple(setup) == CAR_SETUP_FIELDS
    assert setup["onThrottleDifferential"] == 75
    assert setup["brakeBias"] == 57
    assert setup["fuelLoad"] == struct.unpack("<f", struct.pack("<f", 5.5))[0]
    assert CAR_SETUP_STRUCT.size == 50


def test_session_identity_includes_mode_and_persistent_link_numbers():
    packet = bytearray(HEADER_SIZE + SESSION_GAME_MODE_OFFSET + 1)
    offset = HEADER_SIZE
    packet[offset + 6] = 15
    struct.pack_into("<b", packet, offset + 7, 11)
    struct.pack_into("<I", packet, offset + SESSION_SEASON_LINK_OFFSET, 101)
    struct.pack_into("<I", packet, offset + SESSION_WEEKEND_LINK_OFFSET, 202)
    struct.pack_into("<I", packet, offset + SESSION_LINK_OFFSET, 303)
    packet[offset + SESSION_GAME_MODE_OFFSET] = 27
    identity = parse_session_identity(packet)
    assert identity["track_id"] == 11
    assert identity["session_type"] == 15
    assert identity["game_mode"] == 27
    assert identity["session_link_identifier"] == 303
