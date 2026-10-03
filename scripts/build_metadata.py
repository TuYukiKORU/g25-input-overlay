"""Write source-rule identities while source files are available to the builder."""
import argparse
import json
from pathlib import Path
import sys
from importlib.metadata import version

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from analysis_freshness import rules_signature

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="0.3.2-udp-preview")
    args = parser.parse_args()
    destination = ROOT / ".build-assets" / "build-info.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps({"version": args.version, "rules_signature": rules_signature(),
        "dependencies": {name: version(name) for name in ("Flask", "pywebview", "pyinstaller", "pythonnet")}}, indent=2), encoding="utf-8")
