"""Locate read-only assets in a source checkout or a PyInstaller bundle."""
import sys
from pathlib import Path


def resource_root():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]
