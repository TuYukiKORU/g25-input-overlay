"""Explain comparison conditions without estimating causal time penalties."""
from math import isfinite


def number(value):
    try:
        value = float(value)
        return value if isfinite(value) else None
    except (ValueError, TypeError):
        return None


def conditions(lap):
    first = next(iter(lap.get("samples") or []), {})
    wear = [number(v) for v in (lap.get("tyreWearAtStart") or {}).values()]
    wear = [v for v in wear if v is not None]
    return {
        "compound": lap.get("tyreCompound"),
        "setup": lap.get("setupId"),
        "fuel": number(lap.get("fuelInTankKgAtStart") if lap.get("fuelInTankKgAtStart") is not None else first.get("fuel_in_tank_kg")),
        "wear": sum(wear) / len(wear) if wear else None,
        "ers": number(first.get("ers_percent")),
    }


def comparison_context(selected, reference):
    a, b = conditions(selected), conditions(reference)
    notes, score, unknown = [], 0.0, 0
    for key, label, tolerance, unit in (
        ("compound", "Tyre compound", None, ""), ("setup", "Setup", None, ""),
        ("fuel", "Starting fuel", 3.0, " kg"), ("wear", "Starting tyre wear", 3.0, "%"),
        ("ers", "Starting ERS charge", 10.0, "%"),
    ):
        x, y = a[key], b[key]
        if x is None or y is None or x == "" or y == "":
            unknown += 1
            score += 2
            notes.append(f"{label}: unknown")
        elif tolerance is None:
            if x != y:
                score += 10
                notes.append(f"{label}: different")
        else:
            gap = abs(x - y)
            score += min(gap / tolerance, 10)
            if gap > tolerance:
                notes.append(f"{label}: selected {x:.1f}{unit}, comparison {y:.1f}{unit}")
    for owner, lap in (("Selected lap", selected), ("Comparison lap", reference)):
        if lap.get("validLap") is False:
            notes.append(f"{owner}: invalid")
        if lap.get("pitLaneUsed") or any(s.get("pit_status") for s in lap.get("samples", [])):
            notes.append(f"{owner}: pit lane used")
    return {"score": round(score, 3), "notes": notes, "unknown_fields": unknown,
            "label": "Conditions differ or are unknown" if notes else "Similar recorded conditions"}


def recording_gaps(lap, limit=50.0):
    distances = sorted({v for s in lap.get("samples", [])
                        if (v := number(s.get("lap_distance"))) is not None})
    return [{"start_distance": a, "end_distance": b} for a, b in zip(distances, distances[1:]) if b - a > limit]
