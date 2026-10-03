"""Shared Phase 1 section, energy, clipping, tyre, and personal prediction model."""
from bisect import bisect_left
from collections import Counter, defaultdict
from statistics import median

from operation_sections import analyze_operation_sections, build_operation_library
from telemetry_quality import number, select_strategy_laps, prediction_is_usable
from comparison_context import conditions


DEPLOYMENT_ACTIONS = ("boost", "overtake")
LIFT_LEVELS = {"lift_10": .10, "lift_20": .20, "lift_30": .30}
ACTIONS = ("none", *LIFT_LEVELS, *DEPLOYMENT_ACTIONS)
ACTION_CATALOG = {
    "none": {"category": "baseline", "label": "No additional operation", "intensity": 0.0},
    "lift_10": {"category": "lift", "label": "Lift 10%", "intensity": .10,
                "can_fund_follow_up": list(DEPLOYMENT_ACTIONS)},
    "lift_20": {"category": "lift", "label": "Lift 20%", "intensity": .20,
                "can_fund_follow_up": list(DEPLOYMENT_ACTIONS)},
    "lift_30": {"category": "lift", "label": "Lift 30%", "intensity": .30,
                "can_fund_follow_up": list(DEPLOYMENT_ACTIONS)},
    "boost": {"category": "deployment", "label": "Boost", "intensity": 1.0},
    "overtake": {"category": "deployment", "label": "Overtake", "intensity": 1.0},
}


def _number(value, default=None):
    try:
        value = float(value)
        return value if number(value) is not None else default
    except (TypeError, ValueError):
        return default


def _median(values, default=None):
    values = [value for value in values if value is not None]
    return median(values) if values else default


def _mean(values, default=None):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else default


def _rows(lap):
    rows = []
    for sample in lap.get("samples", []):
        position = sample.get("position") or {}
        distance = _number(sample.get("lap_distance"))
        elapsed = _number(sample.get("lap_time_ms"))
        if distance is None or elapsed is None:
            continue
        soc = _number(sample.get("ers_soc"), _number(sample.get("ers_percent")))
        if soc is None or not 0 <= soc <= 100:
            continue
        speed, throttle, brake = (_number(sample.get(key)) for key in ("speed", "throttle", "brake"))
        if any(value is None for value in (speed, throttle, brake)):
            continue
        wear = sample.get("tyre_wear") or {}
        slips = sample.get("wheel_slip_ratio") or {}
        rows.append({
            "s": distance, "t": elapsed, "speed": speed,
            "throttle": throttle, "brake": brake,
            "accel": _number(sample.get("longitudinal_g")), "soc": soc,
            "fuel": _number(sample.get("fuel_in_tank_kg")),
            "mguk": _number(sample.get("ers_mguk_power")),
            "boost": bool(sample.get("boost_active")),
            "overtake": bool(sample.get("overtake_active")),
            "aero": bool(sample.get("active_aero") or sample.get("drs")),
            "slip": max((_number(value, 0.0) for value in slips.values()), default=0.0),
            "wear": _mean([_number(value) for value in wear.values()]),
            "x": _number(position.get("x")), "z": _number(position.get("z")),
        })
    rows.sort(key=lambda row: row["s"])
    return rows


def _at(rows, distance, key):
    distances = [row["s"] for row in rows]
    index = bisect_left(distances, distance)
    if index <= 0:
        return rows[0][key]
    if index >= len(rows):
        return rows[-1][key]
    before, after = rows[index - 1], rows[index]
    left, right = before[key], after[key]
    if left is None or right is None:
        return left if left is not None else right
    ratio = (distance - before["s"]) / max(after["s"] - before["s"], 1e-9)
    return left + (right - left) * ratio


def _deployment_action(local):
    total = max(1, len(local))
    if sum(row["overtake"] for row in local) / total >= .20:
        return "overtake"
    if sum(row["boost"] for row in local) / total >= .20:
        return "boost"
    return "none"


