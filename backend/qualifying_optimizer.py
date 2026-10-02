"""Single-lap ERS allocation using dynamic programming over section and SOC."""


def _adjusted_time(section, action, personal):
    prediction = section["actions"][action]
    value = float(prediction["predicted_time_ms"])
    if not personal or section["personal"].get("status") != "available":
        return value
    residual = float(section["personal"].get("time_residual_ms") or 0)
    if action in ("boost", "overtake"):
        personal_slip = float(section["personal"].get("peak_slip") or 0)
        general_slip = float(section.get("peak_slip") or 0)
        value += max(0.0, personal_slip - general_slip) * (180 if action == "boost" else 260)
        value += max(0.0, residual) * .08
    return value


def _pre_start_runup(model, battery_before_runup_soc, minimum_start_line_soc,
                     deployment_mode):
    """Estimate energy spent accelerating from the final corner to the timing line."""
    section = next((row for row in reversed(model["sections"])
                    if row.get("kind") in ("acceleration", "flat_out")), model["sections"][-1])
    none = section["actions"]["none"]
    prediction = section["actions"][deployment_mode]
    full_cost = max(0.0, float(none.get("soc_delta") or 0)
                    - float(prediction.get("soc_delta") or 0))
    available = max(0.0, battery_before_runup_soc - minimum_start_line_soc)
    applied_cost = min(full_cost, available)
    applied_fraction = applied_cost / full_cost if full_cost > .001 else 0.0
    return {
        "action": deployment_mode, "battery_before_runup_soc": round(battery_before_runup_soc, 2),
        "minimum_start_line_soc": round(minimum_start_line_soc, 2),
        "predicted_soc_cost": round(applied_cost, 3),
        "predicted_start_line_soc": round(battery_before_runup_soc - applied_cost, 2),
        "applied_fraction": round(applied_fraction, 3),
        "source_section_number": section["number"],
        "source_start_distance": section["start_distance"],
        "source_end_distance": section["end_distance"],
        "evidence": prediction.get("evidence"), "confidence": prediction.get("confidence"),
    }


