"""Manually mark explicitly selected saved sessions as F1 26 Season Pack."""
import argparse
import json
from pathlib import Path


FIELDS = {
    "packetFormat": 2026,
    "gameYear": 26,
    "gameVersion": "F1 26",
    "udpMode": "2026 Season Pack",
}


def reclassify(root, session_ids):
    changed = []
    root = root.resolve()
    for session_id in session_ids:
        session_dir = (root / session_id).resolve()
        if session_dir.parent != root or not session_dir.is_dir():
            raise ValueError(f"Unknown session: {session_id}")
        for path in sorted(session_dir.rglob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not any(key in data for key in FIELDS):
                continue
            original = {key: data.get(key) for key in FIELDS}
            data.update(FIELDS)
            data["editionDetection"] = "manual_override"
            data["udpConfigurationWarning"] = (
                "Recorded through legacy F1 25 UDP; Boost, Overtake and Active Aero flags "
                "cannot be reconstructed. Select 2026 Season Pack UDP for future sessions."
            )
            data.setdefault("sourcePacketFormat", original["packetFormat"])
            data.setdefault("sourceGameYear", original["gameYear"])
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed.append(path)
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("session_ids", nargs="+")
    parser.add_argument("--root", type=Path, default=Path("data/sessions"))
    args = parser.parse_args()
    changed = reclassify(args.root, args.session_ids)
    print(f"Reclassified {len(changed)} JSON files as F1 26")


if __name__ == "__main__":
    main()