def _lift_action(local):
    """Classify measured non-braking throttle reduction into a stable level."""
    usable = [row for row in local if row["brake"] < .05]
    if len(usable) < max(2, round(len(local) * .6)):
        return "none", 0.0
    lift_ratio = _mean([max(0.0, min(1.0, 1.0 - row["throttle"])) for row in usable], 0.0)
    if lift_ratio < .05:
        return "none", round(lift_ratio, 3)
    action = min(LIFT_LEVELS, key=lambda name: abs(LIFT_LEVELS[name] - lift_ratio))
    return action, round(lift_ratio, 3)


def _clip_threshold(rows):
    powers = [row["mguk"] for row in rows if row["mguk"] is not None and row["mguk"] > 1000
              and row["throttle"] >= .95 and row["brake"] < .05]
    return max(20000.0, _median(powers, 0) * .20) if powers else None


def _observation(item, section):
    rows = item["rows"]
    start, end = section["start_distance"], section["end_distance"]
    local = [row for row in rows if start <= row["s"] <= end]
    if len(local) < 2:
        return None
    threshold = item["clip_threshold"]
    clipping = []
    super_clipping = []
    for row in local:
        candidate = (threshold is not None and row["throttle"] >= .95 and row["brake"] < .05
                     and row["speed"] >= 180 and row["mguk"] is not None
                     and row["mguk"] <= threshold)
        clipping.append(candidate)
        super_clipping.append(candidate and (row["mguk"] <= threshold * .25
                                               or (row["soc"] is not None and row["soc"] <= 2)))
    start_soc, end_soc = _at(rows, start, "soc"), _at(rows, end, "soc")
    start_fuel, end_fuel = _at(rows, start, "fuel"), _at(rows, end, "fuel")
    start_wear, end_wear = _at(rows, start, "wear"), _at(rows, end, "wear")
    raw_time = _at(rows, end, "t") - _at(rows, start, "t")
    deployment = _deployment_action(local)
    lift_action, lift_ratio = _lift_action(local)
    return {
        "lap_id": item["id"], "session": item["session"], "lap_number": item["lap"].get("lapNumber"),
        "action": deployment if deployment != "none" else lift_action,
        "deployment_action": deployment, "lift_action": lift_action, "lift_ratio": lift_ratio,
        "raw_time_ms": raw_time,
        "normalized_time_ms": raw_time * item["best_time"] / item["sample_elapsed_ms"],
        "soc_delta": ((end_soc - start_soc) if start_soc is not None and end_soc is not None else None),
        "start_soc": start_soc, "end_soc": end_soc,
        "entry_speed": _at(rows, start, "speed"), "exit_speed": _at(rows, end, "speed"),
        "average_speed": _median([row["speed"] for row in local], 0),
        "average_throttle": _mean([row["throttle"] for row in local], 0),
        "average_brake": _mean([row["brake"] for row in local], 0),
        "peak_slip": max((abs(row["slip"]) for row in local), default=0),
        "aero_ratio": _mean([float(row["aero"]) for row in local], 0),
        "wear": _median([row["wear"] for row in local]),
        "fuel": _median([row["fuel"] for row in local]),
        "wear_delta": ((end_wear - start_wear) if start_wear is not None and end_wear is not None else None),
        "fuel_delta_kg": ((end_fuel - start_fuel) if start_fuel is not None and end_fuel is not None else None),
        "clipping": sum(clipping) / len(clipping) >= .30,
        "super_clipping": sum(super_clipping) / len(super_clipping) >= .20,
    }


def _complete_prediction(value, none=None):
    value["soc_cost"] = (round(max(0.0, float(none.get("soc_delta") or 0)
                                      - float(value.get("soc_delta") or 0)), 3)
                         if none is not None else 0.0)
    value["soc_recovery"] = (round(max(0.0, float(value.get("soc_delta") or 0)
                                          - float(none.get("soc_delta") or 0)), 3)
                             if none is not None else 0.0)
    value["exit_speed_delta"] = round(float(value.get("exit_speed") or 0)
                                       - float((none or {}).get("exit_speed") or value.get("exit_speed") or 0), 1)
    value.setdefault("peak_slip", float((none or {}).get("peak_slip") or 0))
    value.setdefault("tyre_delta", (none or {}).get("tyre_delta"))
    value.setdefault("tyre_cost", 0.0)
    value.setdefault("fuel_delta_kg", (none or {}).get("fuel_delta_kg"))
    value["fuel_saving_kg"] = (round(float(value["fuel_delta_kg"]) - float(none["fuel_delta_kg"]), 5)
                               if none is not None and value.get("fuel_delta_kg") is not None
                               and none.get("fuel_delta_kg") is not None else 0.0)
    value.setdefault("confidence", round(min(1.0, value.get("samples", 0) / 5), 3))
    value.setdefault("throttle_reduction", 0.0)
    return value


