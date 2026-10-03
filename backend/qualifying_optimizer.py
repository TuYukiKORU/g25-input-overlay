"""Qualifying objective with run-up and reserve constraints over shared actions."""
from copy import deepcopy
from strategy_scenarios import _optimize_path, _summarize_path, _allocation, _options


def _adjusted_time(section, action, personal):
    value = float(section["actions"][action]["predicted_time_ms"])
    profile = section.get("personal") or {}
    if personal and profile.get("status") == "available" and action in ("boost", "overtake"):
        value += max(0, float(profile.get("peak_slip") or 0) - float(section.get("peak_slip") or 0)) * 180
        value += max(0, float(profile.get("time_residual_ms") or 0)) * .08
    return value


def _pre_start_runup(model, battery_before_runup_soc, minimum_start_line_soc, deployment_mode):
    section = next((s for s in reversed(model["sections"]) if s.get("kind") in ("acceleration", "flat_out")),
                   model["sections"][-1])
    prediction, none = section["actions"][deployment_mode], section["actions"]["none"]
    full_cost = (max(0, none["soc_delta"] - prediction["soc_delta"])
                 if any(action == deployment_mode for action, _, _ in
                        _options(section, "deployment_only", deployment_mode)) else 0)
    cost = min(full_cost, max(0, battery_before_runup_soc - minimum_start_line_soc))
    return {"action": deployment_mode, "battery_before_runup_soc": battery_before_runup_soc,
            "minimum_start_line_soc": minimum_start_line_soc, "predicted_soc_cost": round(cost, 3),
            "predicted_start_line_soc": round(battery_before_runup_soc - cost, 3),
            "applied_fraction": round(cost / full_cost, 3) if full_cost else 0,
            "source_section_number": section["number"], "source_start_distance": section["start_distance"],
            "source_end_distance": section["end_distance"], "evidence": prediction.get("evidence")}


def optimize_qualifying(model, start_soc=None, minimum_finish_soc=5, personal=False,
                        deployment_mode="overtake", minimum_start_line_soc=80):
    if not model.get("analyzable"):
        return {"analyzable": False, "reason": model.get("reason")}
    before = max(0, min(100, float(100 if start_soc is None else start_soc)))
    line_min = max(0, min(100, float(minimum_start_line_soc)))
    reserve = max(0, min(100, float(minimum_finish_soc)))
    if before < max(line_min, reserve):
        return {"analyzable": False, "reason": "Starting battery is below the requested timing-line or finish reserve."}
    mode = "boost" if deployment_mode == "boost" else "overtake"
    runup = _pre_start_runup(model, before, line_min, mode)
    start = runup["predicted_start_line_soc"]
    source = model
    if personal:
        source = deepcopy(model)
        for section in source["sections"]:
            for action in section["actions"]:
                section["actions"][action]["predicted_time_ms"] = _adjusted_time(section, action, True)
    baseline = sum(s["actions"]["none"]["predicted_time_ms"] for s in source["sections"])
    path = _optimize_path(source, start, reserve, "lift_and_deploy", minimum_running_soc=reserve,
                          deployment_mode=mode)
    if path is None:
        return {"analyzable": False, "reason": "The requested reserve cannot be maintained through the timed lap."}
    result = _summarize_path(source, path, start, reserve, 1, baseline)
    lap = result["trajectory"][0]
    allocations = []
    for index, (_, section, action, fraction, prediction) in enumerate(path["path"]):
        allocation = _allocation(section, action, fraction, prediction)
        allocation.update(soc_start=lap["soc_trace"][index]["soc"], soc_end=lap["soc_trace"][index+1]["soc"])
        allocation["soc_recovered"] = max(0, allocation["incremental_soc_delta"])
        allocations.append(allocation)
    result["allocations"] = allocations
    return {"analyzable": True, **result, "strategy_type": "personal" if personal else "general",
            "deployment_mode": mode, "pre_start_runup": runup, "battery_before_runup_soc": before,
            "start_line_soc": start, "minimum_finish_soc": reserve, "baseline_lap_time_ms": round(baseline, 1),
            "estimated_improvement_ms": result["net_gain_vs_no_deployment_ms"],
            "recommended_sections": lap["allocations"], "current_lap_recommendation": lap,
            "soc_trace": lap["soc_trace"], "clipping_predictions": [],
            "recommendation": "Estimated qualifying energy allocation; verify against the next recorded lap."}


def analyze_qualifying(model, start_soc=None, minimum_finish_soc=5, minimum_start_line_soc=80):
    general = optimize_qualifying(model, start_soc, minimum_finish_soc, minimum_start_line_soc=minimum_start_line_soc)
    personal = (optimize_qualifying(model, start_soc, minimum_finish_soc, True,
                                    minimum_start_line_soc=minimum_start_line_soc)
                if model.get("personal", {}).get("status") == "available"
                else {"analyzable": False, "reason": "Personal recommendation has insufficient samples."})
    return {"analyzable": general.get("analyzable", False), "general": general, "personal": personal,
            "deployment_mode": "overtake", "model_summary": {key: model.get(key) for key in
                ("model_version", "source", "personal", "track_length_m", "track_points", "ideal_lap")}}
