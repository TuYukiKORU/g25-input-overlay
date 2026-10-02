"""Generate a reference lap and a slower wheel-spin lap for UI testing."""
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from storage import LapStorage
from analysis_config import tyre_values


def make_lap(number, slow=False):
    samples = []
    for distance in range(0, 5001, 5):
        spin = slow and 3000 <= distance <= 3040
        loss = 180 if slow and distance >= 3040 else 0
        angle = distance / 5000 * math.tau
        samples.append({"lap_distance": float(distance),
            "lap_time_ms": round(distance / 5000 * 90000 + loss), "position": {"x": 400*math.cos(angle), "z": 220*math.sin(angle)},
            "speed": 200, "throttle": .8, "brake": 0,
            "wheel_speed": tyre_values([56,56,55,55]), "wheel_slip_ratio": tyre_values([.28 if spin else .03,.25 if spin else .03,.01,.01]),
            "tyre_wear": tyre_values([5+distance/1500,5+distance/1500,4+distance/1800,4+distance/1800])})
    duration = 90180 if slow else 90000
    return {"packetFormat": 2025, "trackId": 0, "sessionType": 1, "lapNumber": number, "lapTimeMs": duration, "validLap": True,
            "tyreWearAtStart": samples[0]["tyre_wear"], "tyreWearAtEnd": samples[-1]["tyre_wear"], "sampleCount": len(samples),
            "createdAt": datetime.now(timezone.utc).isoformat(), "samples": samples}


if __name__ == "__main__":
    storage = LapStorage(); storage.start_session({"packetFormat": 2025, "trackId": 0, "sessionType": 1})
    storage.save_lap(make_lap(1)); storage.save_lap(make_lap(2, True))
    print(f"Sample laps written to {storage.session_dir}")