def _fallback_deployment(section, action, none):
    duration = max(100.0, none["predicted_time_ms"])
    throttle = section.get("average_throttle", 0)
    speed = section.get("average_speed", 0)
    length = max(20.0, section["end_distance"] - section["start_distance"])
    suitability = max(.15, min(1.0, throttle * .65 + speed / 350 * .35))
    factor = .010 if action == "boost" else .0155
    gain = duration * factor * suitability
    cost = max(.15, length / 1000 * (2.1 if action == "boost" else 3.0) * suitability)
    return _complete_prediction({
        "predicted_time_ms": round(duration - gain, 1), "gain_ms": round(gain, 1),
        "soc_delta": round(float(none.get("soc_delta") or 0) - cost, 3),
        "exit_speed": round(none["exit_speed"] + gain / max(duration, 1) * 18, 1),
        "clipping_probability": none["clipping_probability"],
        "super_clipping_probability": none["super_clipping_probability"],
        "peak_slip": round(float(none.get("peak_slip") or section.get("peak_slip") or 0)
                           * (1.08 if action == "boost" else 1.12), 4),
        "tyre_delta": (round(float(none.get("tyre_delta") or 0)
                             + (.01 if action == "boost" else .015), 4)),
        "tyre_cost": round(.01 if action == "boost" else .015, 4),
        "fuel_delta_kg": none.get("fuel_delta_kg"),
        "samples": 0, "evidence": "inferred", "confidence": .2,
    }, none)


def _fallback_lift(section, action, none):
    intensity = LIFT_LEVELS[action]
    duration = max(100.0, none["predicted_time_ms"])
    length = max(20.0, section["end_distance"] - section["start_distance"])
    speed_factor = max(.35, min(1.25, section.get("average_speed", 0) / 220.0))
    time_loss = duration * (.008 + intensity * .075) * speed_factor
    recovery = max(.03, length / 1000 * (0.55 + intensity * 2.4) * speed_factor)
    exit_loss = max(.2, intensity * speed_factor * 7.5)
    return _complete_prediction({
        "predicted_time_ms": round(duration + time_loss, 1), "gain_ms": round(-time_loss, 1),
        "soc_delta": round(float(none.get("soc_delta") or 0) + recovery, 3),
        "exit_speed": round(max(0.0, float(none.get("exit_speed") or 0) - exit_loss), 1),
        "clipping_probability": round(float(none.get("clipping_probability") or 0)
                                          * max(.2, 1 - intensity * 1.8), 3),
        "super_clipping_probability": round(float(none.get("super_clipping_probability") or 0)
                                                * max(.1, 1 - intensity * 2.2), 3),
        "peak_slip": round(float(none.get("peak_slip") or section.get("peak_slip") or 0)
                           * max(.4, 1 - intensity), 4),
        "tyre_delta": round(float(none.get("tyre_delta") or 0) - intensity * .01, 4),
        "tyre_cost": round(-intensity * .01, 4),
        "fuel_delta_kg": (round(float(none["fuel_delta_kg"]) + intensity * .002, 5)
                          if none.get("fuel_delta_kg") is not None else None),
        "samples": 0, "evidence": "inferred", "confidence": .15,
        "throttle_reduction": intensity,
    }, none)


