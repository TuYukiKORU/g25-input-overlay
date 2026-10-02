"""Windows entry point: own the window, local server and recording lifecycle."""
import argparse
import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT / "backend"))
from runtime_paths import resource_root


def data_home(override=None):
    if override:
        return Path(override).resolve()
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "F1Telemetry"


def seed_test_laps(home):
    """Seed once into a writable sandbox; never overwrite demo edits or live laps."""
    destination = home / "test-laps-v1"
    if destination.is_dir():
        return destination
    source = resource_root() / "test-laps"
    if not source.is_dir():
        source = PROJECT / ".build-assets" / "test-laps"
    if not source.is_dir():
        raise RuntimeError("Test laps are missing. Rebuild the package with prepare_test_laps.py.")
    staging = home / "test-laps-v1.installing"
    if staging.exists():
        if staging.resolve().parent != home.resolve() or staging.is_symlink():
            raise RuntimeError("The interrupted test-data copy points outside the data folder")
        shutil.rmtree(staging)
    shutil.copytree(source, staging)
    staging.rename(destination)
    return destination


class InstanceLock:
    """A Windows file lock, released automatically even if the app crashes."""
    def __init__(self, path):
        import msvcrt
        self.file = path.open("a+b")
        self.file.seek(0)
        self.file.write(b"0")
        self.file.flush()
        self.file.seek(0)
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            self.file.close()
            raise RuntimeError("This mode is already open. Switch to the existing F1 Telemetry window.") from error

    def close(self):
        self.file.close()


def show_error(message):
    ctypes.windll.user32.MessageBoxW(None, str(message), "F1 Telemetry", 0x10)


