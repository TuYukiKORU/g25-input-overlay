"""Replay EA's two packed layouts without binding the real game UDP port.

Fixtures use specification sizes and offsets independently of decoder constants.
"""
import copy
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import telemetry
from state import DEFAULT_TELEMETRY_STATE


RECORDS = {
    2025: {0: 60, 2: 57, 4: 57, 5: 50, 6: 60, 7: 55, 10: 46},
    2026: {0: 54, 2: 57, 4: 60, 5: 50, 6: 59, 7: 59, 10: 46},
}


def packet(wire, packet_id, index=0, uid=1, year=25):
    cars = 24 if wire == 2026 else 22
    if packet_id in RECORDS[wire]:
        size = 29 + RECORDS[wire][packet_id] * cars
        size += 1 if packet_id == 4 else 4 if packet_id == 5 else 3 if packet_id == 6 else 2 if packet_id == 2 else 0
    else:
        size = {1: 926 if wire == 2026 else 753, 13: 273, 16: 269}[packet_id]
    data = bytearray(size)
    struct.pack_into('<HBBBBBQfIIBB', data, 0, wire, year, 1, 0, 1, packet_id, uid, 1.0, 10, 10, index, 255)
    return data


def session(wire=2025, formula=0, uid=1, link=10):
    data = packet(wire, 1, uid=uid)
    data[29 + 3] = 35
    data[29 + 6] = 10
    data[29 + 7] = 10  # Spa
    data[29 + 8] = formula
    struct.pack_into('<III', data, 29 + 641, 100, 200, link)
    data[29 + 665] = 23
    return data


def replay(monkeypatch, packets, latest=None, recorder=None):
    incoming = iter([*packets, None])
    monkeypatch.setattr(telemetry, '_receive_packet', lambda *args: next(incoming))
    receipts = []
    monkeypatch.setattr(telemetry, 'recording_health', SimpleNamespace(
        received=lambda *args: receipts.append(args), reset=lambda _: None))
    latest = copy.deepcopy(DEFAULT_TELEMETRY_STATE) if latest is None else latest
    telemetry.udp_loop(latest, recorder, sock=SimpleNamespace(close=lambda: None))
    return latest, receipts