def _action_prediction(observations, action, none_prediction=None):
    selected = [row for row in observations if row["action"] == action]
    if not selected:
        return None
    value = {
        "predicted_time_ms": round(_median([row["normalized_time_ms"] for row in selected]), 1),
        "soc_delta": round(_median([row["soc_delta"] for row in selected], 0.0), 3),
        "exit_speed": round(_median([row["exit_speed"] for row in selected], 0.0), 1),
        "clipping_probability": round(_mean([float(row["clipping"]) for row in selected], 0), 3),
        "super_clipping_probability": round(_mean([float(row["super_clipping"]) for row in selected], 0), 3),
        "peak_slip": round(_median([row["peak_slip"] for row in selected], 0), 4),
        "tyre_delta": round(_median([row["wear_delta"] for row in selected], 0), 4),
        "tyre_cost": round(_median([row["wear_delta"] for row in selected], 0)
                           - float((none_prediction or {}).get("tyre_delta") or 0), 4),
        "fuel_delta_kg": (round(_median([row["fuel_delta_kg"] for row in selected]), 5)
                          if any(row["fuel_delta_kg"] is not None for row in selected) else None),
        "samples": len(selected), "evidence": "observed",
        "throttle_reduction": (round(_median([row["lift_ratio"] for row in selected], 0), 3)
                               if action in LIFT_LEVELS else 0.0),
    }
    if none_prediction is not None:
        value["gain_ms"] = round(none_prediction["predicted_time_ms"] - value["predicted_time_ms"], 1)
    else:
        value["gain_ms"] = 0.0
    return _complete_prediction(value, none_prediction)


