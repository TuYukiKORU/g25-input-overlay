"""One strategy result shape for race energy, comparison and qualifying goals."""
from collections import Counter
from qualifying_optimizer import optimize_qualifying
from strategy_scenarios import compare_strategy_scenarios, optimize_multi_lap_strategy
from telemetry_quality import lap_quality, select_strategy_laps, number


def workspace_context(entries, session_id, selected_lap_id=None, pace_window_percent=8, max_laps=40):
    selected, info = select_strategy_laps(entries, session_id, selected_lap_id, pace_window_percent, max_laps)
    session_laps = []
    for lap_id, lap in entries:
        if str(lap_id).split("/", 1)[0] != session_id:
            continue
        quality = lap_quality(lap)
        soc = next((value for s in reversed(lap.get("samples", []))
                    if (value := number(s.get("ers_soc") if s.get("ers_soc") is not None else s.get("ers_percent"))) is not None
                    and 0 <= value <= 100), None)
        session_laps.append({"id": lap_id, "lap_number": lap.get("lapNumber"), "lap_time_ms": lap.get("lapTimeMs"),
                             "valid": lap.get("validLap"), "end_soc": soc, **quality})
    session_laps.sort(key=lambda item: item.get("lap_number") or 0)
    reference = info.get("reference_quality")
    return {"laps": session_laps, "reference_lap_id": info.get("reference_lap_id"),
            "readiness": {"ready": len(selected) >= 2, "reason": info.get("reason"),
                          "edition": reference.get("edition") if reference else None,
                          "energy": reference.get("energy") if reference else {"available": False},
                          "geometry": reference.get("geometry") if reference else {"available": False}},
            "comparable_lap_count": len(selected), "excluded": info.get("excluded", {}),
            "unknown_conditions": info.get("unknown_conditions", [])}


def analyze_workspace(model, settings):
    goal = settings.get("goal", "race")
    mode = settings.get("deployment_mode", "boost")
    start = settings.get("start_soc")
    reserve = settings.get("minimum_soc", 5)
    if goal == "qualifying":
        plan = optimize_qualifying(model, start, reserve,
                                   minimum_start_line_soc=settings.get("minimum_start_line_soc", 80))
    elif goal == "compare":
        plan = compare_strategy_scenarios(model, start, mode, minimum_soc=reserve)
    else:
        plan = optimize_multi_lap_strategy(model, settings.get("horizon", 3), settings.get("remaining_laps"),
                                           start, reserve, mode)
    evidence = Counter(a.get("evidence", "unknown") for s in model["sections"] for a in s["actions"].values())
    rejected = sum(not a.get("usable_for_plan", True) for s in model["sections"] for a in s["actions"].values())
    return {"analyzable": plan.get("analyzable", False), "reason": plan.get("reason"), "goal": goal, "plan": plan,
            "readiness": {"edition": 2026, "energy": {"available": True}, "geometry": model["geometry"]},
            "model_summary": {key: model.get(key) for key in ("model_version", "source", "selection", "track_length_m",
                                      "track_points", "geometry_source_lap_id", "current_state")},
            "reference_sections": [{key: s.get(key) for key in ("number", "kind", "label", "start_distance",
                                 "end_distance", "average_speed", "average_throttle", "average_brake")} for s in model["sections"]],
            "evidence": {"action_entries": dict(evidence), "rejected_action_entries": rejected,
                         "accuracy_validated": False},
            "assumptions": ["Recorded section medians are associations, not measured causal gains.",
                            "Unobserved actions use inferred effects; predictions have not been validated in-game.",
                            "Only matching recorded edition, track, compound, setup, fuel and wear conditions are included when known.",
                            "The next lap is actionable; later laps are a forecast to recalculate from measured battery.",
                            "Pit stops, traffic, weather changes and full-race tyre strategy are outside this energy model."]}
