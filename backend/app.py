import threading
from datetime import datetime, timezone
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory
from state import latest
from telemetry import udp_loop, edition_status
from lap_analyzer import analyze_lap
from lap_recorder import LapRecorder
from storage import LapStorage
from analysis_worker import AnalysisWorker
from track_sections import analyze_track_sections, identify_chicanes
from track_names import track_name
from operation_sections import analyze_operation_sections, build_operation_library
from ers_strategy import analyze_ers_strategy
from strategy_model import build_strategy_model
from strategy_scenarios import compare_strategy_scenarios, optimize_multi_lap_strategy
from strategy_worker import StrategyWorker
from analysis_routes import create_analysis_blueprint
from workspace_insights import consistency, stints, setup_changes, wear_estimate
from recording_health import recording_health
from analysis_freshness import freshness
from runtime_paths import resource_root

app = Flask(
    __name__,
    template_folder=str(resource_root() / "frontend" / "templates"),
    static_folder=str(resource_root() / "frontend" / "static")
)
storage = LapStorage()
recorder = LapRecorder(storage)
analysis_worker = AnalysisWorker(storage)
strategy_worker = StrategyWorker(storage)
app.register_blueprint(create_analysis_blueprint(storage, strategy_worker, latest))

@app.route("/")
def index():
    # The legacy real-time overlay is intentionally disabled.  Keep old
    # bookmarks useful by sending them to the only supported UI.
    return redirect("/analysis")

@app.route("/health")
def health():
    return jsonify(status="ok")

