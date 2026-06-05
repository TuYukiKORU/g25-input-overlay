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
LAP_DATA_PACKET_ID = 2
LAP_DATA_SIZE = 57
CAR_STATUS_PACKET_ID = 7

def udp_loop(latest):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))

    while True:
        data, addr = sock.recvfrom(4096)

        packet_format = struct.unpack_from("<H", data, 0)[0]

        CAR_TELEMETRY_DATA_SIZE = 60 if packet_format == 2025 else 59
        CAR_STATUS_DATA_SIZE = 55 if packet_format == 2025 else 59

        packet_id = data[6]
        player_car_index = data[27]

        if packet_id == CAR_TELEMETRY_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * CAR_TELEMETRY_DATA_SIZE

            speed, throttle, steer, brake, clutch, gear, rpm, drs = struct.unpack_from(
                "<HfffBbHB",
                data,
                offset
            )

            latest["speed"] = speed
            latest["gear"] = gear
            latest["throttle"] = round(throttle * 100)
            latest["brake"] = round(brake * 100)
            latest["steer"] = round(steer, 2)
            latest["rpm"] = rpm
            latest["drs"] = drs
            latest["updated"] = time.time()

        elif packet_id == LAP_DATA_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * LAP_DATA_SIZE

            current_lap_time_ms = struct.unpack_from("<I", data, offset + 4)[0]

            latest["lap_time"] = format_lap_time(current_lap_time_ms)

        elif packet_id == CAR_STATUS_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * CAR_STATUS_DATA_SIZE

            ers_store_energy = struct.unpack_from("<f", data, offset + 37)[0]
            ers_deploy_mode = struct.unpack_from("<B", data, offset + 41)[0]

            # 最大4MJとして％表示
            latest["ers_percent"] = round((ers_store_energy / 4000000) * 100)

            # 0 = none, 1 = medium, 2 = hotlap, 3 = overtake
            latest["ers"] = 1 if ers_deploy_mode > 2 else 0
