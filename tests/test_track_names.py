import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from track_names import track_name, track_slug


def test_f1_25_track_ids_are_not_shifted():
    assert track_name(11) == "Monza"
    assert track_name(12) == "Singapore"
    assert track_name(13) == "Suzuka"
    assert track_name(14) == "Abu Dhabi"
    assert track_slug(13) == "suzuka"


def test_unknown_track_is_not_mislabeled():
    assert track_name(1) == "Unknown Track 1"
