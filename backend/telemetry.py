import socket
import struct
import time

def format_lap_time(ms):
    minutes = ms // 60000
    seconds = (ms % 60000) / 1000
    return f"{minutes}:{seconds:06.3f}"

PORT = 20777
HEADER_SIZE = 29
CAR_TELEMETRY_PACKET_ID = 6
CAR_TELEMETRY2_PACKET_ID = 16
CAR_TELEMETRY2_DATA_SIZE = 10
LAP_DATA_PACKET_ID = 2
CAR_STATUS_PACKET_ID = 7
CAR_TELEMETRY_STRUCT = struct.Struct("<HfffBbHB")

def has_bytes(data, offset, size):
    return offset >= 0 and len(data) >= offset + size

def udp_loop(latest):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))

    while True:
        data, addr = sock.recvfrom(4096)

        if len(data) < HEADER_SIZE:
            continue

        packet_format = struct.unpack_from("<H", data, 0)[0]

        if packet_format == 2025:
            latest["game_version"] = "F1 25"
            CAR_TELEMETRY_DATA_SIZE = 60
            CAR_STATUS_DATA_SIZE = 55
            LAP_DATA_SIZE_CURRENT = 57

        elif packet_format == 2026:
            latest["game_version"] = "F1 26"
            CAR_TELEMETRY_DATA_SIZE = 59
            CAR_STATUS_DATA_SIZE = 59
            LAP_DATA_SIZE_CURRENT = 57
        else:
            continue

        packet_id = data[6]
        player_car_index = data[27]

        if packet_id == CAR_TELEMETRY_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * CAR_TELEMETRY_DATA_SIZE

            if not has_bytes(data, offset, CAR_TELEMETRY_STRUCT.size):
                continue

            speed, throttle, steer, brake, clutch, gear, rpm, drs = CAR_TELEMETRY_STRUCT.unpack_from(data, offset)

            latest["speed"] = speed
            latest["gear"] = gear
            latest["throttle"] = round(throttle * 100)
            latest["brake"] = round(brake * 100)
            latest["steer"] = round(steer, 2)
            latest["rpm"] = rpm

            if latest["game_version"] == "F1 26":
                latest["drs"] = 0
                latest["aero"] = drs
            else:
                latest["drs"] = drs
                latest["aero"] = 0

            latest["updated"] = time.time()

        elif packet_id == LAP_DATA_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * LAP_DATA_SIZE_CURRENT

            if not has_bytes(data, offset + 4, 4):
                continue

            current_lap_time_ms = struct.unpack_from("<I", data, offset + 4)[0]

            latest["lap_time"] = format_lap_time(current_lap_time_ms)

        elif packet_id == CAR_STATUS_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * CAR_STATUS_DATA_SIZE

            if not has_bytes(data, offset + 41, 1):
                continue

            if latest["game_version"] == "F1 26":
                ers_store_energy = struct.unpack_from("<f", data, offset + 37)[0]
                ers_deploy_mode = struct.unpack_from("<B", data, offset + 41)[0]

                latest["ers_percent"] = round((ers_store_energy / 4000000) * 100)
                latest["ers_mode"] = ers_deploy_mode
                latest["ers"] = 1 if ers_deploy_mode > 0 else 0
                latest["boost"] = 1 if ers_deploy_mode == 3 else 0

            else:
                ers_store_energy = struct.unpack_from("<f", data, offset + 37)[0]
                ers_deploy_mode = struct.unpack_from("<B", data, offset + 41)[0]

                latest["ers_percent"] = round((ers_store_energy / 4000000) * 100)
                latest["ers_mode"] = ers_deploy_mode
                latest["ers"] = 1 if ers_deploy_mode > 2 else 0
                latest["boost"] = 0

        elif packet_id == CAR_TELEMETRY2_PACKET_ID and packet_format == 2026:
            offset = HEADER_SIZE + player_car_index * CAR_TELEMETRY2_DATA_SIZE

            if not has_bytes(data, offset + 5, 1):
                continue

            aero_mode = struct.unpack_from("<B", data, offset + 0)[0]
            aero_available = struct.unpack_from("<B", data, offset + 1)[0]
            aero_distance = struct.unpack_from("<H", data, offset + 2)[0]
            overtake_active = struct.unpack_from("<B", data, offset + 5)[0]

            latest["aero_mode"] = aero_mode
            latest["aero_available"] = aero_available
            latest["aero_distance"] = aero_distance
            latest["overtake_active"] = overtake_active