@pytest.mark.parametrize('wire,index', [(2025, 0), (2025, 21), (2026, 0), (2026, 23)])
def test_all_used_packets_at_first_and_last_grid_slots(monkeypatch, wire, index):
    motion = packet(wire, 0, index)
    offset = 29 + index * RECORDS[wire][0]
    struct.pack_into('<3f', motion, offset, 1234.5, 7, -987.25)
    if wire == 2026:
        struct.pack_into('<3h', motion, offset + 36, 1125, -2375, 750)
    else:
        struct.pack_into('<3f', motion, offset + 36, 1.125, -2.375, .75)

    timing = packet(wire, 2, index)
    offset = 29 + index * 57
    struct.pack_into('<II', timing, offset, 90555, 12500)
    # Nonzero minute parts must not shift the lapDistance / flags offsets.
    timing[offset + 10] = 1
    timing[offset + 13] = 2
    struct.pack_into('<f', timing, offset + 20, 456.75)
    timing[offset + 33:offset + 38] = bytes([7, 1, 2, 1, 1])

    controls = packet(wire, 6, index)
    offset = 29 + index * RECORDS[wire][6]
    struct.pack_into('<HfffBbHB', controls, offset, 287, .75, -.4, .25, 0, 7, 12000, 1)

    status = packet(wire, 7, index)
    offset = 29 + index * RECORDS[wire][7]
    struct.pack_into('<3f', status, offset + 5, 23.5, 110, -1.25)
    status[offset + 25:offset + 28] = bytes([18, 16, 6])
    struct.pack_into('<3fB', status, offset + 29, 400000, -25000, 2800000, 3)

    damage = packet(wire, 10, index)
    struct.pack_into('<4f', damage, 29 + index * 46, 10.5, 20.25, 30.75, 40)
    wheels = packet(wire, 13, index)
    struct.pack_into('<8f', wheels, 29 + 48, 11, 22, 33, 44, -.125, .25, -.5, .75)

    setup = packet(wire, 5, index)
    struct.pack_into('<BBBBffffBBBBBBBBBffffBf', setup, 29 + index * 50,
                     20, 18, 75, 30, -3.5, -2, .125, .25, 10, 8, 12, 9, 20, 45,
                     100, 57, 70, 22.125, 22.25, 23.125, 23.25, 4, 5.5)
    participants = packet(wire, 4, index)
    participants[29] = 24 if wire == 2026 else 22
    team_offset, fmt, team = (5, '<H', 485) if wire == 2026 else (3, '<B', 8)
    struct.pack_into(fmt, participants, 30 + index * RECORDS[wire][4] + team_offset, team)

    packets = [session(wire, 13 if wire == 2026 else 0), participants,
               motion, controls, status, damage, wheels, setup, timing]
    if wire == 2026:
        extra = packet(wire, 16, index)
        struct.pack_into('<BBHBBHBB', extra, 29 + index * 10, 1, 1, 320, 1, 0, 175, 1, 0)
        packets.append(extra)
    observed = []
    latest, receipts = replay(monkeypatch, packets, recorder=SimpleNamespace(observe=observed.append))
    assert latest['world_position_x'] == 1234.5
    assert latest['world_position_z'] == -987.25
    assert latest['longitudinal_g'] == -2.375
    assert latest['speed'] == 287
    assert latest['throttle_raw'] == .75 and latest['brake_raw'] == .25
    assert latest['last_lap_time_ms'] == 90555 and latest['current_lap_time_ms'] == 12500
    assert latest['lap_distance'] == 456.75 and latest['lap_number'] == 7
    assert latest['pit_status'] == 1 and latest['lap_invalid'] is True
    assert latest['fuel_in_tank_kg'] == 23.5 and latest['fuel_remaining_laps'] == -1.25
    assert latest['fuel_capacity_kg'] == 110
    assert latest['ers_mguk_power'] == -25000 and latest['ers_percent'] == 70
    assert latest['ers_store_energy_j'] == 2800000 and latest['ers_mode'] == 3
    assert latest['tyre_compound'] == 'Soft (C3)' and latest['tyres_age_laps'] == 6
    assert latest['tyres_wear'] == [10.5, 20.25, 30.75, 40]
    assert latest['wheel_speed'] == [11, 22, 33, 44]
    assert latest['wheel_slip_ratio'] == [-.125, .25, -.5, .75]
    assert latest['car_setup']['rearLeftTyrePressure'] == 22.125
    assert latest['car_setup']['frontRightTyrePressure'] == 23.25
    assert latest['car_setup']['brakeBias'] == 57
    assert latest['participant_team_ids'][index] == team
    assert latest['season_link_identifier'] == 100 and latest['session_link_identifier'] == 10
    assert latest['game_mode'] == 23 and latest['total_laps'] == 35
    assert latest['game_version'] == ('F1 26' if wire == 2026 else 'F1 25')
    assert {value[0] for value in receipts} == {0, 1, 2, 4, 5, 6, 7, 10, 13} | ({16} if wire == 2026 else set())
    assert len(observed) == 1  # Timing is the recorder clock, not every packet.
    if wire == 2026:
        assert latest['aero_mode'] == 1 and latest['overtake_available'] == 1
        assert latest['overtake_active'] == 0 and latest['boost_active'] == 1
        assert latest['active_aero_activation_distance'] == 320
        assert latest['overtake_activation_distance'] == 175
    else:
        assert latest['drs'] == 1 and latest['boost_active'] == 0
        assert latest['overtake_active'] == 1


