"""SOC-constrained single-lap DP and 3-5 lap receding-horizon strategy."""


DEPLOYMENT_ACTIONS = ("boost", "overtake")
LIFT_ACTIONS = ("lift_10", "lift_20", "lift_30")


def _number(value, default=0.0):
    try:
        value = float(value)
        return value if value == value else default
    except (TypeError, ValueError):
        return default


def _apply_prediction(section, action, fraction):
    none = section["actions"]["none"]
    prediction = section["actions"][action]
    interpolate = lambda key: (_number(none.get(key))
                               + (_number(prediction.get(key)) - _number(none.get(key))) * fraction)
    return {
        "time_ms": interpolate("predicted_time_ms"),
        "soc_delta": interpolate("soc_delta"),
        "clipping_probability": interpolate("clipping_probability"),
        "super_clipping_probability": interpolate("super_clipping_probability"),
    }


def _options(section, scenario, deployment_mode="boost"):
    yield "none", 1.0, _apply_prediction(section, "none", 1.0)
    kind = section.get("kind")
    if scenario == "no_deployment":
        return
    actions = []
    if kind in ("acceleration", "flat_out"):
        actions.append(deployment_mode if deployment_mode in DEPLOYMENT_ACTIONS else "boost")
    if scenario == "lift_and_deploy" and kind in ("lift", "acceleration", "flat_out"):
        actions.extend(LIFT_ACTIONS)
    for action in actions:
        source = section["actions"][action]
        confidence = _number(source.get("confidence"), 0.0)
        if action == "overtake" and (source.get("evidence") != "observed" or confidence < .35):
            continue
        if action in DEPLOYMENT_ACTIONS and (
                _number(source.get("clipping_probability")) >= .5
                or _number(source.get("super_clipping_probability")) >= .25):
            continue
        fractions = ((.25, .5) if action == "boost" and source.get("evidence") != "observed"
                     else (.25, .5, .75, 1.0))
        for fraction in fractions:
            yield action, fraction, _apply_prediction(section, action, fraction)


def _simulate_none(model, start_soc, horizon):
    soc = start_soc
    total_time = 0.0
    trajectory = []
    for lap_index in range(horizon):
        lap_start, lap_time = soc, 0.0
        for section in model["sections"]:
            prediction = section["actions"]["none"]
            soc = max(0.0, min(100.0, soc + _number(prediction.get("soc_delta"))))
            lap_time += _number(prediction.get("predicted_time_ms"))
        total_time += lap_time
        trajectory.append({"lap_index": lap_index, "soc_start": lap_start,
                           "soc_end": soc, "predicted_lap_time_ms": lap_time})
    return total_time, soc, trajectory


def _optimize_path(model, start_soc, target_soc, scenario, horizon=1, soc_step=.25,
                   minimum_running_soc=0.0, deployment_mode="boost"):
    sections = model["sections"]
    states = {round(start_soc / soc_step): {
        "objective": 0.0, "time_ms": 0.0, "soc": start_soc, "path": [],
    }}
    for lap_index in range(horizon):
        for section in sections:
            next_states = {}
            for state in states.values():
                for action, fraction, prediction in _options(section, scenario, deployment_mode):
                    next_soc = state["soc"] + prediction["soc_delta"]
                    if next_soc < -.001:
                        if minimum_running_soc <= 0:
                            next_soc = 0.0
                        else:
                            continue
                    if state["soc"] < minimum_running_soc:
                        if action in DEPLOYMENT_ACTIONS or next_soc + .001 < state["soc"]:
                            continue
                    elif next_soc < minimum_running_soc - .001:
                        continue
                    next_soc = min(100.0, next_soc)
                    key = round(next_soc / soc_step)
                    clipping_penalty = (prediction["clipping_probability"] * 35.0
                                        + prediction["super_clipping_probability"] * 160.0)
                    tyre_penalty = max(0.0, _number(section["actions"][action].get("tyre_cost"))) * lap_index * 25.0
                    source = section["actions"][action]
                    confidence_penalty = ((1 - _number(source.get("confidence"), 0.0)) * 55.0 * fraction
                                          if action in DEPLOYMENT_ACTIONS and source.get("evidence") != "observed"
                                          else 0.0)
                    objective = (state["objective"] + prediction["time_ms"] + clipping_penalty
                                 + tyre_penalty + confidence_penalty)
                    existing = next_states.get(key)
                    if existing is None or objective < existing["objective"]:
                        next_states[key] = {
                            "objective": objective,
                            "time_ms": state["time_ms"] + prediction["time_ms"] + tyre_penalty,
                            "soc": next_soc,
                            "path": state["path"] + [(lap_index, section, action, fraction, prediction)],
                        }
            if not next_states:
                return None
            states = next_states
    tolerance = soc_step * .8
    feasible = [state for state in states.values() if abs(state["soc"] - target_soc) <= tolerance]
    pool = feasible or list(states.values())
    return min(pool, key=lambda state: state["objective"] + abs(state["soc"] - target_soc) * 2000.0)


