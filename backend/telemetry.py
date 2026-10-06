import socket
import struct
import math
import copy
from state import DEFAULT_TELEMETRY_STATE
from recording_health import recording_health

PORT = 20777
HEADER_SIZE = 29
CAR_TELEMETRY_PACKET_ID = 6
CAR_TELEMETRY2_PACKET_ID = 16
CAR_TELEMETRY2_DATA_SIZE = 10
CAR_TELEMETRY2_STRUCT = struct.Struct("<BBHBBHBB")
PARTICIPANTS_PACKET_ID = 4
PARTICIPANT_DATA_SIZE_2025 = 57
PARTICIPANT_TEAM_ID_OFFSET_2025 = 3
MAX_CARS_2025 = 22
# The 2026 F1 team IDs are 476..486. In the selectable legacy F1 25 UDP
# layout m_teamId is uint8, so their low-byte representations are 220..230.
LEGACY_2026_F1_TEAM_IDS = frozenset(range(220, 231))
F1_2026_TEAM_IDS = frozenset(range(476, 487))
# Season 8 adds 2026 F2 teams 489..499. Their legacy low bytes do not
# overlap the original F1 25 team table (F1 0..9; F2 158..168).
SEASON_2026_TEAM_IDS = F1_2026_TEAM_IDS | frozenset(range(489, 500))
LEGACY_SEASON_2026_TEAM_IDS = frozenset(team % 256 for team in SEASON_2026_TEAM_IDS)
F1_2025_TEAM_IDS = frozenset(range(10))
F1_2026_ONLY_TRACK_IDS = frozenset({42})  # Madrid
LAP_DATA_PACKET_ID = 2
CAR_STATUS_PACKET_ID = 7
CAR_SETUPS_PACKET_ID = 5
CAR_SETUP_STRUCT = struct.Struct("<BBBBffffBBBBBBBBBffffBf")
SESSION_PACKET_ID = 1
MOTION_PACKET_ID = 0
MOTION_LONGITUDINAL_G_OFFSET = 40
MOTION_DATA_SIZE_2025 = 60
MOTION_DATA_SIZE_2026 = 54
MOTION_LONGITUDINAL_G_OFFSET_2026 = 38
MOTION_EX_PACKET_ID = 13
CAR_DAMAGE_PACKET_ID = 10
CAR_DAMAGE_DATA_SIZE = 46
CAR_TELEMETRY_STRUCT = struct.Struct("<HfffBbHB")

# PacketSessionData offset after marshal zones and weather forecast samples.
SESSION_GAME_MODE_OFFSET = 665
SESSION_SEASON_LINK_OFFSET = 641
SESSION_WEEKEND_LINK_OFFSET = 645
SESSION_LINK_OFFSET = 649
SESSION_FORMULA_OFFSET = 8

# Sizes of packed per-car records, selected by packetFormat (not gameYear or
# the detected season). The 2026 grid has 24 slots; legacy UDP has 22.
CAR_RECORD_SIZES = {
    2025: {0: 60, 2: 57, 5: 50, 6: 60, 7: 55, 10: 46},
    2026: {0: 54, 2: 57, 5: 50, 6: 59, 7: 59, 10: 46},
}

CAR_SETUP_FIELDS = (
    "frontWing", "rearWing", "onThrottleDifferential", "offThrottleDifferential",
    "frontCamber", "rearCamber", "frontToe", "rearToe",
    "frontSuspension", "rearSuspension", "frontAntiRollBar", "rearAntiRollBar",
    "frontRideHeight", "rearRideHeight", "brakePressure", "brakeBias",
    "engineBraking", "rearLeftTyrePressure", "rearRightTyrePressure",
    "frontLeftTyrePressure", "frontRightTyrePressure", "ballast", "fuelLoad",
)

ACTUAL_TYRE_COMPOUNDS = {
    7: "Inter", 8: "Wet", 16: "C5", 17: "C4", 18: "C3", 19: "C2", 20: "C1", 21: "C0", 22: "C6",
}
VISUAL_TYRE_COMPOUNDS = {
    7: "Intermediate", 8: "Wet", 16: "Soft", 17: "Medium", 18: "Hard",
}

def tyre_compound_name(actual, visual):
    actual_name = ACTUAL_TYRE_COMPOUNDS.get(actual)
    visual_name = VISUAL_TYRE_COMPOUNDS.get(visual)
    if visual_name in ("Soft", "Medium", "Hard") and actual_name and actual_name.startswith("C"):
        return f"{visual_name} ({actual_name})"
    return visual_name or actual_name or "Unknown"

