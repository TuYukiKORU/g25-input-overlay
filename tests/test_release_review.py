"""Release fault checks: disk failures, queue overflow and local HTTP isolation."""
import queue
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from lap_recorder import LapRecorder
from desktop_security import protect_desktop_server


@pytest.mark.parametrize("error", [OSError("disk full"), ValueError("invalid lap value")])
def test_save_failure_is_visible_and_writer_survives(error):
    class Storage:
        count = 0
        laps = []
        def save_lap(self, lap):
            self.count += 1
            if self.count == 1:
                raise error
            self.laps.append(lap)
    storage = Storage()
    recorder = LapRecorder(storage)
    recorder._queue.put({"lapNumber": 1})
    assert not recorder.flush(2)
    assert recorder.persistence_status()["save_errors"] == 1
    recorder._queue.put({"lapNumber": 2})
    assert not recorder.flush(2)  # Previous failures must not be hidden by recovery.
    assert storage.laps == [{"lapNumber": 2}]
    assert recorder.persistence_status()["pending_laps"] == 0


def test_queue_overflow_is_visible_without_blocking_receiver(monkeypatch, caplog):
    from test_recorder import MemoryStorage, state
    recorder = LapRecorder(MemoryStorage())
    def full(*args):
        raise queue.Full
    monkeypatch.setattr(recorder._queue, "put_nowait", full)
    for distance in range(0, 2100, 100):
        recorder.observe(state(1, distance, distance * 20))
    recorder.observe(state(2, 0, 1000))
    assert recorder.persistence_status()["queue_overflows"] == 1
    assert not recorder.flush(.1)
    assert "was not saved" in caplog.text
    assert recorder.current["lapNumber"] == 2


def test_save_failure_reaches_recording_health_api(monkeypatch):
    import app as app_module
    status = {"ok": False, "save_errors": 1, "queue_overflows": 0, "pending_laps": 0}
    monkeypatch.setattr(app_module, "recorder", SimpleNamespace(persistence_status=lambda: status))
    assert app_module.app.test_client().get("/api/recording-health").get_json()["saving"] == status


@pytest.fixture
def desktop_client():
    app = Flask(__name__)
    protect_desktop_server(app, "http://127.0.0.1:6123")
    @app.route("/probe", methods=["GET", "POST", "PUT"])
    def probe():
        return {"body": __import__('flask').request.get_data(as_text=True)}
    return app.test_client()


def test_own_window_and_local_test_clients_remain_allowed(desktop_client):
    response = desktop_client.get("/probe", base_url="http://127.0.0.1:6123")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert desktop_client.put("/probe", base_url="http://127.0.0.1:6123", headers={"Origin":"http://127.0.0.1:6123"}, json={}).status_code == 200


@pytest.mark.parametrize("headers", [{"Host":"untrusted.example:6123"},
    {"Origin":"https://untrusted.example"}, {"Origin":"null"},
    {"Origin":"http://127.0.0.1:6124"}, {"Sec-Fetch-Site":"cross-site"}])
def test_foreign_host_and_browser_origins_are_rejected(desktop_client, headers):
    assert desktop_client.post("/probe", base_url="http://127.0.0.1:6123", headers=headers).status_code == 403


def test_oversized_request_is_rejected(desktop_client):
    assert desktop_client.post("/probe", base_url="http://127.0.0.1:6123", data=b'x'*(1024*1024+1)).status_code == 413