def configure_logging(home):
    logs = home / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(logs / "desktop.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(threadName)s %(message)s", force=True)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def smoke_window(window, server_url, report_path, demo):
    """Exercise the real embedded window and APIs, and close it after validation."""
    from urllib.request import Request, urlopen
    report = {"ok": False, "demo": demo, "url": server_url, "pid": os.getpid(),
              "frozen": bool(getattr(sys, "frozen", False)), "resource_root": str(resource_root())}
    try:
        if not window.events.loaded.wait(30):
            raise RuntimeError("Embedded page did not load")
        def read_api(route, body=None, method=None):
            payload = json.dumps(body).encode() if body is not None else None
            request = Request(server_url + route, data=payload, method=method,
                              headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        laps = read_api("/api/laps")
        report["lap_count"] = len(laps)
        report["health"] = read_api("/health")
        report["runtime"] = read_api("/api/desktop")
        from urllib.error import HTTPError
        rejected = []
        for header, value in (("Host", "untrusted.example"), ("Origin", "https://untrusted.example")):
            try:
                urlopen(Request(server_url + "/health", headers={header: value}), timeout=10)
                raise RuntimeError(f"Foreign {header} was accepted")
            except HTTPError as error:
                if error.code != 403:
                    raise
                rejected.append(header)
        report["foreign_requests_rejected"] = rejected
        report["initial_language"] = read_api("/api/desktop/preferences")["language"]
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            dom = window.evaluate_js("""(() => ({heading:document.querySelector('h1')?.textContent,
                sessions:document.querySelector('#sessionSelect')?.options.length || 0,
                laps:document.querySelector('#lapSelect')?.options.length || 0,
                message:document.querySelector('#message')?.textContent,
                canvases:document.querySelectorAll('canvas').length,
                painted:[...document.querySelectorAll('canvas')].filter(c =>
                    c.width && c.height && c.getContext('2d').getImageData(0,0,c.width,c.height).data.some(v => v)).length,
                banner:document.querySelector('#desktopStatus')?.textContent}))()""")
            if (not demo and dom["heading"] in ("Lap analysis", "ラップ分析")) or (demo and dom["laps"] and dom["painted"] >= 2):
                break
            time.sleep(0.25)
        report["dom"] = dom
        menu = window.evaluate_js("""({label:document.querySelector('#desktopFileMenu summary')?.textContent,
            actions:[...document.querySelectorAll('[data-desktop-action]')].map(button => ({
                action:button.dataset.desktopAction,enabled:!button.disabled,
                connected:typeof window.pywebview?.api[button.dataset.desktopAction] === 'function'}))})""")
        if len(menu["actions"]) != 4 or not all(action["enabled"] and action["connected"] for action in menu["actions"]):
            raise RuntimeError(f"Desktop file actions are unavailable: {menu}")
        report["desktop_menu"] = menu
        def evaluate_promise(expression):
            completed = threading.Event()
            values = []
            def callback(value):
                values.append(value)
                completed.set()
            window.evaluate_js(expression, callback=callback)
            if not completed.wait(15):
                raise RuntimeError("Language switching did not finish")
            return values[0]

        original_ui_note = window.evaluate_js("document.querySelector('#lapNote')?.value || ''")
        window.evaluate_js("if(document.querySelector('#lapNote')) document.querySelector('#lapNote').value = 'My Lap メモ stays unchanged';")
        baseline = window.evaluate_js("({session:document.querySelector('#sessionSelect')?.value,lap:document.querySelector('#lapSelect')?.value,note:document.querySelector('#lapNote')?.value})")
        switches = []
        for language in ("ja", "en", "ja"):
            # Exercise the same change handler as a user operating the dropdown.
            value = evaluate_promise("""(() => new Promise((resolve,reject) => {
                const target = """ + json.dumps(language) + """, select=document.querySelector('#languageSelect');
                select.value=target; select.dispatchEvent(new Event('change',{bubbles:true}));
                const deadline=Date.now()+10000;
                function check(){
                    if(!select.disabled && I18n.language===target) return resolve({language:I18n.language,
                        heading:document.querySelector('h1').textContent,session:document.querySelector('#sessionSelect')?.value,
                        lap:document.querySelector('#lapSelect')?.value,note:document.querySelector('#lapNote')?.value,
                        selector:select.value,placeholder:document.querySelector('#lapNote')?.placeholder});
                    if(Date.now()>deadline) return reject(new Error('Dropdown did not switch language'));
                    setTimeout(check,20);
                } check();
            }))()""")
            if value["heading"] != ("ラップ分析" if language == "ja" else "Lap analysis"):
                raise RuntimeError(f"Language heading incorrect: {value}")
            if value["session"] != baseline["session"] or value["lap"] != baseline["lap"]:
                raise RuntimeError("Language switch reset the current lap selection")
            if value["note"] != baseline["note"]:
                raise RuntimeError("Language switch changed an unsaved user note")
            if read_api("/api/desktop/preferences")["language"] != language:
                raise RuntimeError("Language preference was not saved")
            switches.append(value)
        report["language_switches"] = switches
        report["unchanged_lap_controls_mutations"] = evaluate_promise("""new Promise(resolve => {
            let changes=0; const observer=new MutationObserver(records=>changes+=records.length);
            for(const id of ['sessionSelect','lapSelect','compareLapSelect'])
                observer.observe(document.getElementById(id),{childList:true,subtree:true});
            setTimeout(()=>{observer.disconnect();resolve(changes);},6500);
        })""")
        if report["unchanged_lap_controls_mutations"]:
            raise RuntimeError("Unchanged lap controls were rebuilt during polling")
        window.evaluate_js("if(document.querySelector('#lapNote')) document.querySelector('#lapNote').value = " + json.dumps(original_ui_note) + ";")
        if demo:
            if len(laps) != 37 or dom["sessions"] != 3 or dom["painted"] < 2:
                raise RuntimeError("Test laps or charts did not render")
            from urllib.parse import quote
            lap = next(value for value in laps if value["trackId"] == 3 and value["validLap"])
            analysis = read_api("/api/laps/" + quote(lap["id"], safe="/") + "/analysis")
            report["analysis_keys"] = sorted(analysis)
            encoded_id = quote(lap["id"], safe="/")
            report["setup_available"] = read_api("/api/laps/" + encoded_id +
                "/setup-comparison?reference_id=" + quote(lap["id"], safe=""))["available"]
            # Exercise the frozen rules fingerprint and persisted background result.
            session_route = "/api/sessions/" + quote(lap["session"], safe="") + "/analysis"
            read_api(session_route, {"track_id": 3, "selected_lap_id": lap["id"]}, "POST")
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                status = read_api(session_route + "/status?track_id=3")
                if status["state"] in ("completed", "failed"):
                    break
                time.sleep(0.25)
            if status["state"] != "completed":
                raise RuntimeError(f"Packaged session analysis failed: {status}")
            result = read_api(session_route + "/result?track_id=3")
            if result["stale"]:
                raise RuntimeError("Newly saved session analysis was incorrectly marked stale")
            report["session_analysis"] = {"state": status["state"], "stale": result["stale"]}
            strategies = []
            strategy_lap = next(value for value in laps if value["trackId"] == 15 and value["validLap"])
            for kind in ("qualifying", "race"):
                route = "/api/sessions/" + quote(strategy_lap["session"], safe="") + "/analysis/" + kind
                job = read_api(route, {"track_id": 15, "selected_lap_id": strategy_lap["id"], "horizon": 3}, "POST")
                query = "?track_id=15&analysis_id=" + job["analysis_id"]
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    state = read_api(route + "/status" + query)
                    if state["state"] in ("completed", "failed"):
                        break
                    time.sleep(.25)
                if state["state"] != "completed":
                    raise RuntimeError(f"Packaged {kind} analysis failed: {state}")
                saved = read_api(route + "/result" + query)
                if saved.get("stale"):
                    raise RuntimeError(f"Packaged {kind} result is stale")
                strategies.append({"kind": kind, "track_id": 15, "state": state["state"], "stale": saved.get("stale")})
            report["strategies"] = strategies
            note_route = "/api/laps/" + encoded_id + "/note"
            original_note = read_api("/api/laps/" + encoded_id).get("note", "")
            report["existing_test_note"] = original_note
            read_api(note_route, {"note": "Packaged app save test"}, "PUT")
            if read_api("/api/laps/" + encoded_id).get("note") != "Packaged app save test":
                raise RuntimeError("Test-copy note was not saved")
            read_api(note_route, {"note": original_note}, "PUT")
            report["note_save"] = True
        page_checks = []
        routes = [("/analysis", "ラップ分析"), ("/session-analysis", "セッション分析"),
                  ("/analysis/qualifying", "予選戦略"), ("/operation-library?view=lap", "操作ライブラリ"),
                  ("/ers-strategy", "ERS戦略"), ("/analysis/race", "レース戦略"),
                  ("/map-corners", "マップ・コーナー")]
        if demo:
            routes.append(("/session-analysis-result?session=" + quote(lap["session"], safe="") + "&track_id=3", "コーナー分析結果"))
        for route, heading in routes:
            window.events.loaded.clear()
            # WebView2 ignores assigning the same Source URI. A unique query
            # forces a document navigation even for the already-open overview.
            separator = "&" if "?" in route else "?"
            window.load_url(server_url + route + separator + "desktop_check=" + str(time.monotonic_ns()))
            if not window.events.loaded.wait(15):
                raise RuntimeError(f"Page did not load: {route}")
            page = window.evaluate_js("""(() => ({heading:document.querySelector('h1')?.textContent,
                language:document.documentElement.lang,selector:document.querySelector('#languageSelect')?.value,
                viewport:window.innerWidth,width:document.documentElement.scrollWidth,
                placeholder:document.querySelector('#lapNote')?.placeholder}))()""")
            if heading not in (page.get("heading") or "") or page["language"] != "ja" or page["selector"] != "ja":
                raise RuntimeError(f"Japanese page did not render correctly: {route}: {page}")
            page_checks.append({"route": route, **page})
        report["pages"] = page_checks
        manual_checks = []
        for language, heading in (("en", "F1 Telemetry · User manual"), ("ja", "F1 Telemetry・ユーザーマニュアル")):
            window.events.loaded.clear()
            window.load_url(server_url + "/manual?lang=" + language)
            if not window.events.loaded.wait(15):
                raise RuntimeError("User manual did not load")
            manual = window.evaluate_js("({heading:document.querySelector('h1')?.textContent,sections:document.querySelectorAll('section').length,language:document.documentElement.lang,links:[...document.querySelectorAll('header a')].map(a=>a.getAttribute('href'))})")
            if manual["heading"] != heading or manual["language"] != language or manual["sections"] != 8:
                raise RuntimeError(f"User manual is incomplete: {manual}")
            if "/manual?lang=en" not in manual["links"] or "/manual?lang=ja" not in manual["links"]:
                raise RuntimeError("Manual language links are broken")
            manual_checks.append(manual)
        report["manuals"] = manual_checks
        report["ok"] = True
    except Exception as error:
        logging.exception("Window smoke test failed")
        report["error"] = str(error)
    finally:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        window.destroy()


def run(args):
    home = data_home(args.data_dir)
    home.mkdir(parents=True, exist_ok=True)
    configure_logging(home)
    lock = InstanceLock(home / ("test.lock" if args.demo else "recording.lock"))
    udp_socket = None
    server = None
    receiver = None
    server_thread = None
    stop_event = threading.Event()
    try:
        sessions = seed_test_laps(home) if args.demo else home / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        # Desktop data has an explicit home and never falls back to the source checkout.
        os.environ["F1_SESSIONS_DIR"] = str(sessions)
        from app import app, recorder, latest
        from telemetry import udp_loop, PORT
        from werkzeug.serving import make_server
        import webview
        from desktop_preferences import DesktopPreferences
        from flask import request, jsonify

        preferences = DesktopPreferences(home)
        def window_title():
            if preferences.language == "ja":
                return "F1 Telemetry — " + ("過去ラップのテスト（記録停止）" if args.demo else "自分の走行記録")
            return f"F1 Telemetry — {mode}"

        if not args.demo:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                udp_socket.bind(("0.0.0.0", PORT))
            except OSError as error:
                raise RuntimeError(f"UDP {PORT} is already in use. Close the browser version or other telemetry receiver, then reopen this app.") from error
        mode = "Test laps — recording off" if args.demo else "My recordings"
        app.config["DESKTOP_MODE"] = "test" if args.demo else "recording"
        app.config["DESKTOP_DATA_DIR"] = str(sessions)

        @app.context_processor
        def desktop_context():
            return {"desktop_mode": app.config["DESKTOP_MODE"], "desktop_language": preferences.language}

        @app.route("/api/desktop/preferences", methods=["GET", "PUT"])
        def desktop_preferences():
            if request.method == "GET":
                return {"language": preferences.language}
            body = request.get_json(silent=True)
            if not isinstance(body, dict) or body.get("language") not in ("en", "ja"):
                return jsonify(error="Language must be en or ja"), 400
            value = preferences.save_language(body["language"])
            window.set_title(window_title())
            return value

        @app.get("/api/desktop")
        def desktop_status():
            return {"mode": app.config["DESKTOP_MODE"], "recording_enabled": not args.demo,
                    "sessions_dir": str(sessions), "udp_port": None if args.demo else PORT}

        # Allocate a free loopback port; browser version and test mode can coexist.
        server = make_server("127.0.0.1", 0, app, threaded=True)
        url = f"http://127.0.0.1:{server.server_port}"
        from desktop_security import protect_desktop_server
        protect_desktop_server(app, url)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True, name="desktop-http")
        server_thread.start()
        if udp_socket is not None:
            receiver = threading.Thread(target=udp_loop, args=(latest, recorder, udp_socket, stop_event),
                                        daemon=True, name="telemetry-receiver")
            receiver.start()

        def launch_mode(demo):
            command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(PROJECT / "desktop.py")]
            command.extend(["--data-dir", str(home)])
            if demo:
                command.append("--demo")
            subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)

        class DesktopActions:
            # Only these fixed actions are exposed to our local app pages.
            def open_other_mode(self):
                launch_mode(not args.demo)

            def open_recordings_folder(self):
                os.startfile(str(sessions))

            def open_logs_folder(self):
                os.startfile(str(home / "logs"))

            def close_window(self):
                window.destroy()

        screen = webview.screens[0]
        width = max(320, min(1280, screen.width - 80))
        height = max(320, min(850, screen.height - 100))
        window = webview.create_window(window_title(), url + "/analysis",
            width=width, height=height, min_size=(min(760, width), min(540, height)),
            background_color="#11161a", text_select=True, js_api=DesktopActions())
        logging.info("Starting %s at %s; recordings: %s", mode, url, sessions)
        kwargs = {}
        if args.smoke_report:
            kwargs = {"func": smoke_window, "args": (window, url, args.smoke_report.resolve(), args.demo)}
        webview.start(gui="edgechromium", icon=str(resource_root() / "frontend/static/icons/app.ico"),
                      private_mode=False, storage_path=str(home / ("webview-test" if args.demo else "webview")),
                      **kwargs)
        if args.smoke_report:
            return 0 if json.loads(args.smoke_report.read_text(encoding="utf-8")).get("ok") else 1
        return 0
    finally:
        stop_event.set()
        if receiver is not None:
            receiver.join(timeout=2)
        if udp_socket is not None:
            udp_socket.close()
        if server is not None:
            server.shutdown()
            server.server_close()
        if server_thread is not None:
            server_thread.join(timeout=2)
        if "recorder" in locals() and not recorder.flush(timeout=10):
            logging.error("Completed-lap writes failed or did not finish before shutdown")
            if not args.smoke_report:
                from desktop_preferences import DesktopPreferences
                if DesktopPreferences(home).language == "ja":
                    show_error("完了ラップの保存に失敗したか、保存が時間内に終わりませんでした。\n空き容量と保存先のアクセス権を確認してください。\n詳細はログフォルダーのdesktop.logにあります。")
                else:
                    show_error("Some completed laps could not be saved or did not finish saving.\nCheck free disk space and folder permissions.\nDetails are in desktop.log in the logs folder.")
        lock.close()
        logging.info("Desktop closed; receiver and HTTP server stopped")


