"""Non-blocking, distance-sampled lap recorder."""
import copy
import logging
import queue
import threading
from datetime import datetime, timezone
from uuid import uuid4
from analysis_config import ANALYSIS_CONFIG, tyre_values
from session_names import game_mode_name, session_type_name


class LapRecorder:
    """Build laps on the UDP thread and persist completed laps on a writer thread."""
    def __init__(self, storage):
        self.storage = storage
        self.current = None
        self.last_distance = None
        self._previous_lap = None
        self._session_key = None
        self._last_clock = None
        self._last_timing = None
        self._queue = queue.Queue(maxsize=8)
        self._status_lock = threading.Lock()
        self._save_errors = 0
        self._queue_overflows = 0
        threading.Thread(target=self._writer, daemon=True, name="lap-writer").start()

    def persistence_status(self):
        """Save errors remain visible for this run, even after packet receipt recovers."""
        with self._status_lock:
            return {"ok": not (self._save_errors or self._queue_overflows),
                    "save_errors": self._save_errors, "queue_overflows": self._queue_overflows,
                    "pending_laps": self._queue.unfinished_tasks}

    def _save_failed(self, overflow=False):
        with self._status_lock:
            if overflow:
                self._queue_overflows += 1
            else:
                self._save_errors += 1

    def _writer(self):
        while True:
            lap = self._queue.get()
            try:
                if not lap.pop("_needs_finalize", False) or self._finalize_lap(lap):
                    self.storage.save_lap(lap)
            except Exception:
                self._save_failed()
                logging.exception("Could not persist completed lap")
            finally:
                self._queue.task_done()

    def flush(self, timeout=10):
        """Wait for completed laps already queued for disk, with a deadline."""
        with self._queue.all_tasks_done:
            drained = self._queue.all_tasks_done.wait_for(
                lambda: self._queue.unfinished_tasks == 0, timeout=timeout)
        return drained and self.persistence_status()["ok"]

    def observe(self, state):
        """Consume a coherent snapshot; never performs file I/O on the caller."""
        if state.get("paused"):
            return
        lap_no = state.get("lap_number")
        distance = state.get("lap_distance")
        if not isinstance(lap_no, int) or lap_no <= 0 or distance is None:
            return
        track_id = state.get("track_id")
        if not isinstance(track_id, int) or track_id < 0:
            return
        session_key = (state.get("session_uid"), track_id, state.get("session_link_identifier"), state.get("session_type"))
        if session_key != self._session_key:
            self.current = None; self.last_distance = None
            self._previous_lap = None
            self._last_clock = None
            self._last_timing = None
            self._session_key = session_key
        clock = state.get("lap_packet_session_time")
        clock_rewound = (clock is not None and self._last_clock is not None
                         and clock < self._last_clock - .001)
        elapsed = state.get("current_lap_time_ms") or 0
        timing_rewound = bool(self.current and self._last_timing
                              and lap_no == self.current["lapNumber"]
                              and elapsed < self._last_timing[1]
                              and distance <= self._last_timing[0])
        # The session clock distinguishes a flashback near the start line from
        # a Time Trial lap whose number did not change at the crossing.
        rewind = clock_rewound or (clock is None and timing_rewound
                                  and not (distance < 100 and self.last_distance is not None
                                           and self.last_distance > 1000
                                           and state.get("session_type") not in (15, 16, 17)))
        if self.current and lap_no < self.current["lapNumber"]:
            # Never finish a lap using timing from an earlier lap. A short
            # flashback across the line can reuse the previous lap's prefix.
            previous = self._previous_lap
            self.current = (self._lap_snapshot(previous) if previous
                            and previous["lapNumber"] == lap_no
                            and (clock_rewound or clock is None) else None)
            self.last_distance = None
            rewind = self.current is not None
        if self.current and rewind and lap_no == self.current["lapNumber"]:
            self._splice_rewind(state)
        self._last_clock = clock
        self._last_timing = (distance, elapsed)
        season_pack = (state.get("packet_format") == 2026 or state.get("game_year") == 26
                       or state.get("game_version") == "F1 26")
        if self.current and season_pack:
            # Telemetry2 may establish the edition after the first sample of a
            # lap. Promote the in-progress lap instead of leaving stale F1 25
            # metadata on disk.
            self.current.update({"packetFormat": 2026, "gameYear": 26,
                                 "gameVersion": "F1 26", "udpMode": "2026 Season Pack",
                                 "editionDetection": state.get("edition_detection", "udp_header"),
                                 "udpConfigurationWarning": None})
        if self.current:
            # Identification can arrive after the first timing packet for
            # either season. Keep its evidence and warning current.
            self.current.update({"editionDetection": state.get("edition_detection", "unknown"),
                                 "udpConfigurationWarning": state.get("udp_configuration_warning"),
                                 "formula": state.get("formula"),
                                 "sourcePacketFormat": state.get("raw_packet_format", state.get("packet_format")),
                                 "sourceGameYear": state.get("raw_game_year", state.get("game_year"))})
        if self.current and lap_no != self.current["lapNumber"]:
            self._finish(state)
        elif self.last_distance is not None and distance < self.last_distance - 100:
            previous_time = (self.current["samples"][-1].get("lap_time_ms")
                             if self.current and self.current["samples"] else 0) or 0
            current_time = state.get("current_lap_time_ms") or 0
            crossed_line = distance < 100 and self.last_distance > 1000 and current_time < previous_time
            if crossed_line:
                # Time Trial can keep the same lap number after invalid attempts.
                self._finish(state)
            else:
                # A mid-lap rewind/flashback abandons this attempt. Starting a
                # fresh attempt prevents the later valid lap inheriting invalidity.
                self.current = None
                self.last_distance = None
        if self.current is None:
            self.current = {"_session_key": session_key, "packetFormat": state.get("packet_format"),
                            "gameYear": state.get("game_year"),
                            "gameVersion": state.get("game_version"),
                            "udpMode": "2026 Season Pack" if season_pack else "F1 25",
                            "sourcePacketFormat": state.get("raw_packet_format", state.get("packet_format")),
                            "sourceGameYear": state.get("raw_game_year", state.get("game_year")),
                            "editionDetection": state.get("edition_detection", "unknown"),
                            "formula": state.get("formula"),
                            "udpConfigurationWarning": state.get("udp_configuration_warning"),
                            "sessionUid": state.get("session_uid"), "trackId": state.get("track_id"),
                            "sessionType": state.get("session_type"),
                            "totalLaps": state.get("total_laps"),
                            "sessionTypeName": session_type_name(state.get("session_type")),
                            "gameMode": state.get("game_mode"),
                            "gameModeName": game_mode_name(state.get("game_mode")),
                            "seasonLinkIdentifier": state.get("season_link_identifier"),
                            "weekendLinkIdentifier": state.get("weekend_link_identifier"),
                            "sessionLinkIdentifier": state.get("session_link_identifier"),
                            "_carSetup": copy.deepcopy(state.get("car_setup")),
                            "recordingId": uuid4().hex, "recordingRevision": 0,
                            "rewindCount": 0, "rewindSplices": [],
                            "lapNumber": lap_no, "lapTimeMs": 0, "validLap": True,
                            "tyreCompound": state.get("tyre_compound"),
                            "fuelInTankKgAtStart": state.get("fuel_in_tank_kg"),
                            "tyreAgeLapsAtStart": state.get("tyres_age_laps"),
                            "tyreWearAtStart": tyre_values(state.get("tyres_wear")), "samples": [],
                            "createdAt": datetime.now(timezone.utc).isoformat()}
        elif state.get("car_setup"):
            self.current["_carSetup"] = copy.deepcopy(state["car_setup"])
        if state.get("pit_status") or state.get("lap_invalid"):
            self.current["validLap"] = False
            self.current.setdefault("_invalid_at_ms", elapsed)
        if self.last_distance is None or distance - self.last_distance >= ANALYSIS_CONFIG["sample_distance_m"]:
            self.current["samples"].append(self._sample(state)); self.last_distance = distance

    def _splice_rewind(self, state):
        """Replace the undone suffix with the game's restored timeline."""
        lap = self.current
        distance, elapsed = state["lap_distance"], state.get("current_lap_time_ms") or 0
        samples = lap["samples"]
        old_distance = samples[-1]["lap_distance"] if samples else distance
        old_time = samples[-1].get("lap_time_ms") if samples else elapsed
        # Both clocks must fit; keep no duplicate endpoint and invent no data.
        retained = [sample for sample in samples if sample["lap_distance"] < distance
                    and (sample.get("lap_time_ms") or 0) < elapsed]
        lap["samples"] = retained
        lap["rewindCount"] += 1
        lap["rewindSplices"].append({"fromDistanceM": old_distance, "toDistanceM": distance,
                                     "fromTimeMs": old_time, "toTimeMs": elapsed,
                                     "removedSamples": len(samples) - len(retained)})
        if lap.get("_invalid_at_ms", float("inf")) >= elapsed:
            lap.pop("_invalid_at_ms", None)
        lap["validLap"] = "_invalid_at_ms" not in lap
        if not retained:
            lap.update(fuelInTankKgAtStart=state.get("fuel_in_tank_kg"),
                       tyreAgeLapsAtStart=state.get("tyres_age_laps"),
                       tyreWearAtStart=tyre_values(state.get("tyres_wear")))
        # Always sample the restored endpoint, even for a sub-5m rewind.
        self.last_distance = None

    def _sample(self, state):
        season_pack = (state.get("packet_format") == 2026 or state.get("game_year") == 26
                       or state.get("game_version") == "F1 26")
        active_aero = season_pack and bool(state.get("aero_mode") or state.get("aero"))
        ers_usage = (bool(state.get("boost_active") or state.get("overtake_active"))
                     if season_pack else int(state.get("ers_mode") or 0) == 3)
        return {"lap_distance": state.get("lap_distance"), "lap_time_ms": state.get("current_lap_time_ms"),
                "position": {"x": state.get("world_position_x"), "y": state.get("world_position_y"),
                             "z": state.get("world_position_z")},
                "speed": state.get("speed", 0),
                "throttle": state.get("throttle_raw", 0), "brake": state.get("brake_raw", 0),
                "longitudinal_g": state.get("longitudinal_g"),
                "active_aero": active_aero, "drs": state.get("drs", 0),
                "ers_usage": ers_usage, "ers_percent": state.get("ers_percent"),
                "ers_soc": (state.get("ers_store_energy_j") / 4000000 * 100
                            if state.get("ers_store_energy_j") is not None else state.get("ers_percent")),
                "ers_store_energy_j": state.get("ers_store_energy_j"),
                "ers_mode": state.get("ers_mode"),
                "ers_mguk_power": state.get("ers_mguk_power"),
                "boost_active": state.get("boost_active", 0),
                "overtake_available": state.get("overtake_available", 0),
                "overtake_active": state.get("overtake_active", 0),
                "active_aero_available": state.get("active_aero_available", 0),
                "active_aero_activation_distance": state.get("active_aero_activation_distance", 0),
                "overtake_activation_distance": state.get("overtake_activation_distance", 0),
                "regulations_2026": state.get("regulations_2026", 0),
                "telemetry2_received": bool(state.get("telemetry2_received", False)),
                "fuel_in_tank_kg": state.get("fuel_in_tank_kg"),
                "fuel_remaining_laps": state.get("fuel_remaining_laps"),
                "tyre_age_laps": state.get("tyres_age_laps"),
                "pit_status": int(state.get("pit_status") or 0),
                "lap_invalid": bool(state.get("lap_invalid", False)),
                "wheel_speed": tyre_values(state.get("wheel_speed")), "wheel_slip_ratio": tyre_values(state.get("wheel_slip_ratio")),
                "tyre_wear": tyre_values(state.get("tyres_wear"))}

    def _finish(self, next_state):
        lap = self.current
        lap["lapTimeMs"] = int(next_state.get("last_lap_time_ms") or (lap["samples"][-1].get("lap_time_ms") if lap["samples"] else 0) or 0)
        lap["recordingRevision"] += 1
        self._previous_lap = self._lap_snapshot(lap)
        lap.pop("_session_key", None)
        lap.pop("_invalid_at_ms", None)
        lap["_needs_finalize"] = True
        # Transfer ownership of this completed attempt. The receiver starts a
        # new lap; rewinds copy containers before trimming or appending. Sample
        # dictionaries are immutable after capture, so no full deep copy is needed.
        try: self._queue.put_nowait(lap)
        except queue.Full:
            self._save_failed(overflow=True)
            logging.error("Lap %s was not saved: lap writer queue is full", lap["lapNumber"])
        self.current = None; self.last_distance = None

    @staticmethod
    def _lap_snapshot(lap):
        """Copy mutable containers while sharing immutable captured samples."""
        return lap | {"samples": list(lap["samples"]),
                      "rewindSplices": list(lap["rewindSplices"])}

    def _finalize_lap(self, lap):
        """Compute summaries and completeness only on the background writer."""
        lap["tyreWearAtEnd"] = lap["samples"][-1]["tyre_wear"] if lap["samples"] else tyre_values([])
        lap["fuelInTankKgAtEnd"] = (lap["samples"][-1].get("fuel_in_tank_kg")
                                     if lap["samples"] else None)
        if lap["samples"]:
            first_sample, last_sample = lap["samples"][0], lap["samples"][-1]
            lap["tyreAgeLapsAtStart"] = lap.get("tyreAgeLapsAtStart") if lap.get("tyreAgeLapsAtStart") is not None else first_sample.get("tyre_age_laps")
            lap["tyreAgeLapsAtEnd"] = last_sample.get("tyre_age_laps")
        lap["sampleCount"] = len(lap["samples"])
        distances = [float(s["lap_distance"]) for s in lap["samples"] if s.get("lap_distance") is not None]
        first_distance = distances[0] if distances else float("inf")
        recorded_distance = max(distances, default=0) - max(first_distance, 0)
        complete = bool(
            lap["lapTimeMs"] > 0
            and lap["sampleCount"] >= ANALYSIS_CONFIG["minimum_samples"]
            and -ANALYSIS_CONFIG["start_line_negative_tolerance_m"] <= first_distance <= ANALYSIS_CONFIG["start_line_tolerance_m"]
            and recorded_distance >= ANALYSIS_CONFIG["minimum_recorded_distance_m"]
        )
        lap["validLap"] = bool(lap["validLap"] and complete)
        lap["activeAeroUses"] = sum(
            bool(sample.get("active_aero")) and not bool(lap["samples"][index - 1].get("active_aero"))
            for index, sample in enumerate(lap["samples"]) if index > 0
        ) + (1 if lap["samples"] and lap["samples"][0].get("active_aero") else 0)
        lap["ersUsageCount"] = sum(
            bool(sample.get("ers_usage")) and not bool(lap["samples"][index - 1].get("ers_usage"))
            for index, sample in enumerate(lap["samples"]) if index > 0
        ) + (1 if lap["samples"] and lap["samples"][0].get("ers_usage") else 0)
        lap["pitEntryCount"] = sum(
            int(sample.get("pit_status") or 0) > 0 and int(lap["samples"][index - 1].get("pit_status") or 0) == 0
            for index, sample in enumerate(lap["samples"]) if index > 0
        )
        lap["pitLaneUsed"] = any(int(sample.get("pit_status") or 0) > 0 for sample in lap["samples"])
        return complete
