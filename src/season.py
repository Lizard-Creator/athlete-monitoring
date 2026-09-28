"""Simulate a season of training + matches, calibrated from each player's REAL match physical profile.

Public tracking data only covers a couple of matches, but load monitoring (ACWR, weekly trends)
needs months of daily data. So: real match output -> per-minute rates -> simulated season calendar.
Everything produced here is labelled synthetic; only the per-player physical profiles are real.
"""
import numpy as np
import pandas as pd

METRICS = ["total_distance_m", "hsr_distance_m", "sprint_distance_m", "sprint_efforts", "accels", "decels"]

# Load as a fraction of a full-match (90 min) load, per matchday code: distance, hsr, sprint, accel/decel
DAY_PROFILE = {
    "MD+1": dict(dist=0.25, hsr=0.10, sprint=0.05, acc=0.20, minutes=45, rpe=3),
    "MD-4": dict(dist=0.60, hsr=0.40, sprint=0.30, acc=1.00, minutes=80, rpe=6),  # strength / small-sided
    "MD-3": dict(dist=0.70, hsr=0.75, sprint=0.70, acc=0.60, minutes=80, rpe=7),  # endurance / speed
    "MD-2": dict(dist=0.55, hsr=0.40, sprint=0.30, acc=0.50, minutes=70, rpe=5),
    "MD-1": dict(dist=0.35, hsr=0.20, sprint=0.25, acc=0.30, minutes=50, rpe=3),
    "COMP": dict(dist=0.60, hsr=0.70, sprint=0.60, acc=0.60, minutes=60, rpe=6),  # non-starters' top-up
    "REHAB": dict(dist=0.30, hsr=0.10, sprint=0.00, acc=0.20, minutes=60, rpe=4),
}
METRIC_KEY = {"total_distance_m": "dist", "hsr_distance_m": "hsr", "sprint_distance_m": "sprint",
              "sprint_efforts": "sprint", "accels": "acc", "decels": "acc"}

# Weekday (Mon=0) -> matchday code. Normal week: Saturday match. Congested week: Wednesday + Saturday.
NORMAL_WEEK = {0: None, 1: "MD-4", 2: "MD-3", 3: "MD-2", 4: "MD-1", 5: "MD", 6: "MD+1"}
CONGESTED_WEEK = {0: "MD-2", 1: "MD-1", 2: "MD", 3: "MD+1", 4: "MD-1", 5: "MD", 6: "MD+1"}


def player_profiles(match_loads: pd.DataFrame, min_minutes: float = 20) -> pd.DataFrame:
    """Per-90 rates for each player, plus position (lowest running output per game = GK) and squad status."""
    df = match_loads[match_loads["minutes"] >= min_minutes].copy()
    for m in METRICS:
        df[f"{m}_p90"] = df[m] / df["minutes"] * 90
    gk = df.groupby("source_game")["total_distance_m_p90"].idxmin()
    df["position"] = np.where(df.index.isin(gk), "GK", "Outfield")
    df["status"] = np.where(df["minutes"] >= 60, "Regular", "Squad")
    return df.reset_index(drop=True)


