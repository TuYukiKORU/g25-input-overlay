import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from session_names import game_mode_name, session_type_name, session_activity_name


def test_current_f1_25_career_and_time_trial_names():
    assert game_mode_name(5) == "Time Trial"
    assert game_mode_name(27) == "My Team Career '25"
    assert game_mode_name(28) == "Driver Career '25"
    assert session_type_name(15) == "Race"
    assert session_type_name(18) == "Time Trial"


def test_unknown_identifiers_keep_their_number():
    assert game_mode_name(99) == "Unknown Game Mode 99"
    assert session_type_name(99) == "Unknown Session Type 99"


def test_session_activity_uses_the_stage_before_game_mode():
    assert session_activity_name(1, 4) == "Practice 1"
    assert session_activity_name(5, 28) == "Qualifying 1"
    assert session_activity_name(10, 4) == "Qualifying · Sprint Shootout 1"
    assert session_activity_name(15, 4) == "Race"
    assert session_activity_name(18) == "Time Attack (Time Trial)"
    assert session_activity_name(None, 5) == "Time Attack (Time Trial)"
    assert session_activity_name(1, 5) == "Practice 1"
    assert session_activity_name(None, 4) == "Unknown session"
    assert session_activity_name(99, 4) == "Unknown Session Type 99"
