"""Small, version-independent preferences stored outside the executable."""
import ctypes
import json
import os
from pathlib import Path
import threading


class DesktopPreferences:
    def __init__(self, home):
        self.path = Path(home) / "preferences.json"
        self.lock = threading.RLock()
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        if not isinstance(saved, dict):
            saved = {}
        try:
            default = "ja" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x11 else "en"
        except AttributeError:
            default = "en"
        self.language = saved.get("language") if saved.get("language") in ("en", "ja") else default

    def save_language(self, language):
        if language not in ("en", "ja"):
            raise ValueError("Language must be en or ja")
        with self.lock:
            # Preserve other preferences when future versions introduce them.
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    value = {}
            except (OSError, ValueError):
                value = {}
            value["language"] = language
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".json.tmp")
            with temporary.open("w", encoding="utf-8") as out:
                json.dump(value, out, ensure_ascii=False, indent=2)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, self.path)
            self.language = language
        return {"language": language}