@pytest.mark.parametrize('wire', [2025, 2026])
@pytest.mark.parametrize('packet_id', [0, 2, 5, 6, 7, 10, 13, 16])
def test_truncated_player_records_do_not_record_or_report_healthy(monkeypatch, wire, packet_id):
    index = 23 if wire == 2026 else 21
    data = packet(wire, packet_id, index)
    end = 273 if packet_id == 13 else 29 + (index + 1) * (10 if packet_id == 16 else RECORDS[wire][packet_id])
    latest, receipts = replay(monkeypatch, [data[:end - 1]], recorder=SimpleNamespace(observe=lambda _: pytest.fail('Malformed timing reached recorder')))
    assert receipts == []
    assert latest['speed'] == 0 and latest['world_position_x'] is None


@pytest.mark.parametrize('packet_id', [0, 2, 4, 5, 6, 7, 10, 16])
def test_invalid_car_index_and_partial_grid_cannot_supply_detection(monkeypatch, packet_id):
    data = packet(2025, packet_id, 255)
    if packet_id == 4:
        data[29] = 22
        data[33] = 229
        data = data[:34]  # Team byte present, but the record/grid is incomplete.
    latest, receipts = replay(monkeypatch, [data])
    assert not latest['season_pack_detected'] and receipts == []


@pytest.mark.parametrize('wire', [2025, 2026])
@pytest.mark.parametrize('packet_id,field_offset', [(2, 20), (5, 4), (6, 2), (7, 37), (10, 0), (13, 48)])
def test_nan_packet_is_skipped_and_receiver_continues(monkeypatch, wire, packet_id, field_offset):
    data = packet(wire, packet_id)
    struct.pack_into('<f', data, 29 + field_offset, float('nan'))
    good = packet(wire, 6)
    struct.pack_into('<HfffBbHB', good, 29, 123, .5, 0, .25, 0, 3, 7000, 0)
    latest, receipts = replay(monkeypatch, [data, good])
    assert latest['speed'] == 123 and [value[0] for value in receipts] == [6]


def test_session_formula_detects_both_seasons_with_same_legacy_header(monkeypatch):
    latest, _ = replay(monkeypatch, [session(formula=13)])
    assert latest['game_version'] == 'F1 26'
    assert latest['edition_detection'] == 'session_formula_2026'
    assert latest['raw_packet_format'] == 2025 and latest['raw_game_year'] == 25
    assert telemetry.edition_status(latest)['confirmed']
    # Returning to 2025 resets the evidence even when EA reuses the UID.
    latest, _ = replay(monkeypatch, [session(formula=0, link=11)], latest)
    assert latest['game_version'] == 'F1 25'
    assert latest['edition_detection'] == 'session_formula_2025'
    assert not latest['season_pack_detected']


def test_legacy_controls_alone_remain_ambiguous_and_late_evidence_wins(monkeypatch):
    latest, _ = replay(monkeypatch, [packet(2025, 6)])
    assert not telemetry.edition_status(latest)['confirmed']
    latest, _ = replay(monkeypatch, [session(formula=13)], latest)
    assert telemetry.edition_status(latest)['confirmed']
    # A later ordinary header never downgrades confirmed 2026 content.
    latest, _ = replay(monkeypatch, [packet(2025, 6)], latest)
    assert latest['game_version'] == 'F1 26'


def test_2026_participants_are_detected_in_legacy_format(monkeypatch):
    data = packet(2025, 4)
    data[29] = 1
    data[33] = 229
    latest, _ = replay(monkeypatch, [data])
    assert latest['edition_detection'] == 'participants_2026_team_id'


@pytest.mark.parametrize('team', [0, 8, 9])
def test_original_f1_participants_confirm_2025_before_session_packet(monkeypatch, team):
    data = packet(2025, 4)
    data[29] = 1
    data[33] = team
    latest, _ = replay(monkeypatch, [data])
    assert latest['edition_detection'] == 'participants_2025_team_id'
    assert latest['game_version'] == 'F1 25' and telemetry.edition_status(latest)['confirmed']