def has_bytes(data, offset, size):
    return offset >= 0 and len(data) >= offset + size

def car_record_offset(data, player_car_index, size, max_cars):
    if not 0 <= player_car_index < max_cars:
        return None
    offset = HEADER_SIZE + player_car_index * size
    return offset if has_bytes(data, offset, size) else None

def parse_car_motion(data, player_car_index, raw_packet_format):
    """Decode the selected wire layout, independently of detected car edition.

    EA's 2026 layout uses signed int16 G values scaled by 1000, shrinking
    each car record from 60 to 54 bytes. Legacy 2025 UDP still uses floats.
    """
    if raw_packet_format == 2026:
        size, max_cars = MOTION_DATA_SIZE_2026, 24
    elif raw_packet_format == 2025:
        size, max_cars = MOTION_DATA_SIZE_2025, 22
    else:
        return None
    if not 0 <= player_car_index < max_cars:
        return None
    offset = HEADER_SIZE + player_car_index * size
    if not has_bytes(data, offset, size):
        return None
    x, y, z = struct.unpack_from("<3f", data, offset)
    if raw_packet_format == 2026:
        longitudinal = struct.unpack_from("<h", data, offset + MOTION_LONGITUDINAL_G_OFFSET_2026)[0] / 1000.0
    else:
        longitudinal = struct.unpack_from("<f", data, offset + MOTION_LONGITUDINAL_G_OFFSET)[0]
    if not all(math.isfinite(value) for value in (x, y, z, longitudinal)):
        return None
    return {"world_position_x": x, "world_position_y": y, "world_position_z": z, "longitudinal_g": longitudinal}

def parse_car_setup(data, player_car_index, raw_packet_format=2025):
    """Decode only the player's compact 50-byte setup record."""
    offset = car_record_offset(data, player_car_index, CAR_SETUP_STRUCT.size,
                               24 if raw_packet_format == 2026 else 22)
    if offset is None:
        return None
    values = CAR_SETUP_STRUCT.unpack_from(data, offset)
    if not all(math.isfinite(value) for value in values):
        return None
    return dict(zip(CAR_SETUP_FIELDS, values))

def parse_car_telemetry2(data, player_car_index):
    """Decode the official 2026-only active-aero and Overtake fields."""
    offset = car_record_offset(data, player_car_index, CAR_TELEMETRY2_STRUCT.size, 24)
    if offset is None:
        return None
    values = CAR_TELEMETRY2_STRUCT.unpack_from(data, offset)
    if any(values[index] not in (0, 1) for index in (0, 1, 3, 4, 6, 7)):
        return None
    return dict(zip((
        "active_aero_mode", "active_aero_available", "active_aero_activation_distance",
        "overtake_available", "overtake_active", "overtake_activation_distance",
        "regulations_2026", "driving_wrong_way",
    ), values))

def parse_session_identity(data):
    """Decode the stable identifiers used to classify and split sessions."""
    offset = HEADER_SIZE
    if not has_bytes(data, offset + SESSION_GAME_MODE_OFFSET, 1):
        return None
    return {
        "total_laps": data[offset + 3],
        "session_type": data[offset + 6],
        "track_id": struct.unpack_from("<b", data, offset + 7)[0],
        "formula": data[offset + SESSION_FORMULA_OFFSET],
        "paused": bool(data[offset + 14]),
        "season_link_identifier": struct.unpack_from("<I", data, offset + SESSION_SEASON_LINK_OFFSET)[0],
        "weekend_link_identifier": struct.unpack_from("<I", data, offset + SESSION_WEEKEND_LINK_OFFSET)[0],
        "session_link_identifier": struct.unpack_from("<I", data, offset + SESSION_LINK_OFFSET)[0],
        "game_mode": data[offset + SESSION_GAME_MODE_OFFSET],
    }

def telemetry_mode(packet_format, game_year, season_pack_detected=False):
    """Normalize the selectable F1 25 / 2026 Season Pack UDP modes."""
    if packet_format == 2026 or game_year == 26 or season_pack_detected:
        return 2026, "F1 26"
    if packet_format == 2025:
        return 2025, "F1 25"
    return None, "unknown"

