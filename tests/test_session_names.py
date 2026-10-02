import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from session_names import game_mode_name, session_type_name


def test_current_f1_25_career_and_time_trial_names():
    assert game_mode_name(5) == "Time Trial"
    assert game_mode_name(27) == "My Team Career '25"
    assert game_mode_name(28) == "Driver Career '25"
    assert session_type_name(15) == "Race"
    assert session_type_name(18) == "Time Trial"


def test_unknown_identifiers_keep_their_number():
    assert game_mode_name(99) == "Unknown Game Mode 99"
    assert session_type_name(99) == "Unknown Session Type 99"
