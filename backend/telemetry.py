import socket
import struct
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
F1_2026_ONLY_TRACK_IDS = frozenset({42})  # Madrid
LAP_DATA_PACKET_ID = 2
CAR_STATUS_PACKET_ID = 7
CAR_SETUPS_PACKET_ID = 5
CAR_SETUP_STRUCT = struct.Struct("<BBBBffffBBBBBBBBBffffBf")
SESSION_PACKET_ID = 1
MOTION_PACKET_ID = 0
MOTION_LONGITUDINAL_G_OFFSET = 40
MOTION_EX_PACKET_ID = 13
CAR_DAMAGE_PACKET_ID = 10
CAR_DAMAGE_DATA_SIZE = 46
CAR_TELEMETRY_STRUCT = struct.Struct("<HfffBbHB")

# PacketSessionData offset after marshal zones and weather forecast samples.
SESSION_GAME_MODE_OFFSET = 665
SESSION_SEASON_LINK_OFFSET = 641
SESSION_WEEKEND_LINK_OFFSET = 645
SESSION_LINK_OFFSET = 649

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

def parse_car_setup(data, player_car_index):
    """Decode only the player's compact 50-byte setup record."""
    offset = HEADER_SIZE + player_car_index * CAR_SETUP_STRUCT.size
    if not has_bytes(data, offset, CAR_SETUP_STRUCT.size):
        return None
    return dict(zip(CAR_SETUP_FIELDS, CAR_SETUP_STRUCT.unpack_from(data, offset)))

