"""Checks for data isolation, frozen resources and stoppable UDP reception."""
import importlib.util
import json
from pathlib import Path
import socket
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
import desktop
import analysis_freshness
from runtime_paths import resource_root
from telemetry import udp_loop
from lap_recorder import LapRecorder
from storage import LapStorage


def test_frozen_rules_match_source_without_python_files(tmp_path, monkeypatch):
    expected = analysis_freshness.rules_signature()
    (tmp_path / "build-info.json").write_text(json.dumps({"rules_signature": expected}), encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert resource_root() == tmp_path
    assert analysis_freshness.rules_signature() == expected


def test_test_copy_is_separate_and_does_not_overwrite_edits(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    original = bundle / "test-laps" / "example" / "lap.json"
    original.parent.mkdir(parents=True)
    original.write_text('{"note":"original"}', encoding="utf-8")
    monkeypatch.setattr(desktop, "resource_root", lambda: bundle)
    home = tmp_path / "userdata"
    home.mkdir()
    live = home / "sessions" / "lap.json"
    live.parent.mkdir()
    live.write_text("live", encoding="utf-8")
    copied = desktop.seed_test_laps(home) / "example" / "lap.json"
    copied.write_text('{"note":"edited"}', encoding="utf-8")
    desktop.seed_test_laps(home)
    assert json.loads(copied.read_text())["note"] == "edited"
    assert json.loads(original.read_text())["note"] == "original"
    assert live.read_text() == "live"


def test_recording_socket_stops_and_releases_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    address = sock.getsockname()
    stop = threading.Event()
    thread = threading.Thread(target=udp_loop, args=({}, None, sock, stop))
    thread.start()
    stop.set()
    thread.join(2)
    assert not thread.is_alive()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as replacement:
        replacement.bind(address)


def test_completed_laps_are_flushed_before_shutdown(tmp_path):
    storage = LapStorage(tmp_path)
    recorder = LapRecorder(storage)
    lap = {"lapNumber": 1, "lapTimeMs": 90000, "validLap": True,
           "trackId": 3, "sessionUid": 123, "sampleCount": 1, "samples": []}
    recorder._queue.put(lap)
    assert recorder.flush(5)
    assert storage.list_laps()[0]["lapTimeMs"] == 90000


def test_instance_lock_releases_after_close(tmp_path):
    import pytest
    path = tmp_path / "mode.lock"
    first = desktop.InstanceLock(path)
    try:
        with pytest.raises(RuntimeError, match="already open"):
            desktop.InstanceLock(path)
    finally:
        first.close()
    second = desktop.InstanceLock(path)
    second.close()


def test_test_preparation_cannot_target_original_recordings(tmp_path):
    import pytest
    spec = importlib.util.spec_from_file_location("prepare_test_laps", ROOT / "scripts" / "prepare_test_laps.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match="separate"):
        module.prepare(tmp_path, tmp_path)