@pytest.mark.parametrize('team', [233, 243])  # 489 / 499 encoded in legacy uint8.
def test_season_eight_2026_f2_grid_is_detected_in_legacy_udp(monkeypatch, team):
    data = packet(2025, 4)
    data[29] = 1
    data[33] = team
    latest, _ = replay(monkeypatch, [session(formula=2), data])
    assert latest['game_version'] == 'F1 26'


def test_formula_switch_resets_identification_without_uid_or_link_change(monkeypatch):
    latest, _ = replay(monkeypatch, [session(formula=13)])
    latest, _ = replay(monkeypatch, [session(formula=0)], latest)
    assert latest['edition_detection'] == 'session_formula_2025'


@pytest.mark.parametrize('formula', [1, 2, 3, 4, 6, 8, 9])
def test_other_formula_classes_do_not_falsely_confirm_original_f1_25(monkeypatch, formula):
    latest, _ = replay(monkeypatch, [session(formula=formula)])
    assert latest['edition_detection'] == 'legacy_udp_unconfirmed'


def test_new_session_clears_edition_and_old_car_values(monkeypatch):
    latest, _ = replay(monkeypatch, [session(formula=13)])
    latest.update(tyres_wear=[50] * 4, fuel_in_tank_kg=20, wheel_speed=[100] * 4, car_setup={'frontWing': 20})
    latest, _ = replay(monkeypatch, [packet(2025, 6, uid=2)], latest)
    assert latest['edition_detection'] == 'legacy_udp_unconfirmed'
    assert latest['tyres_wear'] == [None] * 4 and latest['fuel_in_tank_kg'] is None
    assert latest['wheel_speed'] == [None] * 4 and latest['car_setup'] is None


def test_telemetry2_remains_authoritative_when_legacy_packets_arrive(monkeypatch):
    extra = packet(2025, 16)
    struct.pack_into('<BBHBBHBB', extra, 29, 1, 1, 0, 1, 0, 0, 1, 0)
    status = packet(2025, 7)
    status[29 + 41] = 3  # Legacy mode 3 must not overwrite dedicated Overtake=0.
    latest, _ = replay(monkeypatch, [extra, packet(2025, 6), status])
    assert latest['aero'] == 1 and latest['overtake_active'] == 0


def test_invalid_telemetry2_boolean_does_not_promote_edition(monkeypatch):
    data = packet(2025, 16)
    data[29] = 255
    latest, receipts = replay(monkeypatch, [data])
    assert latest['game_version'] == 'unknown' and receipts == []


@pytest.mark.parametrize('formula,label', [(0, 'F1 25'), (13, 'F1 25 · 2026 Season Pack')])
def test_automatic_identification_reaches_recording_panel_api(monkeypatch, formula, label):
    import app as app_module
    latest, _ = replay(monkeypatch, [session(formula=formula)])
    monkeypatch.setattr(app_module, 'latest', latest)
    body = app_module.app.test_client().get('/api/recording-health').get_json()
    assert body['edition']['label'] == label and body['edition']['confirmed']
    assert body['edition']['wire_format'] == 2025 and body['edition']['formula'] == formula
    assert 4 in {group['packet_id'] for group in body['groups']}


def test_reused_uid_does_not_keep_previous_session_packet_health(monkeypatch):
    from recording_health import RecordingHealth
    incoming = iter([session(formula=13), packet(2025, 0), session(formula=0), None])
    monkeypatch.setattr(telemetry, '_receive_packet', lambda *args: next(incoming))
    health = RecordingHealth(lambda: 1)
    monkeypatch.setattr(telemetry, 'recording_health', health)
    telemetry.udp_loop(copy.deepcopy(DEFAULT_TELEMETRY_STATE), sock=SimpleNamespace(close=lambda: None))
    groups = {group['packet_id']: group['state'] for group in health.snapshot()['groups']}
    assert groups[1] == 'receiving' and groups[0] == 'missing'