def main():
    parser = argparse.ArgumentParser(description="F1 Telemetry desktop app")
    parser.add_argument("--demo", action="store_true", help="Open real previous laps with recording disabled")
    parser.add_argument("--data-dir", type=Path, help="Override the user data folder")
    parser.add_argument("--smoke-report", type=Path, help="Validate the embedded window and close it automatically")
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as error:
        logging.exception("Desktop startup failed")
        if args.smoke_report:
            args.smoke_report.parent.mkdir(parents=True, exist_ok=True)
            args.smoke_report.write_text(json.dumps({"ok": False, "error": str(error)}, indent=2), encoding="utf-8")
        else:
            from desktop_preferences import DesktopPreferences
            if DesktopPreferences(data_home(args.data_dir)).language == "ja":
                message = str(error)
                if "UDP 20777 is already in use" in message:
                    message = "UDPポート20777が使用中です。ブラウザー版または別のテレメトリー受信アプリを終了してから、開き直してください。"
                elif "This mode is already open" in message:
                    message = "このモードはすでに起動しています。既存のF1 Telemetryウィンドウを使用してください。"
                show_error(f"起動できませんでした。\n{message}\n\n画面を表示できない場合はMicrosoft Edge WebView2 Runtimeを確認してください。\n詳細は %LOCALAPPDATA%\\F1Telemetry のlogsフォルダーにあります。")
            else:
                show_error(f"{error}\n\nIf the window cannot start, install Microsoft Edge WebView2 Runtime.\nDetails are in the logs folder under %LOCALAPPDATA%\\F1Telemetry.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
