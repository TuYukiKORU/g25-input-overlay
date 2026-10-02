"""Monotonic receipt times for decoded packet groups."""
import threading
import time


PACKETS = {0: ("Motion", 2), 1: ("Session", 5), 2: ("Lap timing", 2),
           5: ("Setup", 10), 6: ("Controls", 2), 7: ("Fuel / tyres / ERS", 3),
           10: ("Tyre wear", 5), 13: ("Wheel slip", 2), 16: ("2026 aero / boost", 2)}


class RecordingHealth:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.session = None
        self.receipts = {}
        self.lock = threading.Lock()

    def received(self, packet_id, session_uid):
        if packet_id not in PACKETS:
            return
        with self.lock:
            if self.session != session_uid:
                self.receipts.clear()
                self.session = session_uid
            self.receipts[packet_id] = self.clock()

    def snapshot(self, season_pack=False):
        with self.lock:
            now, values = self.clock(), self.receipts.copy()
        groups = []
        for packet_id, (label, limit) in PACKETS.items():
            if packet_id == 16 and not season_pack:
                continue
            age = now - values[packet_id] if packet_id in values else None
            groups.append({"name": label, "packet_id": packet_id, "age_s": round(age, 1) if age is not None else None,
                           "state": "missing" if age is None else "stale" if age > limit else "receiving"})
        ages = [now - timestamp for timestamp in values.values()]
        return {"state": "waiting" if not ages else "receiving" if min(ages) <= 3 else "stale",
                "groups": groups, "notice": "Receipt age measures incoming packets. Paused games and stopped sessions can appear stale."}


recording_health = RecordingHealth()
