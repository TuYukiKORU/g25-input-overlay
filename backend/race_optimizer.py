"""Multi-lap Phase 1 MPC built on the shared section prediction model."""

from qualifying_optimizer import _adjusted_time


LEVELS = ("attack", "fast", "sustainable", "save")
LEVEL_LABELS = {"attack": "Attack", "fast": "Fast", "sustainable": "Sustainable", "save": "Save / Recharge"}


def _lap_plan(model, level, personal=False, deployment_mode="boost"):
    sections = model["sections"]
    candidates = []
    for index, section in enumerate(sections):
        if section.get("kind") not in ("acceleration", "flat_out"):
            continue
        action = "overtake" if deployment_mode == "overtake" else "boost"
        prediction = section["actions"][action]
        candidates.append((float(prediction.get("value_ms_per_soc") or 0), index, action))
    candidates.sort(reverse=True)
    fractions = {"attack": 1.0, "fast": .58, "sustainable": .28, "save": 0.0}
    limit = round(len(sections) * fractions[level])
    chosen = {}
    for _, index, action in candidates:
        if index in chosen:
            continue
        chosen[index] = action
        if len(chosen) >= limit:
            break
    time_ms = 0.0
    delta_soc = 0.0
    clipping = []
    allocations = []
    for index, section in enumerate(sections):
        action = chosen.get(index, "none")
        prediction = section["actions"][action]
        time_ms += _adjusted_time(section, action, personal)
        delta_soc += float(prediction.get("soc_delta") or 0)
        allocations.append({"section_number": section["number"], "label": section.get("label"),
                            "kind": section.get("kind"), "start_distance": section["start_distance"],
                            "end_distance": section["end_distance"], "action": action})
        if prediction.get("clipping_probability", 0) >= .25 or prediction.get("super_clipping_probability", 0) >= .15:
            clipping.append({"section_number": section["number"], "start_distance": section["start_distance"],
                             "end_distance": section["end_distance"],
                             "clipping_probability": prediction.get("clipping_probability", 0),
                             "super_clipping_probability": prediction.get("super_clipping_probability", 0)})
    # Save must be capable of recovering in sparse historical datasets where
    # integer SOC sampling hides small per-section recovery.
    if level == "save":
        delta_soc = max(delta_soc, 3.0)
        time_ms += 220.0
    tyre_cost = {"attack": .18, "fast": .11, "sustainable": .06, "save": .02}[level]
    return {"level": level, "label": LEVEL_LABELS[level], "predicted_lap_time_ms": round(time_ms, 1),
            "delta_soc": round(delta_soc, 2), "tyre_cost": tyre_cost,
            "clipping_probability": round(max((row["clipping_probability"] for row in clipping), default=0), 3),
            "super_clipping_probability": round(max((row["super_clipping_probability"] for row in clipping), default=0), 3),
            "clipping_predictions": clipping, "allocations": allocations}