def _allocation(section, action, fraction, prediction):
    none = section["actions"]["none"]
    incremental_soc = prediction["soc_delta"] - _number(none.get("soc_delta"))
    time_delta = prediction["time_ms"] - _number(none.get("predicted_time_ms"))
    return {
        "section_number": section["number"], "label": section.get("label"),
        "kind": section.get("kind"), "start_distance": section["start_distance"],
        "end_distance": section["end_distance"], "action": action,
        "applied_fraction": round(fraction, 2), "time_delta_ms": round(time_delta, 1),
        "incremental_soc_delta": round(incremental_soc, 3),
        "evidence": section["actions"][action].get("evidence"),
        "confidence": section["actions"][action].get("confidence"),
        "clipping_probability": round(prediction["clipping_probability"], 3),
        "super_clipping_probability": round(prediction["super_clipping_probability"], 3),
    }


def _summarize_path(model, state, start_soc, target_soc, horizon, baseline_time):
    sections_per_lap = len(model["sections"])
    trajectory = []
    soc = start_soc
    all_allocations = []
    for lap_index in range(horizon):
        rows = state["path"][lap_index * sections_per_lap:(lap_index + 1) * sections_per_lap]
        lap_start, lap_time = soc, 0.0
        allocations = []
        soc_trace = [{"distance": 0.0, "soc": round(soc, 3), "action": "start"}]
        deployment_gain = lift_loss = soc_used = soc_recovered = 0.0
        max_clip = max_super = 0.0
        for _, section, action, fraction, prediction in rows:
            none = section["actions"]["none"]
            lap_time += prediction["time_ms"]
            soc = max(0.0, min(100.0, soc + prediction["soc_delta"]))
            soc_trace.append({"distance": round(section["end_distance"], 1),
                              "soc": round(soc, 3), "action": action,
                              "section_number": section["number"]})
            max_clip = max(max_clip, prediction["clipping_probability"])
            max_super = max(max_super, prediction["super_clipping_probability"])
            if action == "none":
                continue
            allocation = _allocation(section, action, fraction, prediction)
            allocations.append(allocation)
            all_allocations.append(allocation | {"lap_index": lap_index})
            if action in DEPLOYMENT_ACTIONS:
                deployment_gain += max(0.0, -allocation["time_delta_ms"])
                soc_used += max(0.0, -allocation["incremental_soc_delta"])
            else:
                lift_loss += max(0.0, allocation["time_delta_ms"])
                soc_recovered += max(0.0, allocation["incremental_soc_delta"])
        delta = soc - lap_start
        if delta < -2:
            level = "attack"
        elif delta < -.5:
            level = "fast"
        elif delta > .5:
            level = "save"
        else:
            level = "sustainable"
        trajectory.append({
            "lap_index": lap_index, "level": level,
            "label": {"attack": "Attack", "fast": "Fast", "sustainable": "Sustainable",
                      "save": "Save / Recharge"}[level],
            "soc_start": round(lap_start, 2), "soc_end": round(soc, 2), "delta_soc": round(delta, 2),
            "minimum_soc": round(min(point["soc"] for point in soc_trace), 2),
            "soc_trace": soc_trace,
            "predicted_lap_time_ms": round(lap_time, 1),
            "deployment_gain_ms": round(deployment_gain, 1), "lifting_loss_ms": round(lift_loss, 1),
            "soc_used": round(soc_used, 3), "soc_recovered": round(soc_recovered, 3),
            "clipping_probability": round(max_clip, 3),
            "super_clipping_probability": round(max_super, 3), "allocations": allocations,
        })
    predicted_time = sum(row["predicted_lap_time_ms"] for row in trajectory)
    return {
        "predicted_total_time_ms": round(predicted_time, 1),
        "predicted_lap_time_ms": round(predicted_time / horizon, 1),
        "start_soc": round(start_soc, 2), "target_finish_soc": round(target_soc, 2),
        "predicted_finish_soc": round(soc, 2), "finish_soc_error": round(soc - target_soc, 3),
        "net_gain_vs_no_deployment_ms": round(baseline_time - predicted_time, 1),
        "soc_used": round(sum(row["soc_used"] for row in trajectory), 3),
        "soc_recovered": round(sum(row["soc_recovered"] for row in trajectory), 3),
        "deployment_gain_ms": round(sum(row["deployment_gain_ms"] for row in trajectory), 1),
        "lifting_loss_ms": round(sum(row["lifting_loss_ms"] for row in trajectory), 1),
        "allocations": all_allocations, "trajectory": trajectory,
    }


def _run_scenario(model, identifier, label, start_soc, target_soc, horizon, baseline_time,
                  deployment_mode):
    state = _optimize_path(model, start_soc, target_soc, identifier, horizon,
                           deployment_mode=deployment_mode)
    if state is None:
        return {"id": identifier, "label": label, "analyzable": False,
                "reason": "SOC制約を満たす経路がありません"}
    result = _summarize_path(model, state, start_soc, target_soc, horizon, baseline_time)
    return {"id": identifier, "label": label, "analyzable": True, **result}


