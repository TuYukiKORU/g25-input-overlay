"""Human-readable names for F1 UDP session and game mode identifiers."""

SESSION_TYPE_NAMES = {
    0: "Unknown",
    1: "Practice 1", 2: "Practice 2", 3: "Practice 3",
    4: "Short Practice", 5: "Qualifying 1", 6: "Qualifying 2",
    7: "Qualifying 3", 8: "Short Qualifying", 9: "One-Shot Qualifying",
    10: "Sprint Shootout 1", 11: "Sprint Shootout 2",
    12: "Sprint Shootout 3", 13: "Short Sprint Shootout",
    14: "One-Shot Sprint Shootout", 15: "Race", 16: "Race 2",
    17: "Race 3", 18: "Time Trial",
}

GAME_MODE_NAMES = {
    4: "Grand Prix '23", 5: "Time Trial", 6: "Splitscreen",
    7: "Online Custom", 15: "Online Weekly Event",
    17: "Story Mode (Braking Point)", 27: "My Team Career '25",
    28: "Driver Career '25", 29: "Career '25 Online",
    30: "Challenge Career '25", 75: "Story Mode (APXGP)",
    127: "Benchmark",
}


def session_type_name(value):
    return SESSION_TYPE_NAMES.get(value, f"Unknown Session Type {value}")


def game_mode_name(value):
    if value is None:
        return "Unknown"
    return GAME_MODE_NAMES.get(value, f"Unknown Game Mode {value}")