def optimize_qualifying(model, start_soc=None, minimum_finish_soc=5.0, personal=False,
                        deployment_mode="overtake", minimum_start_line_soc=80.0):
    if not model.get("analyzable"):
        return {"analyzable": False, "reason": model.get("reason")}
    sections = model["sections"]
    deployment_mode = "overtake" if deployment_mode == "overtake" else "boost"
    battery_before_runup_soc = max(0.0, min(100.0, float(100.0 if start_soc is None else start_soc)))
    minimum_start_line_soc = max(0.0, min(battery_before_runup_soc,
                                          float(minimum_start_line_soc)))
    pre_start = _pre_start_runup(model, battery_before_runup_soc,
                                 minimum_start_line_soc, deployment_mode)
    start_soc = pre_start["predicted_start_line_soc"]
    target = max(0.0, min(start_soc, float(minimum_finish_soc)))
    step = .5
    start_key = round(start_soc / step)
    states = {start_key: (0.0, [])}
    for index, section in enumerate(sections):
        next_states = {}
        for soc_key, (cost, path) in states.items():
            soc = soc_key * step
            actions = ["none"]
            if section.get("kind") in ("lift", "acceleration", "flat_out"):
                actions.extend(("lift_10", "lift_20", "lift_30"))
            if section.get("kind") in ("acceleration", "flat_out"):
                actions.append(deployment_mode)
            allowed = ((action, section["actions"][action]) for action in actions)
            for action, prediction in allowed:
                next_soc = min(100.0, soc + float(prediction.get("soc_delta") or 0))
                if next_soc < target - .01:
                    continue
                next_key = round(next_soc / step)
                next_cost = cost + _adjusted_time(section, action, personal)
                existing = next_states.get(next_key)
                if existing is None or next_cost < existing[0]:
                    next_states[next_key] = (next_cost, path + [action])
        if not next_states:
            return {"analyzable": False, "reason": f"Section {index + 1}で最低SOCを維持できません"}
        states = next_states

    # A small terminal value prevents waste while allowing a faster solution to
    # finish slightly above the target when that energy has little lap-time value.
    finish_key, (predicted_time, path) = min(
        states.items(), key=lambda item: item[1][0] + abs(item[0] * step - target) * 8.0)
    finish_soc = finish_key * step
    baseline_time = sum(_adjusted_time(section, "none", personal) for section in sections)
    running_soc = start_soc
    allocations, clipping = [], []
    for section, action in zip(sections, path):
        prediction = section["actions"][action]
        before = running_soc
        running_soc = min(100.0, running_soc + float(prediction.get("soc_delta") or 0))
        row = {
            "section_number": section["number"], "label": section.get("label"), "kind": section.get("kind"),
            "start_distance": section["start_distance"], "end_distance": section["end_distance"],
            "action": action, "soc_start": round(before, 2), "soc_end": round(running_soc, 2),
            "soc_used": round(max(0.0, before - running_soc), 2),
            "soc_recovered": round(max(0.0, running_soc - before), 2),
            "estimated_gain_ms": round(section["actions"]["none"]["predicted_time_ms"]
                                       - prediction["predicted_time_ms"], 1),
            "value_ms_per_soc": prediction.get("value_ms_per_soc", 0),
            "exit_speed": prediction.get("exit_speed"), "evidence": prediction.get("evidence"),
            "clipping_probability": prediction.get("clipping_probability", 0),
            "super_clipping_probability": prediction.get("super_clipping_probability", 0),
        }
        allocations.append(row)
        if row["clipping_probability"] >= .25 or row["super_clipping_probability"] >= .15:
            clipping.append({key: row[key] for key in ("section_number", "start_distance", "end_distance",
                                                       "clipping_probability", "super_clipping_probability")})
    used = [row for row in allocations if row["action"] != "none"]
    return {
        "analyzable": True, "strategy_type": "personal" if personal else "general",
        "deployment_mode": deployment_mode,
        "pre_start_runup": pre_start,
        "battery_before_runup_soc": round(battery_before_runup_soc, 2),
        "start_line_soc": round(start_soc, 2),
        "start_soc": round(start_soc, 2), "minimum_finish_soc": round(target, 2),
        "predicted_finish_soc": round(finish_soc, 2),
        "predicted_lap_time_ms": round(predicted_time, 1),
        "baseline_lap_time_ms": round(baseline_time, 1),
        "estimated_improvement_ms": round(baseline_time - predicted_time, 1),
        "allocations": allocations, "recommended_sections": used,
        "clipping_predictions": clipping,
        "recommendation": (f"{len(used)}区間でERSを使用し、フィニッシュSOCを約{finish_soc:.1f}%にします。"
                           if used else "最低SOC制約のため、追加ERS展開は推奨しません。"),
    }


def _analyze_qualifying_legacy(model, start_soc=None, minimum_finish_soc=5.0):
    general = optimize_qualifying(model, start_soc, minimum_finish_soc, personal=False)
    personal = (optimize_qualifying(model, start_soc, minimum_finish_soc, personal=True)
                if model.get("personal", {}).get("status") == "available"
                else {"analyzable": False, "reason": "Personal recommendationはサンプル不足です"})
    return {"analyzable": general.get("analyzable", False), "general": general,
            "personal": personal, "model_summary": {
                "model_version": model.get("model_version"), "source": model.get("source"),
                "personal": model.get("personal"), "track_length_m": model.get("track_length_m"),
                "track_points": model.get("track_points", []), "ideal_lap": model.get("ideal_lap"),
            }}


def analyze_qualifying(model, start_soc=None, minimum_finish_soc=5.0,
                       minimum_start_line_soc=80.0):
    general = optimize_qualifying(
        model, start_soc, minimum_finish_soc, personal=False,
        deployment_mode="overtake", minimum_start_line_soc=minimum_start_line_soc)
    if model.get("personal", {}).get("status") == "available":
        personal = optimize_qualifying(
            model, start_soc, minimum_finish_soc, personal=True,
            deployment_mode="overtake", minimum_start_line_soc=minimum_start_line_soc)
    else:
        personal = {"analyzable": False, "reason": "Personal recommendationはサンプル不足です"}
    return {
        "analyzable": general.get("analyzable", False), "general": general,
        "personal": personal, "deployment_mode": "overtake",
        "model_summary": {
            "model_version": model.get("model_version"), "source": model.get("source"),
            "personal": model.get("personal"), "track_length_m": model.get("track_length_m"),
            "track_points": model.get("track_points", []), "ideal_lap": model.get("ideal_lap"),
        },
    }
