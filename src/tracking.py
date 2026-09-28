"""Turn raw Metrica tracking data (x/y per frame) into per-player physical load metrics."""
from pathlib import Path

import numpy as np
import pandas as pd

FPS = 25                       # Metrica tracking frame rate
PITCH_X, PITCH_Y = 105.0, 68.0  # metres; Metrica coords are normalised 0-1
HSR_SPEED = 5.5                # m/s (19.8 km/h) - high-speed running threshold
SPRINT_SPEED = 7.0             # m/s (25.2 km/h)
ACCEL_THRESHOLD = 3.0          # m/s^2
MAX_SPEED = 12.0               # m/s - anything faster is tracking noise
SMOOTH_FRAMES = 7              # rolling window used to de-noise speed


def read_metrica(path: Path) -> pd.DataFrame:
    """Read a Metrica RawTrackingData CSV into long format: one row per player per frame, in metres."""
    df = pd.read_csv(path, skiprows=2)
    raw_cols = list(df.columns)
    names = ["period", "frame", "time_s"]
    for i in range(3, len(raw_cols), 2):
        names += [f"{raw_cols[i]}_x", f"{raw_cols[i]}_y"]
    df.columns = names

    players = [c[:-2] for c in names if c.endswith("_x") and c != "Ball_x"]
    frames = []
    for p in players:
        part = df[["period", "frame", "time_s", f"{p}_x", f"{p}_y"]].copy()
        part.columns = ["period", "frame", "time_s", "x", "y"]
        part["jersey"] = int(p.replace("Player", ""))
        frames.append(part)
    long = pd.concat(frames, ignore_index=True)
    long["x"] *= PITCH_X
    long["y"] *= PITCH_Y
    return long


def count_efforts(mask: pd.Series, min_frames: int) -> int:
    """Count separate runs of True that last at least `min_frames` consecutive frames."""
    run_id = (mask != mask.shift()).cumsum()
    run_lengths = mask.groupby(run_id).agg(["first", "size"])
    return int(((run_lengths["first"]) & (run_lengths["size"] >= min_frames)).sum())


def player_loads(long: pd.DataFrame) -> pd.DataFrame:
    """Aggregate frame-level positions into one row of match load metrics per player."""
    long = long.sort_values(["jersey", "period", "frame"])
    by = long.groupby(["jersey", "period"])
    speed = np.hypot(by["x"].diff(), by["y"].diff()) * FPS
    speed = speed.where(speed <= MAX_SPEED)
    long["speed"] = speed.groupby([long["jersey"], long["period"]]).transform(
        lambda s: s.rolling(SMOOTH_FRAMES, center=True, min_periods=1).mean()
    )
    long["accel"] = long.groupby(["jersey", "period"])["speed"].diff() * FPS

    rows = []
    for jersey, p in long.groupby("jersey"):
        on_pitch = p["x"].notna()
        if not on_pitch.any():
            continue
        s, a = p["speed"].fillna(0), p["accel"].fillna(0)
        rows.append({
            "jersey": jersey,
            "minutes": on_pitch.sum() / FPS / 60,
            "total_distance_m": s.sum() / FPS,
            "hsr_distance_m": s[s >= HSR_SPEED].sum() / FPS,
            "sprint_distance_m": s[s >= SPRINT_SPEED].sum() / FPS,
            "sprint_efforts": count_efforts(s >= SPRINT_SPEED, FPS),          # >= 1 s
            "accels": count_efforts(a >= ACCEL_THRESHOLD, FPS // 2),          # >= 0.5 s
            "decels": count_efforts(a <= -ACCEL_THRESHOLD, FPS // 2),
            "max_speed_ms": p["speed"].rolling(FPS, min_periods=FPS).mean().max(),  # best 1-s average
        })
    return pd.DataFrame(rows)