def parse_car_telemetry2(data, player_car_index):
    """Decode the official 2026-only active-aero and Overtake fields."""
    offset = HEADER_SIZE + player_car_index * CAR_TELEMETRY2_STRUCT.size
    if not has_bytes(data, offset, CAR_TELEMETRY2_STRUCT.size):
        return None
    values = CAR_TELEMETRY2_STRUCT.unpack_from(data, offset)
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
    offset = HEADER_SIZE + player_car_index * CAR_TELEMETRY2_DATA_SIZE
    return (packet_id == CAR_TELEMETRY2_PACKET_ID
            and has_bytes(data, offset, CAR_TELEMETRY2_DATA_SIZE))

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

    count = min(active_cars, max_cars)
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
            if raw_packet_format == 2025 and team_ids & LEGACY_2026_F1_TEAM_IDS:
                return "participants_2026_team_id"
            if raw_packet_format == 2026 and team_ids & F1_2026_TEAM_IDS:
                return "participants_2026_team_id"
    if packet_id == SESSION_PACKET_ID:
        identity = parse_session_identity(data)
        if identity and identity["track_id"] in F1_2026_ONLY_TRACK_IDS:
            return "2026_only_track"
    return None

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
        incoming_session_uid = struct.unpack_from("<Q", data, 7)[0]
        if latest.get("session_uid") != incoming_session_uid:
            latest["track_id"] = None
            latest["session_type"] = None
            latest["game_mode"] = None
            latest["season_link_identifier"] = None
            latest["weekend_link_identifier"] = None
            latest["session_link_identifier"] = None
            latest["car_setup"] = None
            latest["season_pack_detected"] = False
            latest["season_pack_detection"] = None
            latest["num_active_cars"] = None
            latest["participant_team_ids"] = []
            latest["boost_active"] = 0
            latest["overtake_available"] = 0
            latest["overtake_active"] = 0
            latest["aero_mode"] = 0
            latest["active_aero_available"] = 0
            latest["active_aero_activation_distance"] = 0
            latest["overtake_activation_distance"] = 0
            latest["regulations_2026"] = 0
            latest["driving_wrong_way"] = 0
            latest["telemetry2_received"] = False

        packet_id = data[6]
        player_car_index = data[27]
        evidence = season_pack_packet_evidence(
            packet_id, data, player_car_index, raw_packet_format
        )
        if evidence:
            latest["season_pack_detected"] = True
            latest["season_pack_detection"] = evidence
        if packet_id == PARTICIPANTS_PACKET_ID:
            participants = parse_participants_summary(data, raw_packet_format)
            if participants:
                latest["num_active_cars"] = participants["num_active_cars"]
                latest["participant_team_ids"] = participants["team_ids"]
        packet_format, game_version = telemetry_mode(
            raw_packet_format, raw_game_year, latest.get("season_pack_detected", False)
        )
        if raw_packet_format == 2026 or raw_game_year == 26:
            latest["edition_detection"] = "udp_header"
        elif latest.get("season_pack_detected"):
            latest["edition_detection"] = latest.get("season_pack_detection") or "packet_evidence"
        else:
            # Legacy UDP does not identify whether the game content is 2025 or
            # 2026, so this is an unconfirmed schema rather than a car edition.
            latest["edition_detection"] = "legacy_udp_unconfirmed"
        latest["udp_configuration_warning"] = (
            "UDP format is set to F1 25 and no 2026-only signal has been seen yet. "
            "Automatic detection may become available from the grid/track data; selecting "
            "the 2026 Season Pack UDP format remains the most reliable setting."
            if latest["edition_detection"] == "legacy_udp_unconfirmed" else None
        )
        latest["game_year"] = 26 if packet_format == 2026 else raw_game_year
        latest["packet_format"] = packet_format
        latest["game_version"] = game_version
        latest["raw_packet_format"] = raw_packet_format
        latest["raw_game_year"] = raw_game_year
        latest["session_uid"] = incoming_session_uid

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

            latest["speed"] = speed

            if latest["game_version"] == "F1 26":
                latest["drs"] = 0
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
            latest["last_lap_time_ms"] = struct.unpack_from("<I", data, offset)[0]
            # F1 25/26 LapData includes minute parts for sector/delta fields.
            # This places lapDistance at 20, currentLapNum at 33, pitStatus at
            # 34 and currentLapInvalid at 37 (all relative to the car record).
            if has_bytes(data, offset + 20, 4): latest["lap_distance"] = struct.unpack_from("<f", data, offset + 20)[0]
            if has_bytes(data, offset + 34, 1):
                latest["lap_number"] = data[offset + 33]
                latest["pit_status"] = data[offset + 34]
            if has_bytes(data, offset + 37, 1): latest["lap_invalid"] = bool(data[offset + 37])
            latest["current_lap_time_ms"] = current_lap_time_ms

        elif packet_id == MOTION_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * 60
            if has_bytes(data, offset, 12):
                latest["world_position_x"], _, latest["world_position_z"] = struct.unpack_from("<3f", data, offset)
            if has_bytes(data, offset + MOTION_LONGITUDINAL_G_OFFSET, 4):
                latest["longitudinal_g"] = struct.unpack_from("<f", data, offset + MOTION_LONGITUDINAL_G_OFFSET)[0]

        elif packet_id == MOTION_EX_PACKET_ID:
            # PacketMotionEx: suspension position/velocity/acceleration, then wheel speed and slip ratio.
            offset = HEADER_SIZE
            if has_bytes(data, offset + 48, 32):
                latest["wheel_speed"] = list(struct.unpack_from("<4f", data, offset + 48))
                latest["wheel_slip_ratio"] = list(struct.unpack_from("<4f", data, offset + 64))

        elif packet_id == CAR_DAMAGE_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * CAR_DAMAGE_DATA_SIZE
            if has_bytes(data, offset, 16): latest["tyres_wear"] = list(struct.unpack_from("<4f", data, offset))

        elif packet_id == SESSION_PACKET_ID:
            identity = parse_session_identity(data)
            if identity is not None:
                incoming_track_id = identity["track_id"]
                if latest.get("track_id") != incoming_track_id:
                    latest["car_setup"] = None
                previous_link = latest.get("session_link_identifier")
                latest.update(identity)
                if previous_link is not None and previous_link != identity["session_link_identifier"]:
                    latest["car_setup"] = None

        elif packet_id == CAR_SETUPS_PACKET_ID:
            setup = parse_car_setup(data, player_car_index)
            if setup is not None:
                latest["car_setup"] = setup

        elif packet_id == CAR_STATUS_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * CAR_STATUS_DATA_SIZE

            if not has_bytes(data, offset + 41, 1):
                continue

            actual_compound = struct.unpack_from("<B", data, offset + 25)[0]
            visual_compound = struct.unpack_from("<B", data, offset + 26)[0]
            latest["tyre_compound"] = tyre_compound_name(actual_compound, visual_compound)
            latest["tyres_age_laps"] = struct.unpack_from("<B", data, offset + 27)[0]

            if has_bytes(data, offset + 5, 12):
                latest["fuel_in_tank_kg"] = struct.unpack_from("<f", data, offset + 5)[0]
                latest["fuel_capacity_kg"] = struct.unpack_from("<f", data, offset + 9)[0]
                latest["fuel_remaining_laps"] = struct.unpack_from("<f", data, offset + 13)[0]
            latest["ers_mguk_power"] = struct.unpack_from("<f", data, offset + 33)[0]
            ers_store_energy = struct.unpack_from("<f", data, offset + 37)[0]
            latest["ers_store_energy_j"] = ers_store_energy
            latest["ers_percent"] = round((ers_store_energy / 4000000) * 100)
            ers_mode = data[offset + 41]
            latest["ers_mode"] = ers_mode
            # Mode 3 is Boost in the 2026 wire schema and Overtake in the
            # selectable legacy F1 25 wire schema.
            activity = ers_activity_for_wire_mode(raw_packet_format, ers_mode)
            latest["boost_active"] = activity["boost_active"]
            if raw_packet_format == 2025:
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
            MOTION_PACKET_ID: HEADER_SIZE + player_car_index * 60 + MOTION_LONGITUDINAL_G_OFFSET + 4,
            SESSION_PACKET_ID: HEADER_SIZE + SESSION_GAME_MODE_OFFSET + 1,
            LAP_DATA_PACKET_ID: HEADER_SIZE + player_car_index * LAP_DATA_SIZE_CURRENT + 38,
            CAR_SETUPS_PACKET_ID: HEADER_SIZE + player_car_index * CAR_SETUP_STRUCT.size + CAR_SETUP_STRUCT.size,
            CAR_TELEMETRY_PACKET_ID: HEADER_SIZE + player_car_index * CAR_TELEMETRY_DATA_SIZE + CAR_TELEMETRY_STRUCT.size,
            CAR_STATUS_PACKET_ID: HEADER_SIZE + player_car_index * CAR_STATUS_DATA_SIZE + 42,
            CAR_DAMAGE_PACKET_ID: HEADER_SIZE + player_car_index * CAR_DAMAGE_DATA_SIZE + 16,
            MOTION_EX_PACKET_ID: HEADER_SIZE + 80,
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
