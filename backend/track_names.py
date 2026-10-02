"""Human-readable circuit names for F1 UDP track identifiers."""

TRACK_NAMES = {
    # F1 25 UDP appendix. Retired/unused IDs are intentionally omitted so an
    # old table cannot silently assign the wrong circuit name.
    0: "Melbourne", 2: "Shanghai", 3: "Bahrain", 4: "Catalunya",
    5: "Monaco", 6: "Montreal", 7: "Silverstone", 9: "Hungaroring",
    10: "Spa", 11: "Monza", 12: "Singapore", 13: "Suzuka",
    14: "Abu Dhabi", 15: "COTA", 16: "Brazil", 17: "Austria",
    19: "Mexico", 20: "Baku", 26: "Zandvoort", 27: "Imola",
    29: "Jeddah", 30: "Miami", 31: "Las Vegas", 32: "Losail",
    39: "Silverstone Reverse", 40: "Austria Reverse",
    41: "Zandvoort Reverse",
}


def track_name(track_id):
    return TRACK_NAMES.get(track_id, f"Unknown Track {track_id}")


def track_slug(track_id):
    return track_name(track_id).lower().replace(" ", "-")