def simulate_season(profiles: pd.DataFrame, start="2025-08-04", weeks=30, seed=7):
    """Return (sessions, wellness, injuries) DataFrames for a synthetic season."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=weeks * 7, freq="D")
    congested = set(rng.choice(range(4, weeks), size=weeks // 6, replace=False))
    injured_until = {p: pd.Timestamp.min for p in profiles["player_id"]}
    sessions, wellness, injuries = [], [], []

    for d in dates:
        week = (d - dates[0]).days // 7
        code = (CONGESTED_WEEK if week in congested else NORMAL_WEEK)[d.weekday()]
        available = [p for p in profiles["player_id"] if injured_until[p] < d]

        if code == "MD":
            minutes = _pick_match_minutes(profiles[profiles["player_id"].isin(available)], rng)

        for _, pl in profiles.iterrows():
            pid = pl["player_id"]
            if injured_until[pid] >= d:
                if d.weekday() < 5:  # rehab on weekdays
                    sessions.append(_session(pl, d, "REHAB", "Rehab", DAY_PROFILE["REHAB"], rng))
                continue
            if code is None:
                continue
            if code == "MD":
                mins = minutes.get(pid, 0)
                if mins > 0:
                    prof = dict(dist=mins / 90, hsr=mins / 90, sprint=mins / 90, acc=mins / 90,
                                minutes=mins, rpe=8)
                    sessions.append(_session(pl, d, "MD", "Match", prof, rng))
                else:
                    sessions.append(_session(pl, d, "COMP", "Training", DAY_PROFILE["COMP"], rng))
            else:
                sessions.append(_session(pl, d, code, "Training", DAY_PROFILE[code], rng))

            if rng.random() < 0.004:  # ~1 time-loss injury per player per ~8 months of exposure
                days_out = int(rng.integers(7, 35))
                injured_until[pid] = d + pd.Timedelta(days=days_out)
                injuries.append({"player_id": pid, "injury_date": d.date(),
                                 "return_date": (d + pd.Timedelta(days=days_out + 1)).date(),
                                 "days_out": days_out})

    sessions = pd.DataFrame(sessions)
    wellness = _simulate_wellness(sessions, rng)
    return sessions, wellness, pd.DataFrame(injuries)


def _pick_match_minutes(avail: pd.DataFrame, rng) -> dict:
    """11 starters (one GK) weighted towards regulars; 3-5 subs."""
    gks, outfield = avail[avail["position"] == "GK"], avail[avail["position"] == "Outfield"]
    w = np.where(outfield["status"] == "Regular", 4.0, 1.0)
    order = list(rng.choice(outfield["player_id"], size=len(outfield), replace=False, p=w / w.sum()))
    starters, bench = order[:10], order[10:]
    minutes = {rng.choice(gks["player_id"]): 90} if len(gks) else {}
    n_subs = int(rng.integers(3, 6))
    subbed_off = rng.choice(starters, size=min(n_subs, len(starters)), replace=False)
    for p in starters:
        minutes[p] = int(rng.integers(60, 86)) if p in subbed_off else 90
    for p in bench[:n_subs]:
        minutes[p] = int(rng.integers(5, 31))
    return minutes


def _session(pl, date, md_code, session_type, prof, rng) -> dict:
    noise = lambda: rng.lognormal(0, 0.12)
    row = {"player_id": pl["player_id"], "date": date.date(), "session_type": session_type,
           "md_code": md_code, "duration_min": prof["minutes"]}
    for m in METRICS:
        val = pl[f"{m}_p90"] * prof[METRIC_KEY[m]] * noise()
        row[m] = round(val) if m in ("sprint_efforts", "accels", "decels") else round(val, 1)
    top = 0.97 if session_type == "Match" else (0.9 if md_code == "MD-3" else 0.75)
    row["max_speed_ms"] = round(pl["max_speed_ms"] * top * rng.uniform(0.92, 1.03), 2)
    row["rpe"] = int(np.clip(round(rng.normal(prof["rpe"], 1)), 1, 10))
    row["srpe_au"] = row["rpe"] * row["duration_min"]
    return row


def _simulate_wellness(sessions: pd.DataFrame, rng) -> pd.DataFrame:
    """Morning questionnaire (1-5, higher = better) that responds to the previous day's sRPE."""
    prev = sessions.groupby(["player_id", "date"])["srpe_au"].sum().reset_index()
    prev["date"] = pd.to_datetime(prev["date"]) + pd.Timedelta(days=1)
    strain = (prev["srpe_au"] / 700).clip(0, 1.2)
    score = lambda base: np.clip(np.round(base - 1.8 * strain + rng.normal(0, 0.6, len(prev))), 1, 5).astype(int)
    return pd.DataFrame({"player_id": prev["player_id"], "date": prev["date"].dt.date,
                         "sleep_quality": score(4.2), "fatigue": score(4.5), "soreness": score(4.6)})
