"""Compatibility API over the single shared race-energy planner."""
from copy import deepcopy
from qualifying_optimizer import _adjusted_time
from strategy_scenarios import optimize_multi_lap_strategy


def optimize_race(model, horizon=5, current_soc=None, minimum_soc=5.0,
                  remaining_laps=None, personal=False, deployment_mode="boost"):
    source = model
    if personal and model.get("analyzable"):
        source = deepcopy(model)
        for section in source["sections"]:
            for action in section["actions"]:
                section["actions"][action]["predicted_time_ms"] = _adjusted_time(section, action, True)
    result = optimize_multi_lap_strategy(source, horizon=horizon, remaining_laps=remaining_laps,
                                        start_soc=current_soc, minimum_finish_soc=minimum_soc,
                                        deployment_mode=deployment_mode)
    return result | {"strategy_type": "personal" if personal else "general"}


def analyze_race(model, horizon=5, current_soc=None, minimum_soc=5.0, remaining_laps=None):
    general = optimize_race(model, horizon, current_soc, minimum_soc, remaining_laps)
    personal = (optimize_race(model, horizon, current_soc, minimum_soc, remaining_laps, True)
                if model.get("personal", {}).get("status") == "available"
                else {"analyzable": False, "reason": "Personal recommendation has insufficient samples."})
    return {"analyzable": general.get("analyzable", False), "general": general, "personal": personal,
            "model_summary": {key: model.get(key) for key in
                              ("model_version", "source", "personal", "track_length_m", "track_points", "ideal_lap")}}