@app.get("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "icons/app.ico", mimetype="image/x-icon")

@app.get("/api/recording-health")
def recording_health_status():
    return jsonify(recording_health.snapshot(latest.get("game_version") == "F1 26") |
                   {"saving": recorder.persistence_status(), "edition": edition_status(latest)})

@app.get("/api/laps/<path:lap_id>/workspace-insights")
def lap_workspace_insights(lap_id):
    value = storage.load_lap(lap_id)
    if not value:
        return jsonify(error="Lap not found"), 404
    session_id = lap_id.split("/", 1)[0]
    entries = storage.session_track_laps(session_id, value.get("trackId"))
    profile = storage.load_track_profile(value.get("trackId"))
    if profile and not _profile_compatible(profile, _lap_track_length(value)):
        profile = None
    return jsonify(consistency=consistency(entries, value, profile), stints=stints(entries),
                   tyre_wear_estimate=wear_estimate(entries, value))

@app.get("/api/laps/<path:lap_id>/setup-comparison")
def lap_setup_comparison(lap_id):
    value = storage.load_lap(lap_id)
    other_id = request.args.get("reference_id", "")
    other = storage.load_lap(other_id) if other_id else None
    if not value or not other:
        return jsonify(error="Both selected and comparison laps are required"), 404
    if value.get("trackId") != other.get("trackId"):
        return jsonify(error="Setups must be compared on the same track"), 400
    return jsonify(setup_changes(storage.load_lap_setup(lap_id), storage.load_lap_setup(other_id)))

@app.route("/analysis")
def analysis_page():
    return render_template("analysis.html")

@app.get("/manual")
def user_manual():
    language = request.args.get("lang", "en")
    if language not in ("en", "ja"):
        language = "en"
    return send_from_directory(app.static_folder, f"manual-{language}.html")

@app.route("/session-analysis")
def session_analysis_page():
    return render_template("session_analysis.html")

@app.route("/map-corners")
def map_corners_page():
    return render_template("section_experiment.html")

@app.route("/operation-map")
def operation_map_page():
    return redirect("/operation-library?view=lap")

@app.route("/operation-library")
def operation_library_page():
    return render_template("operation_library.html")

@app.route("/ers-strategy")
def ers_strategy_page():
    return render_template("ers_strategy.html")

@app.route("/session-analysis-result")
def session_analysis_result_page():
    return render_template("session_analysis_result.html")

@app.route("/api/laps")
def laps():
    return jsonify(storage.list_laps())

@app.route("/api/sessions")
def sessions():
    return jsonify(storage.hierarchy())

def _profile_compatible(profile, track_length):
    saved_length = profile.get("track_length_m") if profile else None
    try:
        return abs(float(saved_length) - float(track_length)) <= max(100.0, float(track_length) * .03)
    except (TypeError, ValueError):
        return False

def _lap_track_length(lap):
    values = []
    for sample in lap.get("samples", []):
        try: values.append(float(sample.get("lap_distance")))
        except (TypeError, ValueError): pass
    return max(values, default=0)

@app.get("/api/tracks/<track_id>/corner-profile")
def track_corner_profile(track_id):
    profile = storage.load_track_profile(track_id)
    return (jsonify(profile), 200) if profile else (jsonify(error="Corner profile not found"), 404)

@app.get("/api/track-corner-profiles")
def track_corner_profiles():
    values = storage.list_track_profiles()
    for value in values:
        try: value["track_name"] = track_name(int(value.get("track_id")))
        except (TypeError, ValueError): value["track_name"] = f"Track {value.get('track_id')}"
    return jsonify(values)

@app.put("/api/tracks/<track_id>/corner-profile")
def save_track_corner_profile(track_id):
    body = request.get_json(silent=True) or {}
    supplied_corners = body.get("corners")
    if not isinstance(supplied_corners, list) or not supplied_corners or len(supplied_corners) > 40:
        return jsonify(error="corners must contain between 1 and 40 turns"), 400
    corners = []
    try:
        for index, source in enumerate(supplied_corners):
            start = float(source["start_distance"]); apex = float(source["apex_distance"]); end = float(source["end_distance"])
            if not 0 <= start <= apex <= end or end - start < 5:
                raise ValueError("invalid turn distance")
            corner = {
                "label": f"T{index + 1}", "start_distance": round(start, 1),
                "apex_distance": round(apex, 1), "end_distance": round(end, 1),
                "direction": "right" if source.get("direction") == "right" else "left",
                "peak_curvature": source.get("peak_curvature"), "radius_m": source.get("radius_m"),
            }
            corners.append(corner)
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Each corner requires valid start, apex, and end distances"), 400
    if any(corners[index]["start_distance"] < corners[index - 1]["end_distance"] for index in range(1, len(corners))):
        return jsonify(error="Corner distances must be ordered and non-overlapping"), 400
    try: track_length = float(body.get("track_length_m"))
    except (TypeError, ValueError): return jsonify(error="track_length_m is required"), 400
    settings = body.get("settings") or {}
    try:
        sanitized_settings = {
            "threshold": float(settings.get("threshold", .0066)),
            "smoothing_m": float(settings.get("smoothing_m", 20)),
            "min_length_m": float(settings.get("min_length_m", 15)),
            "step_m": float(settings.get("step_m", 5)),
        }
    except (TypeError, ValueError):
        return jsonify(error="Invalid corner detection settings"), 400
    chicanes = identify_chicanes(corners)
    course_rotation = body.get("course_rotation")
    if course_rotation not in ("clockwise", "counterclockwise"):
        source_lap = storage.load_lap(body.get("source_lap_id")) if body.get("source_lap_id") else None
        if source_lap:
            course_rotation = analyze_track_sections(source_lap, **sanitized_settings).get("course_rotation")
    if course_rotation not in ("clockwise", "counterclockwise"):
        course_rotation = "unknown"
    profile = {
        "schema_version": 1, "direction_convention": 2,
        "track_id": track_id, "track_length_m": round(track_length, 1),
        "course_rotation": course_rotation,
        "corner_direction_basis": "vehicle_travel_direction",
        "settings": sanitized_settings, "corners": corners, "chicanes": chicanes,
        "source_session": body.get("source_session"), "source_lap_id": body.get("source_lap_id"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    storage.save_track_profile(track_id, profile)
    return jsonify(profile)

@app.get("/api/sessions/<session_id>/track-sections")
def track_sections(session_id):
    track_id = request.args.get("track_id")
    if storage._safe_session_dir(session_id) is None:
        return jsonify(error="Session not found"), 404
    if track_id is None:
        return jsonify(error="track_id is required"), 400
    laps = storage.session_track_laps(session_id, track_id)
    valid = [(lap_id, lap) for lap_id, lap in laps if lap.get("validLap") and lap.get("samples")]
    if not valid:
        return jsonify(error="No valid lap with telemetry was found"), 404
    reference_id, reference = min(valid, key=lambda item: item[1].get("lapTimeMs", float("inf")))
    def bounded(name, default, minimum, maximum):
        try: value = float(request.args.get(name, default))
        except (TypeError, ValueError): value = default
        return max(minimum, min(maximum, value))
    result = analyze_track_sections(
        reference,
        threshold=bounded("threshold", .0066, .0002, .05),
        smoothing_m=bounded("smoothing_m", 20, 0, 100),
        min_length_m=bounded("min_length_m", 15, 5, 200),
    )
    result["source_lap_id"] = reference_id
    profile = storage.load_track_profile(track_id)
    if request.args.get("profile") == "1" and profile and _profile_compatible(profile, result.get("track_length_m")):
        result["corners"] = profile["corners"]
        result["chicanes"] = profile.get("chicanes", [])
        result["settings"] = profile.get("settings", result["settings"])
        result["profile"] = {"applied": True, "updated_at": profile.get("updated_at"),
                             "source_session": profile.get("source_session")}
    else:
        result["profile"] = {"applied": False, "available": bool(profile),
                             "reason": "track_length_mismatch" if profile else None}
    return jsonify(result)

def _analysis_target(session_id, body=None):
    body = body or {}
    track_id = body.get("track_id", request.args.get("track_id"))
    selected_lap_id = body.get("selected_lap_id", request.args.get("selected_lap_id"))
    if storage._safe_session_dir(session_id) is None:
        return None, None, (jsonify(error="Session not found"), 404)
    if track_id is None and selected_lap_id:
        selected = storage.load_lap(selected_lap_id)
        track_id = selected.get("trackId") if selected else None
    if track_id is None:
        return None, None, (jsonify(error="track_id is required"), 400)
    if selected_lap_id and not any(lap_id == selected_lap_id for lap_id, _ in storage.session_track_laps(session_id, track_id)):
        return None, None, (jsonify(error="Selected lap must belong to the requested session and track"), 400)
    return track_id, selected_lap_id, None

@app.post("/api/sessions/<session_id>/analysis")
def start_session_analysis(session_id):
    body = request.get_json(silent=True) or {}
    track_id, selected_lap_id, error = _analysis_target(session_id, body)
    if error: return error
    supplied = body.get("section_settings") or {}
    def setting(name, default, minimum, maximum):
        try: value = float(supplied.get(name, default))
        except (TypeError, ValueError): value = default
        return max(minimum, min(maximum, value))
    section_settings = {
        "threshold": setting("threshold", .0066, .0002, .05),
        "smoothing_m": setting("smoothing_m", 20, 0, 100),
        "min_length_m": setting("min_length_m", 15, 5, 200),
    }
    laps = storage.session_track_laps(session_id, track_id)
    current_length = max((_lap_track_length(lap) for _, lap in laps), default=0)
    profile = storage.load_track_profile(track_id)
    turn_definition = None
    if profile and _profile_compatible(profile, current_length):
        section_settings.update(profile.get("settings") or {})
        turn_definition = {"analyzable": True, "reason": None, "settings": profile.get("settings", {}),
                           "corners": profile.get("corners", []), "chicanes": profile.get("chicanes", []),
                           "profile": {"track_id": track_id, "updated_at": profile.get("updated_at")}}
    status, started = analysis_worker.start(
        session_id, track_id, selected_lap_id, bool(body.get("force")), section_settings, turn_definition)
    return jsonify(status | {"started": started}), (202 if started else 200)

@app.get("/api/sessions/<session_id>/analysis/status")
def session_analysis_status(session_id):
    track_id, _, error = _analysis_target(session_id)
    if error: return error
    return jsonify(analysis_worker.status(session_id, track_id))

@app.get("/api/sessions/<session_id>/analysis/result")
def session_analysis_result(session_id):
    track_id, _, error = _analysis_target(session_id)
    if error: return error
    result = storage.load_session_analysis(session_id, track_id)
    if result is None:
        status = analysis_worker.status(session_id, track_id)
        return jsonify(error="Analysis result is not available", state=status.get("state")), 404
    return jsonify(result | freshness(storage, result, track_id, session_id))

@app.route("/api/laps/<path:lap_id>")
def lap(lap_id):
    value = storage.load_lap(lap_id)
    return (jsonify(value), 200) if value else (jsonify(error="Lap not found"), 404)

@app.put("/api/laps/<path:lap_id>/note")
def lap_note(lap_id):
    body = request.get_json(silent=True) or {}
    note = body.get("note")
    if not isinstance(note, str): return jsonify(error="note must be a string"), 400
    if len(note) > 5000: return jsonify(error="note must be 5000 characters or fewer"), 400
    value = storage.update_lap_note(lap_id, note)
    return (jsonify({"note": value.get("note"), "noteUpdatedAt": value.get("noteUpdatedAt")}), 200) if value else (jsonify(error="Lap not found"), 404)

@app.route("/api/laps/<path:lap_id>/analysis")
def lap_analysis(lap_id):
    value = storage.load_lap(lap_id)
    if not value: return jsonify(error="Lap not found"), 404
    reference_id = request.args.get("reference_id")
    reference = storage.load_lap(reference_id) if reference_id else storage.session_reference(lap_id)
    if reference_id and not reference:
        return jsonify(error="Comparison lap not found"), 404
    if reference_id and (reference.get("sessionUid") != value.get("sessionUid")
                         or reference.get("trackId") != value.get("trackId")):
        return jsonify(error="Comparison lap must be from the same session and track"), 400
    previous = storage.previous_lap(lap_id)
    result = analyze_lap(value, reference)
    result["previous_comparison"] = analyze_lap(value, previous)["comparison"] if previous else []
    result["summary"] = {
        "is_session_best": bool(value.get("validLap") and reference and value.get("createdAt") == reference.get("createdAt")),
        "vs_previous_ms": (value.get("lapTimeMs", 0) - previous.get("lapTimeMs", 0)) if previous else None,
        "previous_lap_number": previous.get("lapNumber") if previous else None,
    }
    return jsonify(result)

@app.get("/api/laps/<path:lap_id>/operation-sections")
def lap_operation_sections(lap_id):
    value = storage.load_lap(lap_id)
    if not value:
        return jsonify(error="Lap not found"), 404
    def bounded(name, default, minimum, maximum):
        try: supplied = float(request.args.get(name, default))
        except (TypeError, ValueError): supplied = default
        return max(minimum, min(maximum, supplied))
    result = analyze_operation_sections(
        value,
        smoothing_m=bounded("smoothing_m", 15, 0, 80),
        min_section_m=bounded("min_section_m", 20, 5, 150),
        braking_threshold=bounded("braking_threshold", .05, .01, .5),
        flat_threshold=bounded("flat_threshold", .95, .6, 1.0),
        lift_threshold=bounded("lift_threshold", .20, 0, .6),
    )
    return jsonify(result)

@app.get("/api/operation-library")
def operation_library_index():
    grouped = {}
    for lap in storage.list_laps():
        lap_time = lap.get("lapTimeMs")
        if (not lap.get("validLap") or lap.get("pitLaneUsed") or not lap_time
                or (lap.get("sampleCount") or 0) < 20):
            continue
        key = str(lap.get("trackId"))
        group = grouped.setdefault(key, {"track_id": lap.get("trackId"),
                                         "track_name": lap.get("trackName"), "laps": []})
        group["laps"].append(lap)
    result = []
    for group in grouped.values():
        ordered = sorted(group.pop("laps"), key=lambda lap: lap.get("lapTimeMs", float("inf")))
        best = ordered[0]["lapTimeMs"]
        fast = [lap for lap in ordered if lap["lapTimeMs"] <= best * 1.03]
        result.append(group | {"eligible_lap_count": len(ordered),
                               "fast_lap_count": len(fast), "best_lap_time_ms": best,
                               "library_ready": len(fast) >= 2})
    result.sort(key=lambda value: value["track_name"] or str(value["track_id"]))
    return jsonify(result)

@app.get("/api/tracks/<track_id>/operation-library")
def track_operation_library(track_id):
    def bounded(name, default, minimum, maximum):
        try: supplied = float(request.args.get(name, default))
        except (TypeError, ValueError): supplied = default
        return max(minimum, min(maximum, supplied))
    entries = []
    for metadata in storage.list_laps():
        if str(metadata.get("trackId")) != str(track_id):
            continue
        lap = storage.load_lap(metadata["id"])
        if lap:
            entries.append((metadata["id"], lap))
    result = build_operation_library(
        entries,
        pace_window_percent=bounded("pace_window_percent", 3, .5, 10),
        max_laps=round(bounded("max_laps", 8, 2, 20)),
        smoothing_m=bounded("smoothing_m", 15, 0, 80),
        min_section_m=bounded("min_section_m", 20, 5, 150),
    )
    result["track_name"] = track_name(int(track_id)) if str(track_id).lstrip("-").isdigit() else f"Track {track_id}"
    return jsonify(result)

@app.get("/api/ers-strategy")
def ers_strategy_index():
    grouped = {}
    for metadata in storage.list_laps():
        if not (metadata.get("packetFormat") == 2026 or metadata.get("gameYear") == 26
                or metadata.get("gameVersion") == "F1 26"):
            continue
        if (not metadata.get("validLap") or metadata.get("pitLaneUsed")
                or not metadata.get("lapTimeMs") or (metadata.get("sampleCount") or 0) < 50):
            continue
        key = str(metadata.get("trackId"))
        group = grouped.setdefault(key, {"track_id": metadata.get("trackId"),
                                         "track_name": metadata.get("trackName"), "laps": []})
        group["laps"].append(metadata)
    result = []
    for group in grouped.values():
        ordered = sorted(group.pop("laps"), key=lambda lap: lap["lapTimeMs"])
        best = ordered[0]["lapTimeMs"]
        fast = [lap for lap in ordered if lap["lapTimeMs"] <= best * 1.05]
        result.append(group | {"eligible_lap_count": len(ordered), "fast_lap_count": len(fast),
                               "best_lap_time_ms": best, "strategy_ready": len(fast) >= 2})
    result.sort(key=lambda value: value["track_name"] or str(value["track_id"]))
    return jsonify(result)

@app.get("/api/tracks/<track_id>/ers-strategy")
def track_ers_strategy(track_id):
    def bounded(name, default, minimum, maximum):
        try: supplied = float(request.args.get(name, default))
        except (TypeError, ValueError): supplied = default
        return max(minimum, min(maximum, supplied))
    entries = []
    for metadata in storage.list_laps():
        if str(metadata.get("trackId")) != str(track_id):
            continue
        lap = storage.load_lap(metadata["id"])
        if lap:
            entries.append((metadata["id"], lap))
    result = analyze_ers_strategy(
        entries,
        pace_window_percent=bounded("pace_window_percent", 5, 1, 12),
        max_laps=round(bounded("max_laps", 16, 2, 30)),
        window_m=bounded("window_m", 200, 100, 500),
        stride_m=bounded("stride_m", 50, 25, 200),
    )
    if result.get("analyzable"):
        model = build_strategy_model(
            entries,
            pace_window_percent=bounded("pace_window_percent", 5, 1, 12),
            max_laps=round(bounded("max_laps", 16, 2, 30)),
        )
        supplied_start_soc = (None if request.args.get("start_soc") in (None, "")
                              else bounded("start_soc", model.get("initial_soc", 100), 0, 100))
        result["scenario_comparisons"] = {
            mode: compare_strategy_scenarios(model, start_soc=supplied_start_soc,
                                             deployment_mode=mode)
            for mode in ("boost", "overtake")
        }
        result["scenario_comparison"] = result["scenario_comparisons"]["boost"]
        remaining_laps = request.args.get("remaining_laps")
        strategy_settings = {
            "horizon": round(bounded("horizon", 5, 3, 5)),
            "remaining_laps": (None if remaining_laps in (None, "")
                               else round(bounded("remaining_laps", 5, 1, 100))),
            "start_soc": supplied_start_soc,
            "minimum_finish_soc": bounded("minimum_finish_soc", 5, 0, 50),
        }
        result["multi_lap_strategies"] = {
            mode: optimize_multi_lap_strategy(model, deployment_mode=mode, **strategy_settings)
            for mode in ("boost", "overtake")
        }
        result["multi_lap_strategy"] = result["multi_lap_strategies"]["boost"]
    result["track_name"] = track_name(int(track_id)) if str(track_id).lstrip("-").isdigit() else f"Track {track_id}"
    return jsonify(result)

if __name__ == "__main__":
    threading.Thread(target=udp_loop, args=(latest, recorder), daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