def ers_activity_for_wire_mode(raw_packet_format, ers_mode):
    """Interpret deploy mode 3 according to the selected UDP wire schema."""
    active = int(ers_mode == 3)
    return {
        "boost_active": active if raw_packet_format == 2026 else 0,
        "legacy_overtake_active": active if raw_packet_format == 2025 else 0,
    }

def packet_indicates_season_pack(packet_id, data, player_car_index):
    """Recognize Season Pack even when its common header still says 2025/25."""
    return (packet_id == CAR_TELEMETRY2_PACKET_ID
            and parse_car_telemetry2(data, player_car_index) is not None)

def parse_participants_summary(data, packet_format):
    """Read active-car count and team IDs from either official wire layout."""
    if not has_bytes(data, HEADER_SIZE, 1):
        return None
    active_cars = data[HEADER_SIZE]
    if packet_format == 2025:
        record_size, team_offset, max_cars, team_format = (
            PARTICIPANT_DATA_SIZE_2025, PARTICIPANT_TEAM_ID_OFFSET_2025,
            MAX_CARS_2025, "<B",
        )
    elif packet_format == 2026:
        # aiControlled:u8, driverId:u16, networkId:u16, teamId:u16
        record_size, team_offset, max_cars, team_format = 60, 5, 24, "<H"
    else:
        return None

    if active_cars > max_cars or not has_bytes(
            data, HEADER_SIZE + 1, active_cars * record_size):
        return None
    count = active_cars
    teams = []
    records_offset = HEADER_SIZE + 1
    team_size = struct.calcsize(team_format)
    for index in range(count):
        offset = records_offset + index * record_size + team_offset
        if not has_bytes(data, offset, team_size):
            break
        teams.append(struct.unpack_from(team_format, data, offset)[0])
    return {"num_active_cars": active_cars, "team_ids": teams}

def season_pack_packet_evidence(packet_id, data, player_car_index, raw_packet_format):
    """Return a high-confidence content signal independent of the UDP header."""
    if packet_indicates_season_pack(packet_id, data, player_car_index):
        return "telemetry2_packet"
    if packet_id == PARTICIPANTS_PACKET_ID:
        summary = parse_participants_summary(data, raw_packet_format)
        if summary:
            team_ids = set(summary["team_ids"])
            if raw_packet_format == 2025 and team_ids & LEGACY_SEASON_2026_TEAM_IDS:
                return "participants_2026_team_id"
            if raw_packet_format == 2026 and team_ids & SEASON_2026_TEAM_IDS:
                return "participants_2026_team_id"
    if packet_id == SESSION_PACKET_ID:
        identity = parse_session_identity(data)
        if identity:
            if identity["formula"] == 13:
                return "session_formula_2026"
            if identity["track_id"] in F1_2026_ONLY_TRACK_IDS:
                return "2026_only_track"
    return None

def update_edition_detection(latest, raw_packet_format, raw_game_year):
    """Resolve positive season signals; never infer a season from packet length."""
    packet_format, game_version = telemetry_mode(
        raw_packet_format, raw_game_year, latest.get("season_pack_detected", False))
    if raw_packet_format == 2026 or raw_game_year == 26:
        detection = "udp_header"
    elif latest.get("season_pack_detected"):
        detection = latest.get("season_pack_detection") or "packet_evidence"
    elif latest.get("formula") == 0:
        # EA identifies the original modern F1 cars as formula 0, and the
        # 2026 cars as formula 13, including in the legacy session prefix.
        detection = "session_formula_2025"
    elif latest.get("f1_25_detected") and latest.get("formula") in (None, 0):
        detection = "participants_2025_team_id"
    else:
        detection = "legacy_udp_unconfirmed"
    latest.update({
        "edition_detection": detection,
        "udp_configuration_warning": (
            "Waiting for Session or Participants packets to identify F1 25 versus "
            "the 2026 Season Pack automatically. The F1 25 UDP header alone is ambiguous."
            if detection == "legacy_udp_unconfirmed" else None),
        "game_year": 26 if packet_format == 2026 else raw_game_year,
        "packet_format": packet_format, "game_version": game_version,
        "raw_packet_format": raw_packet_format, "raw_game_year": raw_game_year,
    })

