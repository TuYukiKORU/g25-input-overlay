"""Routes for manually-triggered qualifying and race strategy analysis."""
from flask import Blueprint, jsonify, render_template, request
from analysis_freshness import freshness


def create_analysis_blueprint(storage, worker, latest):
    blueprint = Blueprint("strategy_analysis", __name__)

    @blueprint.get("/analysis/qualifying")
    def qualifying_page():
        return render_template("qualifying_analysis.html")

    @blueprint.get("/analysis/race")
    def race_page():
        return render_template("race_analysis.html")

    def target(session_id, kind):
        body = request.get_json(silent=True) or {}
        track_id = body.get("track_id")
        if storage._safe_session_dir(session_id) is None:
            return None, None, (jsonify(error="Session not found"), 404)
        if track_id is None:
            return None, None, (jsonify(error="track_id is required"), 400)
        if not storage.session_track_laps(session_id, track_id):
            return None, None, (jsonify(error="Session and track have no saved laps"), 404)
        settings = {"selected_lap_id": body.get("selected_lap_id")}
        try:
            settings["pace_window_percent"] = max(2.0, min(15.0, float(body.get("pace_window_percent", 8))))
            settings["max_laps"] = max(2, min(80, int(body.get("max_laps", 40))))
            if kind == "qualifying":
                settings["start_soc"] = (None if body.get("start_soc") in (None, "") else
                                         max(0.0, min(100.0, float(body["start_soc"]))))
                settings["minimum_start_line_soc"] = max(
                    50.0, min(100.0, float(body.get("minimum_start_line_soc", 80))))
                settings["minimum_finish_soc"] = max(0.0, min(50.0, float(body.get("minimum_finish_soc", 5))))
            else:
                settings["horizon"] = max(3, min(5, int(body.get("horizon", 5))))
                settings["current_soc"] = (None if body.get("current_soc") in (None, "") else
                                           max(0.0, min(100.0, float(body["current_soc"]))))
                settings["minimum_soc"] = max(0.0, min(50.0, float(body.get("minimum_soc", 5))))
                settings["remaining_laps"] = (None if body.get("remaining_laps") in (None, "") else
                                              max(1, int(body["remaining_laps"])))
        except (TypeError, ValueError):
            return None, None, (jsonify(error="Invalid analysis settings"), 400)
        return track_id, settings, None

    @blueprint.post("/api/sessions/<session_id>/analysis/<kind>")
    def start_strategy(session_id, kind):
        if kind not in ("qualifying", "race"):
            return jsonify(error="Unknown strategy kind"), 404
        track_id, settings, error = target(session_id, kind)
        if error:
            return error
        body = request.get_json(silent=True) or {}
        status, started = worker.start(kind, session_id, track_id, settings, bool(body.get("force")))
        return jsonify(status | {"started": started}), (202 if started else 200)

    @blueprint.get("/api/sessions/<session_id>/analysis/<kind>/status")
    def strategy_status(session_id, kind):
        track_id, analysis_id = request.args.get("track_id"), request.args.get("analysis_id")
        if kind not in ("qualifying", "race") or not track_id or not analysis_id:
            return jsonify(error="kind, track_id and analysis_id are required"), 400
        return jsonify(worker.status(session_id, track_id, kind, analysis_id))

    @blueprint.get("/api/sessions/<session_id>/analysis/<kind>/result")
    def strategy_result(session_id, kind):
        track_id, analysis_id = request.args.get("track_id"), request.args.get("analysis_id")
        if kind not in ("qualifying", "race") or not track_id or not analysis_id:
            return jsonify(error="kind, track_id and analysis_id are required"), 400
        result = storage.load_strategy_artifact(session_id, track_id, kind, analysis_id)
        return (jsonify(result | freshness(storage, result, track_id)), 200) if result else (jsonify(error="Analysis result is not available"), 404)

    @blueprint.get("/api/strategy/live-state")
    def live_strategy_state():
        keys = ("session_uid", "track_id", "lap_number", "total_laps", "ers_percent",
                "ers_store_energy_j", "fuel_in_tank_kg", "fuel_remaining_laps",
                "tyres_age_laps", "tyres_wear", "tyre_compound", "game_version",
                "raw_packet_format", "raw_game_year", "edition_detection",
                "season_pack_detection", "num_active_cars", "participant_team_ids",
                "aero_mode", "active_aero_available", "active_aero_activation_distance",
                "boost_active", "overtake_available", "overtake_active",
                "overtake_activation_distance", "regulations_2026",
                "telemetry2_received",
                "udp_configuration_warning")
        return jsonify({key: latest.get(key) for key in keys})

    return blueprint