def compare_strategy_scenarios(model, start_soc=None, deployment_mode="boost"):
    """Optimize three one-lap scenarios at the same start and finish SOC."""
    if not model.get("analyzable"):
        return {"analyzable": False, "reason": model.get("reason")}
    start_soc = max(0.0, min(100.0, _number(
        model.get("initial_soc") if start_soc is None else start_soc, 100.0)))
    deployment_mode = deployment_mode if deployment_mode in DEPLOYMENT_ACTIONS else "boost"
    mode_label = "Boost" if deployment_mode == "boost" else "Overtake"
    baseline_time, target_soc, _ = _simulate_none(model, start_soc, 1)
    specifications = (
        ("no_deployment", "No deployment"),
        ("deployment_only", f"{mode_label} only"),
        ("lift_and_deploy", f"Lift + {mode_label}"),
    )
    scenarios = [_run_scenario(model, identifier, label, start_soc, target_soc, 1, baseline_time,
                               deployment_mode)
                 for identifier, label in specifications]
    valid = [row for row in scenarios if row.get("analyzable")]
    fastest = min(valid, key=lambda row: row["predicted_total_time_ms"])
    lift = next(row for row in scenarios if row["id"] == "lift_and_deploy")
    return {
        "analyzable": True, "method": "same-finish-soc-section-dp-v2", "is_optimized": True,
        "deployment_mode": deployment_mode,
        "soc_step": .25, "start_soc": round(start_soc, 2), "common_finish_soc": round(target_soc, 2),
        "scenarios": scenarios, "fastest_scenario": fastest["id"],
        "estimated_best_gain_ms": fastest["net_gain_vs_no_deployment_ms"],
        "conclusion": ("Liftで回収したSOCの再配置により短縮見込みがあります。"
                       if lift.get("net_gain_vs_no_deployment_ms", 0) > 0
                       else "同一終了SOCでは追加リフトの利益を確認できません。"),
    }


def _minimum_reachable_soc(model, start_soc, horizon, deployment_mode="boost"):
    """Return the lowest SOC represented by the available section actions."""
    soc = start_soc
    for _ in range(horizon):
        for section in model["sections"]:
            soc += min(prediction["soc_delta"]
                       for _, _, prediction in _options(section, "lift_and_deploy", deployment_mode))
            soc = max(0.0, min(100.0, soc))
    return soc


def optimize_multi_lap_strategy(model, horizon=5, remaining_laps=None, start_soc=None,
                                minimum_finish_soc=5.0, deployment_mode="boost"):
    """Optimize 3-5 laps; only the first-lap recommendation is adopted."""
    if not model.get("analyzable"):
        return {"analyzable": False, "reason": model.get("reason")}
    horizon = max(3, min(5, int(horizon)))
    remaining_laps = None if remaining_laps in (None, "") else max(1, int(remaining_laps))
    if remaining_laps is not None:
        horizon = min(horizon, remaining_laps)
    deployment_mode = deployment_mode if deployment_mode in DEPLOYMENT_ACTIONS else "boost"
    start_soc = max(0.0, min(100.0, _number(
        model.get("current_state", {}).get("soc") if start_soc is None else start_soc,
        model.get("initial_soc", 100.0))))
    baseline_time, baseline_finish, baseline_trajectory = _simulate_none(model, start_soc, horizon)
    finishing_race = remaining_laps is not None and remaining_laps <= horizon
    requested_finish_soc = max(0.0, min(start_soc, float(minimum_finish_soc)))
    minimum_reachable_soc = _minimum_reachable_soc(model, start_soc, horizon, deployment_mode)
    target_soc = (max(requested_finish_soc, minimum_reachable_soc)
                  if finishing_race else baseline_finish)
    safety_soc_floor = max(0.0, min(30.0, float(minimum_finish_soc)))
    state = _optimize_path(model, start_soc, target_soc, "lift_and_deploy", horizon,
                           soc_step=.5, minimum_running_soc=safety_soc_floor,
                           deployment_mode=deployment_mode)
    if state is None:
        return {"analyzable": False, "reason": "予測期間内でSOC制約を満たせません"}
    result = _summarize_path(model, state, start_soc, target_soc, horizon, baseline_time)
    return {
        "analyzable": True, "method": "receding-horizon-section-dp-v1", "horizon_laps": horizon,
        "deployment_mode": deployment_mode,
        "remaining_laps": remaining_laps, "finishing_race": finishing_race,
        "requested_minimum_finish_soc": round(requested_finish_soc, 2),
        "safety_soc_floor": round(safety_soc_floor, 2),
        "minimum_reachable_soc": round(minimum_reachable_soc, 2),
        "minimum_soc_unreachable": finishing_race and minimum_reachable_soc > requested_finish_soc + .5,
        "baseline_no_deployment_time_ms": round(baseline_time, 1),
        "baseline_soc_trajectory": [round(row["soc_end"], 2) for row in baseline_trajectory],
        "soc_target_trajectory": [row["soc_end"] for row in result["trajectory"]],
        "current_lap_recommendation": result["trajectory"][0],
        "recalculate_next_lap": True, **result,
    }
