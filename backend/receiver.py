import socket
import struct
import time

PORT = 20777
HEADER_SIZE = 29
CAR_TELEMETRY_PACKET_ID = 6
CAR_TELEMETRY_DATA_SIZE = 60

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", PORT))
sock.settimeout(1.0)

print(f"Listening UDP on port {PORT}...")

last_print = 0

try:
    while True:
        try:
            data, addr = sock.recvfrom(4096)

            packet_id = data[6]
            player_car_index = data[27]

            if packet_id != CAR_TELEMETRY_PACKET_ID:
                continue

            offset = HEADER_SIZE + player_car_index * CAR_TELEMETRY_DATA_SIZE

            speed, throttle, steer, brake, clutch, gear, rpm, drs = struct.unpack_from(
                "<HfffBbHB",
                data,
                offset
            )

            now = time.time()
            if now - last_print > 0.2:
                print(
                    f"speed={speed:3d} km/h | "
                    f"gear={gear:2d} | "
                    f"throttle={throttle*100:5.1f}% | "
                    f"brake={brake*100:5.1f}% | "
                    f"steer={steer: .2f} | "
                    f"rpm={rpm} | "
                    f"drs={drs} | "
                )
                last_print = now

        except socket.timeout:
            pass

except KeyboardInterrupt:
    print("\nstopped")

finally:
    sock.close()