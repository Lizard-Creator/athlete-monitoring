import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from acwr import add_acwr, daily_load  # noqa: E402
from tracking import FPS, PITCH_X, count_efforts, player_loads, read_metrica  # noqa: E402


def _long(speed_ms: float, seconds: int, jersey=9) -> pd.DataFrame:
    """A player running in a straight line at constant speed."""
    n = seconds * FPS
    return pd.DataFrame({"period": 1, "frame": range(n), "time_s": np.arange(n) / FPS,
                         "x": np.arange(n) * speed_ms / FPS, "y": 30.0, "jersey": jersey})


def test_constant_hsr_run():
    row = player_loads(_long(6.0, 60)).iloc[0]
    assert row["total_distance_m"] == pytest.approx(360, rel=0.01)
    assert row["hsr_distance_m"] == pytest.approx(360, rel=0.01)
    assert row["sprint_distance_m"] == 0
    assert row["minutes"] == pytest.approx(1.0)


def test_sprint_counted_once():
    row = player_loads(_long(8.0, 5)).iloc[0]
    assert row["sprint_efforts"] == 1
    assert row["max_speed_ms"] == pytest.approx(8.0, rel=0.01)


def test_count_efforts_respects_min_duration():
    mask = pd.Series([True] * 30 + [False] * 5 + [True] * 10 + [False] + [True] * 25)
    assert count_efforts(mask, 25) == 2


def test_read_metrica(tmp_path):
    csv = tmp_path / "t.csv"
    csv.write_text(",,,Home,,Home,,,\n,,,11,,1,,,\n"
                   "Period,Frame,Time [s],Player11,,Player1,,Ball,\n"
                   "1,1,0.04,0.5,0.5,0.1,0.2,0.5,0.5\n")
    long = read_metrica(csv)
    assert set(long["jersey"]) == {11, 1}
    assert long.loc[long["jersey"] == 1, "x"].iloc[0] == pytest.approx(0.1 * PITCH_X)


def test_acwr_is_one_for_constant_load():
    dates = pd.date_range("2025-01-01", periods=40).date
    sessions = pd.DataFrame({"player_id": "A", "date": dates, "srpe_au": 400.0,
                             "total_distance_m": 5000.0, "hsr_distance_m": 300.0})
    out = add_acwr(daily_load(sessions))
    assert out["acwr"].iloc[:27].isna().all()      # needs 28 days of history
    assert out["acwr"].iloc[-1] == pytest.approx(1.0)
    assert out["acwr_flag"].iloc[-1] == "Normal"


def test_rest_days_are_zero_filled_and_spike_flags_high():
    dates = list(pd.date_range("2025-01-01", periods=28).date)
    sessions = pd.DataFrame({"player_id": "A", "date": dates[::2], "srpe_au": 300.0,
                             "total_distance_m": 0.0, "hsr_distance_m": 0.0})
    spike = pd.DataFrame({"player_id": "A", "date": pd.date_range("2025-01-29", periods=7).date,
                          "srpe_au": 900.0, "total_distance_m": 0.0, "hsr_distance_m": 0.0})
    out = add_acwr(daily_load(pd.concat([sessions, spike])))
    assert len(out) == 35                           # every calendar day present
    assert out["acwr_flag"].iloc[-1] == "High"