def build_strategy_model(lap_entries, selected_session_id=None, selected_lap_id=None, track_profile=None,
                         pace_window_percent=8.0, max_laps=40):
    """Build one reusable statistical model for qualifying and race optimizers."""
    selected, selection = select_strategy_laps(lap_entries, selected_session_id, selected_lap_id,
                                               pace_window_percent, max_laps)
    if selection.get("reason"):
        return {"analyzable": False, "reason": selection["reason"], "selection": selection}
    eligible = []
    for lap_id, lap in selected:
        lap_time = _number(lap.get("lapTimeMs"))
        rows = _rows(lap)
        season_pack = (lap.get("packetFormat") == 2026 or lap.get("gameYear") == 26
                       or lap.get("gameVersion") == "F1 26"
                       or lap.get("udpMode") == "2026 Season Pack")
        if (not season_pack or not lap.get("validLap") or lap.get("pitLaneUsed") or not lap_time
                or len(rows) < 50 or rows[-1]["s"] - rows[0]["s"] < 500):
            continue
        eligible.append({"id": lap_id, "session": str(lap_id).split("/", 1)[0],
                         "lap": lap, "lap_time": lap_time, "rows": rows})
    eligible.sort(key=lambda item: item["lap_time"])
    if len(eligible) < 2:
        return {"analyzable": False, "reason": "F1 26の比較可能な有効ラップが2周以上必要です"}
    all_eligible = list(eligible)
    best_time = eligible[0]["lap_time"]
    for item in all_eligible:
        item["best_time"] = best_time
        item["sample_elapsed_ms"] = max(1, item["rows"][-1]["t"] - item["rows"][0]["t"])
        item["clip_threshold"] = _clip_threshold(item["rows"])
    library = build_operation_library([(item["id"], item["lap"]) for item in eligible],
                                      pace_window_percent=pace_window_percent,
                                      max_laps=max_laps)
    if library.get("analyzable"):
        definitions = library["sections"]
        geometry = [{key: point.get(key) for key in ("s", "x", "z")}
                    for point in library.get("points", [])]
    else:
        fallback = analyze_operation_sections(eligible[0]["lap"])
        if not fallback.get("analyzable"):
            return {"analyzable": False, "reason": fallback.get("reason")}
        definitions, geometry = fallback["sections"], [
            {key: point.get(key) for key in ("s", "x", "z")} for point in fallback.get("points", [])]
    geometry_status = library["geometry"] if library.get("analyzable") else fallback["geometry"]
    if not geometry_status.get("available"):
        geometry = []
    # Resampled input runs are separated by one sample step. Partition those
    # boundaries continuously so the planner does not omit time or energy.
    boundaries = [0.0] + [(a["end_distance"] + b["start_distance"]) / 2
                         for a, b in zip(definitions, definitions[1:])] + [eligible[0]["rows"][-1]["s"]]
    definitions = [definition | {"start_distance": boundaries[index], "end_distance": boundaries[index+1]}
                   for index, definition in enumerate(definitions)]

    sections = []
    all_observations = []
    ideal_sections = []
    session_section_times = defaultdict(list)
    for definition in definitions:
        observations = [value for item in eligible
                        if (value := _observation(item, definition)) is not None]
        if not observations:
            return {"analyzable": False, "reason": "Recorded samples do not cover every input section sufficiently.",
                    "selection": selection}
        none = _action_prediction(observations, "none")
        if none is None:
            none = _complete_prediction({
                "predicted_time_ms": round(_median([row["normalized_time_ms"] for row in observations]), 1),
                "gain_ms": 0.0, "soc_delta": round(_median([row["soc_delta"] for row in observations], 0), 3),
                "soc_cost": 0.0, "exit_speed": round(_median([row["exit_speed"] for row in observations], 0), 1),
                "clipping_probability": round(_mean([float(row["clipping"]) for row in observations], 0), 3),
                "super_clipping_probability": round(_mean([float(row["super_clipping"]) for row in observations], 0), 3),
            "peak_slip": round(_median([row["peak_slip"] for row in observations], 0), 4),
                "tyre_delta": round(_median([row["wear_delta"] for row in observations], 0), 4),
                "tyre_cost": 0.0,
                "fuel_delta_kg": (round(_median([row["fuel_delta_kg"] for row in observations]), 5)
                                  if any(row["fuel_delta_kg"] is not None for row in observations) else None),
                "samples": 0, "evidence": "inferred_baseline", "confidence": .25,
                "throttle_reduction": 0.0,
            })
        actions = {"none": none}
        summary = {
            "average_speed": round(_median([row["average_speed"] for row in observations], 0), 1),
            "average_throttle": round(_median([row["average_throttle"] for row in observations], 0), 3),
            "average_brake": round(_median([row["average_brake"] for row in observations], 0), 3),
            "peak_slip": round(_median([row["peak_slip"] for row in observations], 0), 4),
            "tyre_wear": round(_median([row["wear"] for row in observations], 0), 3),
        }
        model_section = {
            "number": definition.get("number", len(sections) + 1), "kind": definition.get("kind"),
            "label": definition.get("label"), "start_distance": definition["start_distance"],
            "end_distance": definition["end_distance"], **summary,
        }
        for action in LIFT_LEVELS:
            predicted = _action_prediction(observations, action, none)
            actions[action] = predicted or _fallback_lift(model_section, action, none)
        for action in DEPLOYMENT_ACTIONS:
            predicted = _action_prediction(observations, action, none)
            actions[action] = predicted or _fallback_deployment(model_section, action, none)
        for action in ACTIONS:
            cost = actions[action].get("soc_cost", 0)
            actions[action]["value_ms_per_soc"] = round(actions[action].get("gain_ms", 0) / cost, 2) if cost > .01 else 0
            recovery = actions[action].get("soc_recovery", 0)
            actions[action]["time_cost_ms_per_soc_recovered"] = (
                round(max(0, -actions[action].get("gain_ms", 0)) / recovery, 2) if recovery > .01 else None
            )

        personal_rows = [row for row in observations if row["session"] == selected_session_id]
        other_sessions = {row["session"] for row in observations if row["session"] != selected_session_id}
        if len(personal_rows) >= 3 and other_sessions:
            personal_residual = _median([row["normalized_time_ms"] for row in personal_rows], 0) - _median(
                [row["normalized_time_ms"] for row in observations], 0)
            personal = {
                "status": "available", "samples": len(personal_rows),
                "time_residual_ms": round(personal_residual, 1),
                "peak_slip": round(_median([row["peak_slip"] for row in personal_rows], 0), 4),
                "early_deployment_ratio": round(sum(row["deployment_action"] != "none" for row in personal_rows) / len(personal_rows), 3),
            }
        else:
            personal = {"status": "insufficient_samples", "samples": len(personal_rows)}
        model_section["actions"] = actions
        for action in ACTIONS:
            actions[action]["usable_for_plan"] = prediction_is_usable(model_section, action)
        model_section["personal"] = personal
        model_section["observation_count"] = len(observations)
        sections.append(model_section)
        all_observations.extend(observations)
        session_observations = [value for item in all_eligible if item["session"] == selected_session_id
                                if (value := _observation(item, definition)) is not None]
        for value in session_observations:
            session_section_times[value["lap_id"]].append(value["raw_time_ms"])
        if session_observations:
            fastest_section = min(session_observations, key=lambda value: value["raw_time_ms"])
            ideal_sections.append({
                "section_number": model_section["number"], "label": model_section.get("label"),
                "kind": model_section.get("kind"), "start_distance": model_section["start_distance"],
                "end_distance": model_section["end_distance"], "raw_time_ms": fastest_section["raw_time_ms"],
                "source_lap_id": fastest_section["lap_id"],
                "source_lap_number": fastest_section["lap_number"], "action": fastest_section["action"],
            })

    session_items = [item for item in all_eligible if item["session"] == selected_session_id]
    session_best = min(session_items, key=lambda item: item["lap_time"], default=None)
    reference_section_time = (sum(session_section_times.get(session_best["id"], [])) if session_best else 0)
    coverage_scale = (session_best["lap_time"] / reference_section_time
                      if session_best and reference_section_time > 0 else 1.0)
    ideal_time = round(sum(section["raw_time_ms"] for section in ideal_sections) * coverage_scale, 1)
    for section in ideal_sections:
        section["predicted_time_ms"] = round(section.pop("raw_time_ms") * coverage_scale, 1)
    ideal_lap = {
        "analyzable": bool(session_best and len(ideal_sections) == len(sections)),
        "method": "best_observed_section_composite", "session_id": selected_session_id,
        "source_lap_count": len(session_items), "session_best_lap_number": session_best["lap"].get("lapNumber") if session_best else None,
        "session_best_lap_time_ms": round(session_best["lap_time"], 1) if session_best else None,
        "predicted_lap_time_ms": ideal_time if ideal_sections else None,
        "potential_improvement_ms": round(session_best["lap_time"] - ideal_time, 1) if session_best and ideal_sections else None,
        "sections": ideal_sections,
    }

    initial_soc = _median([item["rows"][0]["soc"] for item in eligible if item["rows"][0]["soc"] is not None], 100)
    finish_soc = _median([item["rows"][-1]["soc"] for item in eligible if item["rows"][-1]["soc"] is not None], initial_soc)
    selected_items = [item for item in eligible if item["session"] == selected_session_id]
    reference_id = selection["reference_lap_id"]
    reference_lap = next(lap for lap_id, lap in lap_entries if lap_id == reference_id)
    current = {"id": reference_id, "lap": reference_lap, "rows": _rows(reference_lap)}
    if current is None:
        current_pool = selected_items or eligible
        current = max(current_pool, key=lambda item: item["lap"].get("createdAt", ""))
    personal_available = sum(section["personal"]["status"] == "available" for section in sections)
    return {
        "analyzable": bool(sections), "reason": None if sections else "共通セクションを作成できませんでした",
        "schema_version": 5, "model_version": "condition-matched-section-actions-v5",
        "action_catalog": ACTION_CATALOG,
        "track_id": eligible[0]["lap"].get("trackId"), "track_length_m": round(eligible[0]["rows"][-1]["s"], 1),
        "best_lap_time_ms": round(best_time), "initial_soc": round(initial_soc, 2),
        "historical_finish_soc": round(finish_soc, 2), "sections": sections, "track_points": geometry,
        "geometry": geometry_status, "geometry_source_lap_id": library.get("geometry_source_lap_id"),
        "selection": selection,
        "ideal_lap": ideal_lap,
        "source": {"eligible_laps": len(eligible), "sessions": len({item["session"] for item in eligible}),
                   "pace_window_percent": pace_window_percent,
                   "lap_ids": [item["id"] for item in eligible],
                   "laps": [{"id": item["id"], "lap_number": item["lap"].get("lapNumber"),
                             "lap_time_ms": item["lap_time"], "conditions": conditions(item["lap"])} for item in eligible]},
        "personal": {"status": "available" if personal_available else "insufficient_samples",
                     "available_sections": personal_available, "selected_session": selected_session_id},
        "current_state": {
            "lap_number": current["lap"].get("lapNumber"), "total_laps": current["lap"].get("totalLaps"),
            "soc": round(current["rows"][-1]["soc"], 2) if current["rows"][-1]["soc"] is not None else round(initial_soc, 2),
            "fuel_kg": current["rows"][-1]["fuel"], "tyre_wear": current["rows"][-1]["wear"],
            "tyre_compound": current["lap"].get("tyreCompound"),
        },
    }