def edition_status(latest):
    """Small public status used by the recording panel and saved-lap metadata."""
    source = latest.get("edition_detection", "unknown")
    confirmed = source not in ("unknown", "legacy_udp_unconfirmed")
    version = latest.get("game_version", "unknown")
    label = ("F1 25 · 2026 Season Pack" if version == "F1 26" else "F1 25")
    if not confirmed:
        label = "Detecting F1 25 / 2026 Season Pack" if latest.get("raw_packet_format") else "Waiting for game"
    return {"label": label, "confirmed": confirmed, "source": source,
            "wire_format": latest.get("raw_packet_format"), "formula": latest.get("formula"),
            "warning": latest.get("udp_configuration_warning")}

def _receive_packet(sock, stop_event=None):
    """Allow the desktop window to stop reception before draining saved laps."""
    if stop_event is not None:
        sock.settimeout(0.25)
    while stop_event is None or not stop_event.is_set():
        try:
            data, _ = sock.recvfrom(4096)
            return data
        except socket.timeout:
            continue
        except OSError:
            if stop_event is not None and stop_event.is_set():
                return None
            raise
    return None


def udp_loop(latest, recorder=None, sock=None, stop_event=None):
    if sock is None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("0.0.0.0", PORT))
        except OSError:
            sock.close()
            raise

    while True:
        data = _receive_packet(sock, stop_event)
        if data is None:
            sock.close()
            break

        if len(data) < HEADER_SIZE:
            continue

        raw_packet_format = struct.unpack_from("<H", data, 0)[0]
        raw_game_year = data[2]
        if raw_packet_format not in CAR_RECORD_SIZES:
            continue
        incoming_session_uid = struct.unpack_from("<Q", data, 7)[0]
        packet_id = data[6]
        player_car_index = data[27]
        record_size = CAR_RECORD_SIZES[raw_packet_format].get(packet_id)
        if record_size is not None and car_record_offset(
                data, player_car_index, record_size,
                24 if raw_packet_format == 2026 else 22) is None:
            continue
        identity = parse_session_identity(data) if packet_id == SESSION_PACKET_ID else None
        if packet_id == SESSION_PACKET_ID and identity is None:
            continue
        participants = (parse_participants_summary(data, raw_packet_format)
                        if packet_id == PARTICIPANTS_PACKET_ID else None)
        if packet_id == PARTICIPANTS_PACKET_ID and participants is None:
            continue
        if packet_id == CAR_TELEMETRY2_PACKET_ID and parse_car_telemetry2(data, player_car_index) is None:
            continue
        old_link = latest.get("session_link_identifier")
        new_session = (latest.get("session_uid") != incoming_session_uid or
                       (identity is not None and old_link is not None and
                        old_link != identity["session_link_identifier"]) or
                       (identity is not None and latest.get("track_id") is not None and
                        latest["track_id"] != identity["track_id"]) or
                       (identity is not None and latest.get("formula") is not None and
                        latest["formula"] != identity["formula"]))
        if new_session:
            latest.clear()
            latest.update(copy.deepcopy(DEFAULT_TELEMETRY_STATE))
            recording_health.reset(incoming_session_uid)
        latest["session_uid"] = incoming_session_uid
        latest["player_car_index"] = player_car_index
        if identity is not None:
            latest.update(identity)
        evidence = season_pack_packet_evidence(
            packet_id, data, player_car_index, raw_packet_format
        )
        if evidence:
            latest["season_pack_detected"] = True
            latest["season_pack_detection"] = evidence
        if participants is not None:
            latest["num_active_cars"] = participants["num_active_cars"]
            latest["participant_team_ids"] = participants["team_ids"]
            latest["f1_25_detected"] = bool(set(participants["team_ids"]) & F1_2025_TEAM_IDS)
        update_edition_detection(latest, raw_packet_format, raw_game_year)
        packet_format = latest["packet_format"]

        # Packet format controls the wire layout. Edition detection is kept
        # separate because Season Pack can report a 2025/25 common header.
        if raw_packet_format == 2025:
            CAR_TELEMETRY_DATA_SIZE = 60
            CAR_STATUS_DATA_SIZE = 55
            LAP_DATA_SIZE_CURRENT = 57

        elif raw_packet_format == 2026:
            CAR_TELEMETRY_DATA_SIZE = 59
            CAR_STATUS_DATA_SIZE = 59
            LAP_DATA_SIZE_CURRENT = 57
        else:
            continue

        if packet_id == CAR_TELEMETRY_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * CAR_TELEMETRY_DATA_SIZE

            if not has_bytes(data, offset, CAR_TELEMETRY_STRUCT.size):
                continue

            speed, throttle, _, brake, _, _, _, drs = CAR_TELEMETRY_STRUCT.unpack_from(data, offset)
            if not all(math.isfinite(value) for value in (throttle, brake)):
                continue

            latest["speed"] = speed

            if latest["game_version"] == "F1 26":
                latest["drs"] = 0
                if not latest.get("telemetry2_received"):
                    latest["aero"] = drs
            else:
                latest["drs"] = drs
                latest["aero"] = 0

            latest["throttle_raw"] = throttle
            latest["brake_raw"] = brake

        elif packet_id == LAP_DATA_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * LAP_DATA_SIZE_CURRENT

            if not has_bytes(data, offset + 4, 4):
                continue

            current_lap_time_ms = struct.unpack_from("<I", data, offset + 4)[0]
            lap_distance = struct.unpack_from("<f", data, offset + 20)[0]
            if not math.isfinite(lap_distance):
                continue
            session_time = struct.unpack_from("<f", data, 15)[0]
            if not math.isfinite(session_time):
                continue
            previous_clock = latest.get("lap_packet_session_time")
            if previous_clock is not None and session_time < previous_clock - .001:
                # Other packet groups may still describe the undone future.
                # Leave missing measurements until their restored packets arrive.
                for key in ("speed", "throttle_raw", "brake_raw", "world_position_x",
                            "world_position_y", "world_position_z", "longitudinal_g",
                            "wheel_speed", "wheel_slip_ratio", "tyres_wear", "tyres_age_laps",
                            "fuel_in_tank_kg", "fuel_remaining_laps", "ers_store_energy_j",
                            "ers_percent", "ers_mguk_power", "ers_mode", "boost_active",
                            "overtake_active", "overtake_available", "aero_mode", "aero", "drs",
                            "active_aero_available", "active_aero_activation_distance",
                            "overtake_activation_distance", "regulations_2026"):
                    latest[key] = copy.deepcopy(DEFAULT_TELEMETRY_STATE.get(key))
                latest["telemetry2_received"] = False
                latest["ers_percent"] = None
            latest["lap_packet_session_time"] = session_time
            latest["last_lap_time_ms"] = struct.unpack_from("<I", data, offset)[0]
            # F1 25/26 LapData includes minute parts for sector/delta fields.
            # This places lapDistance at 20, currentLapNum at 33, pitStatus at
            # 34 and currentLapInvalid at 37 (all relative to the car record).
            latest["lap_distance"] = lap_distance
            if has_bytes(data, offset + 34, 1):
                latest["lap_number"] = data[offset + 33]
                latest["pit_status"] = data[offset + 34]
            if has_bytes(data, offset + 37, 1): latest["lap_invalid"] = bool(data[offset + 37])
            latest["current_lap_time_ms"] = current_lap_time_ms

        elif packet_id == MOTION_PACKET_ID:
            motion = parse_car_motion(data, player_car_index, raw_packet_format)
            if motion is None:
                continue
            latest.update(motion)

        elif packet_id == MOTION_EX_PACKET_ID:
            # PacketMotionEx: suspension position/velocity/acceleration, then wheel speed and slip ratio.
            offset = HEADER_SIZE
            if not has_bytes(data, offset, 244):
                continue
            wheels = struct.unpack_from("<8f", data, offset + 48)
            if not all(math.isfinite(value) for value in wheels):
                continue
            latest["wheel_speed"] = list(wheels[:4])
            latest["wheel_slip_ratio"] = list(wheels[4:])

        elif packet_id == CAR_DAMAGE_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * CAR_DAMAGE_DATA_SIZE
            wear = struct.unpack_from("<4f", data, offset)
            if not all(math.isfinite(value) for value in wear):
                continue
            latest["tyres_wear"] = list(wear)

        elif packet_id == SESSION_PACKET_ID:
            if identity is None:
                continue

        elif packet_id == CAR_SETUPS_PACKET_ID:
            setup = parse_car_setup(data, player_car_index, raw_packet_format)
            if setup is None:
                continue
            latest["car_setup"] = setup

        elif packet_id == CAR_STATUS_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * CAR_STATUS_DATA_SIZE

            if not has_bytes(data, offset + 41, 1):
                continue
            fuel = struct.unpack_from("<3f", data, offset + 5)
            mguk_power, ers_store_energy = struct.unpack_from("<2f", data, offset + 33)
            if not all(math.isfinite(value) for value in (*fuel, mguk_power, ers_store_energy)):
                continue

            actual_compound = struct.unpack_from("<B", data, offset + 25)[0]
            visual_compound = struct.unpack_from("<B", data, offset + 26)[0]
            latest["tyre_compound"] = tyre_compound_name(actual_compound, visual_compound)
            latest["tyres_age_laps"] = struct.unpack_from("<B", data, offset + 27)[0]

            latest["fuel_in_tank_kg"], latest["fuel_capacity_kg"], latest["fuel_remaining_laps"] = fuel
            latest["ers_mguk_power"] = mguk_power
            latest["ers_store_energy_j"] = ers_store_energy
            latest["ers_percent"] = round((ers_store_energy / 4000000) * 100)
            ers_mode = data[offset + 41]
            latest["ers_mode"] = ers_mode
            # Mode 3 is Boost in the 2026 wire schema and Overtake in the
            # selectable legacy F1 25 wire schema.
            activity = ers_activity_for_wire_mode(raw_packet_format, ers_mode)
            latest["boost_active"] = activity["boost_active"]
            if raw_packet_format == 2025 and not latest.get("telemetry2_received"):
                latest["overtake_active"] = activity["legacy_overtake_active"]

        elif packet_id == CAR_TELEMETRY2_PACKET_ID and packet_format == 2026:
            telemetry2 = parse_car_telemetry2(data, player_car_index)
            if telemetry2 is None:
                continue
            latest["aero_mode"] = telemetry2["active_aero_mode"]
            latest["aero"] = int(telemetry2["active_aero_mode"] > 0)
            latest["active_aero_available"] = telemetry2["active_aero_available"]
            latest["active_aero_activation_distance"] = telemetry2["active_aero_activation_distance"]
            latest["overtake_available"] = telemetry2["overtake_available"]
            latest["overtake_active"] = telemetry2["overtake_active"]
            latest["overtake_activation_distance"] = telemetry2["overtake_activation_distance"]
            latest["regulations_2026"] = telemetry2["regulations_2026"]
            latest["driving_wrong_way"] = telemetry2["driving_wrong_way"]
            latest["telemetry2_received"] = True

        health_sizes = {
            MOTION_PACKET_ID: HEADER_SIZE + (player_car_index + 1) * (
                MOTION_DATA_SIZE_2026 if raw_packet_format == 2026 else MOTION_DATA_SIZE_2025),
            SESSION_PACKET_ID: HEADER_SIZE + SESSION_GAME_MODE_OFFSET + 1,
            PARTICIPANTS_PACKET_ID: HEADER_SIZE + 1,
            LAP_DATA_PACKET_ID: HEADER_SIZE + player_car_index * LAP_DATA_SIZE_CURRENT + 38,
            CAR_SETUPS_PACKET_ID: HEADER_SIZE + player_car_index * CAR_SETUP_STRUCT.size + CAR_SETUP_STRUCT.size,
            CAR_TELEMETRY_PACKET_ID: HEADER_SIZE + player_car_index * CAR_TELEMETRY_DATA_SIZE + CAR_TELEMETRY_STRUCT.size,
            CAR_STATUS_PACKET_ID: HEADER_SIZE + player_car_index * CAR_STATUS_DATA_SIZE + 42,
            CAR_DAMAGE_PACKET_ID: HEADER_SIZE + player_car_index * CAR_DAMAGE_DATA_SIZE + 16,
            MOTION_EX_PACKET_ID: HEADER_SIZE + 244,
            CAR_TELEMETRY2_PACKET_ID: HEADER_SIZE + player_car_index * CAR_TELEMETRY2_DATA_SIZE + CAR_TELEMETRY2_DATA_SIZE,
        }
        if (packet_id in health_sizes and len(data) >= health_sizes[packet_id]
                and (packet_id != CAR_TELEMETRY2_PACKET_ID or packet_format == 2026)):
            recording_health.received(packet_id, incoming_session_uid)

        # Lap Data is the recorder's timing/distance clock.  Sampling only on
        # this packet keeps the latest values from the other packet types but
        # avoids copying and inspecting state for every UDP datagram.
        if recorder is not None and packet_id == LAP_DATA_PACKET_ID:
            recorder.observe(latest.copy())
