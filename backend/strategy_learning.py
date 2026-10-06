"""Rank controlled ERS experiments from recorded coverage, not predicted gains."""
from statistics import median

from telemetry_quality import number


REPEAT_TARGET = 3  # Coverage goal, not a claim of statistical accuracy.


def summarize_learning_evidence(observations):
    """One observation per saved lap; missing activation flags are never 'off'."""
    unique = {row["lap_id"]: row for row in observations}
    groups = {}
    for action in ("none", "boost", "overtake"):
        rows = [row for row in unique.values() if row.get("deployment_recorded")
                and row["action"] == action and number(row.get("soc_delta")) is not None]
        deltas = [row["soc_delta"] for row in rows]
        center = median(deltas) if deltas else None
        groups[action] = {
            "count": len(rows), "lap_ids": [row["lap_id"] for row in rows],
            "soc_delta_median": center,
            "soc_delta_mad": median(abs(value - center) for value in deltas) if deltas else None,
            "entries": [{"soc": row.get("start_soc"), "speed": row.get("entry_speed")}
                        for row in rows],
        }
    return {"actions": groups, "unknown_activation_laps": sum(
        not row.get("deployment_recorded") for row in unique.values())}


def _entry_matches(a, b):
    return (all(number(row.get(key)) is not None for row in (a, b) for key in ("soc", "speed"))
            and abs(a["soc"] - b["soc"]) <= 10 and abs(a["speed"] - b["speed"]) <= 15)


def suggest_ers_experiments(model, deployment_mode="boost"):
    """Suggest a single changed section per lap and its matching control run."""
    if not model.get("analyzable"):
        return {"analyzable": False, "reason": model.get("reason")}
    mode = deployment_mode if deployment_mode in ("boost", "overtake") else "boost"
    candidates, excluded = [], {}
    for section in model["sections"]:
        # Restrict experiments to recorded steady throttle stretches. This is
        # a suitability heuristic, not a statement that a track segment is safe.
        if (section.get("kind") not in ("flat_out", "acceleration")
                or section["end_distance"] - section["start_distance"] < 150
                or (number(section.get("average_throttle")) or 0) < .9
                or number(section.get("average_brake")) is None
                or section["average_brake"] > .03
                or number(section.get("peak_slip")) is None or section["peak_slip"] > .15):
            excluded["unsuitable_input_or_slip"] = excluded.get("unsuitable_input_or_slip", 0) + 1
            continue
        evidence = section.get("learning_evidence", {})
        groups = evidence.get("actions", {})
        baseline, deployed = groups.get("none", {}), groups.get(mode, {})
        n_off, n_on = baseline.get("count", 0), deployed.get("count", 0)
        if not any(row.get("count", 0) for row in groups.values()):
            excluded["no_recorded_mode_or_control"] = excluded.get("no_recorded_mode_or_control", 0) + 1
            continue
        paired = sum(any(_entry_matches(on, off) for off in baseline.get("entries", []))
                     for on in deployed.get("entries", []))
        scatter = max(number(row.get("soc_delta_mad")) or 0 for row in (baseline, deployed))
        if n_off == n_on == 0:
            reason, priority = "missing_pair", 110
        elif n_on == 0:
            reason, priority = "missing_mode", 100
        elif n_off == 0:
            reason, priority = "missing_baseline", 100
        elif min(n_off, n_on) < REPEAT_TARGET:
            reason, priority = "few_repeats", 60
        elif paired < REPEAT_TARGET:
            reason, priority = "unmatched_entry", 45
        elif scatter > .25:
            reason, priority = "variable_energy", 25
        else:
            continue
        next_action = mode if n_off > 0 and n_on <= n_off else "none"
        opposite = baseline if next_action == mode else deployed
        entry_soc = [row["soc"] for row in opposite.get("entries", []) if number(row.get("soc")) is not None]
        candidates.append({
            "section_number": section["number"], "label": section.get("label"),
            "start_distance": section["start_distance"], "end_distance": section["end_distance"],
            "action": next_action, "control_action": "none" if next_action == mode else mode,
            "deployment_mode": mode, "reason": reason,
            "priority": round(priority + 3 * max(0, REPEAT_TARGET - min(n_off, n_on))
                              + min(scatter, 5), 3),
            "baseline_laps": n_off, "deployment_laps": n_on, "matched_entry_laps": paired,
            "baseline_lap_ids": baseline.get("lap_ids", []),
            "deployment_lap_ids": deployed.get("lap_ids", []),
            "soc_delta_mad": round(scatter, 3) if n_off or n_on else None,
            "suggested_entry_soc": round(median(entry_soc), 1) if entry_soc else None,
            "repeats_needed": {"none": max(0, REPEAT_TARGET - n_off), mode: max(0, REPEAT_TARGET - n_on)},
        })
    candidates.sort(key=lambda row: (-row["priority"], row["start_distance"]))
    targets = [dict(row, rank=index + 1) for index, row in enumerate(candidates[:3])]
    unknown = model.get("selection", {}).get("unknown_conditions", [])
    return {
        "analyzable": True, "method": "recorded-coverage-experiments-v1", "deployment_mode": mode,
        "targets": targets, "candidate_count": len(candidates), "excluded_sections": excluded,
        "repeat_target": REPEAT_TARGET, "unknown_conditions": unknown,
        "message": ("Test one highlighted section at a time, then rebuild after recording."
                    if targets else "No suitable evidence gaps found. Check activation data and comparison conditions, or choose another reference lap."),
        "assumptions": [
            "Practice priorities describe missing comparisons and observed variation, not predicted lap-time gains.",
            "Practice uses all compatible valid laps, including slower laps; recorded race-length mismatches are excluded.",
            "Missing Boost or Overtake activation flags are not counted as no deployment.",
            "Three repeats per action is a coverage goal, not a guarantee of accuracy.",
            "Change ERS in one section only. Keep setup, compound, fuel, wear, entry speed, starting charge and other inputs similar.",
            "Repeat with and without the selected mode at the same distance markers. Avoid empty or fully charged battery, traffic and pit laps; use Overtake only when available in-game.",
            "The map uses recorded steady-throttle sections. End deployment before braking and skip the test if grip or battery reserve is insufficient.",
        ],
    }