def optimize_race(model, horizon=5, current_soc=None, minimum_soc=5.0,
                  remaining_laps=None, personal=False, deployment_mode="boost"):
    if not model.get("analyzable"):
        return {"analyzable": False, "reason": model.get("reason")}
    horizon = max(3, min(5, int(horizon)))
    current = model.get("current_state", {})
    start_lap = int(current.get("lap_number") or 1)
    if remaining_laps is None:
        total = current.get("total_laps")
        remaining_laps = max(1, int(total) - start_lap + 1) if total else horizon
    remaining_laps = max(1, int(remaining_laps))
    horizon = min(horizon, remaining_laps)
    start_soc = max(0.0, min(100.0, float(current.get("soc") if current_soc is None else current_soc)))
    minimum_soc = max(0.0, min(start_soc, float(minimum_soc)))
    deployment_mode = "overtake" if deployment_mode == "overtake" else "boost"
    plans = {level: _lap_plan(model, level, personal, deployment_mode) for level in LEVELS}
    states = {round(start_soc): (0.0, [])}
    for offset in range(horizon):
        next_states = {}
        for soc_key, (cost, path) in states.items():
            for level, plan in plans.items():
                next_soc = min(100.0, soc_key + plan["delta_soc"])
                if next_soc < minimum_soc:
                    continue
                key = round(next_soc)
                tyre_penalty = plan["tyre_cost"] * offset * 35.0
                clip_penalty = plan["super_clipping_probability"] * 180.0
                value = cost + plan["predicted_lap_time_ms"] + tyre_penalty + clip_penalty
                if key not in next_states or value < next_states[key][0]:
                    next_states[key] = (value, path + [level])
        if not next_states:
            return {"analyzable": False, "reason": "予測期間内で最低SOCを維持できません"}
        states = next_states
    finishing_race = remaining_laps <= horizon
    target_soc = minimum_soc if finishing_race else min(70.0, max(minimum_soc + 15, start_soc))
    finish_key, (_, path) = min(states.items(), key=lambda item: item[1][0] + abs(item[0] - target_soc) * 35.0)
    trajectory, soc = [], start_soc
    fuel = current.get("fuel_kg")
    wear = current.get("tyre_wear")
    baseline = plans["sustainable"]["predicted_lap_time_ms"] * horizon
    predicted_total = 0.0
    shortage_lap = None
    for offset, level in enumerate(path):
        plan = plans[level]
        before = soc
        soc = min(100.0, soc + plan["delta_soc"])
        predicted_time = plan["predicted_lap_time_ms"] + plan["tyre_cost"] * offset * 35.0
        predicted_total += predicted_time
        if soc <= minimum_soc + 1 and shortage_lap is None and offset + 1 < horizon:
            shortage_lap = start_lap + offset
        trajectory.append({
            "lap_number": start_lap + offset, "level": level, "label": plan["label"],
            "soc_start": round(before, 1), "soc_end": round(soc, 1), "delta_soc": round(soc - before, 1),
            "predicted_lap_time_ms": round(predicted_time, 1),
            "clipping_probability": plan["clipping_probability"],
            "super_clipping_probability": plan["super_clipping_probability"],
            "tyre_cost": plan["tyre_cost"], "predicted_tyre_wear": (round(wear + plan["tyre_cost"] * (offset + 1), 2)
                                                                       if wear is not None else None),
            "predicted_fuel_kg": (round(max(0, fuel - 1.6 * offset), 2) if fuel is not None else None),
            "clipping_predictions": plan["clipping_predictions"],
            "allocations": plan["allocations"],
        })
    return {
        "analyzable": True, "strategy_type": "personal" if personal else "general",
        "deployment_mode": deployment_mode,
        "horizon_laps": horizon, "remaining_laps": remaining_laps, "finishing_race": finishing_race,
        "start_soc": round(start_soc, 1), "target_finish_soc": round(target_soc, 1),
        "predicted_finish_soc": round(finish_key, 1), "trajectory": trajectory,
        "current_lap_recommendation": trajectory[0], "soc_shortage_lap": shortage_lap,
        "estimated_gain_vs_sustainable_ms": round(baseline - predicted_total, 1),
        "recommendation": (f"現在周は{trajectory[0]['label']}。{horizon}周後のSOC目標は約{target_soc:.0f}%です。"),
        "level_options": list(plans.values()),
    }


def analyze_race(model, horizon=5, current_soc=None, minimum_soc=5.0, remaining_laps=None):
    general = optimize_race(model, horizon, current_soc, minimum_soc, remaining_laps, False)
    personal = (optimize_race(model, horizon, current_soc, minimum_soc, remaining_laps, True)
                if model.get("personal", {}).get("status") == "available"
                else {"analyzable": False, "reason": "Personal recommendationはサンプル不足です"})
    return {"analyzable": general.get("analyzable", False), "general": general, "personal": personal,
            "model_summary": {"model_version": model.get("model_version"), "source": model.get("source"),
                              "personal": model.get("personal"), "track_length_m": model.get("track_length_m"),
                              "track_points": model.get("track_points", []), "ideal_lap": model.get("ideal_lap")}}
