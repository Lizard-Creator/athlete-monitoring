"""End-to-end: download tracking -> real match loads -> simulated season -> ACWR -> SQLite + Power BI CSVs.

Run from the project root:  python src/pipeline.py
"""
import sqlite3
import urllib.request
from pathlib import Path

import pandas as pd

from acwr import add_acwr, daily_load
from season import player_profiles, simulate_season
from tracking import player_loads, read_metrica

ROOT = Path(__file__).resolve().parents[1]
RAW, PROCESSED, OUT = ROOT / "data" / "raw", ROOT / "data" / "processed", ROOT / "outputs"
DB = OUT / "athlete_monitoring.db"
BASE_URL = "https://raw.githubusercontent.com/metrica-sports/sample-data/master/data"
GAMES = [1, 2]  # home team of each sample game forms our (anonymised) squad


def download():
    RAW.mkdir(parents=True, exist_ok=True)
    for g in GAMES:
        name = f"Sample_Game_{g}_RawTrackingData_Home_Team.csv"
        dest = RAW / name
        if not dest.exists():
            print(f"Downloading {name} (~32 MB)...")
            urllib.request.urlretrieve(f"{BASE_URL}/Sample_Game_{g}/{name}", dest)


def match_loads() -> pd.DataFrame:
    cache = PROCESSED / "match_loads.csv"
    if cache.exists():
        return pd.read_csv(cache)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    frames = []
    for g in GAMES:
        print(f"Processing tracking for game {g}...")
        loads = player_loads(read_metrica(RAW / f"Sample_Game_{g}_RawTrackingData_Home_Team.csv"))
        loads["source_game"] = f"G{g}"
        loads["player_id"] = [f"G{g}-{j:02d}" for j in loads["jersey"]]
        frames.append(loads)
    df = pd.concat(frames, ignore_index=True)
    df.to_csv(cache, index=False)
    return df


def load_sqlite(tables: dict):
    OUT.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB) as con:
        con.executescript((ROOT / "sql" / "schema.sql").read_text())
        for name, df in tables.items():
            df.to_sql(name, con, if_exists="append", index=False)
        con.executescript((ROOT / "sql" / "views.sql").read_text())


def export_powerbi(tables: dict):
    folder = OUT / "powerbi"
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(folder / f"{name}.csv", index=False)
    with sqlite3.connect(DB) as con:
        for view in ("v_weekly_load", "v_latest_status", "v_md_profile"):
            pd.read_sql(f"SELECT * FROM {view}", con).to_csv(folder / f"{view}.csv", index=False)


def main():
    download()
    loads = match_loads()
    profiles = player_profiles(loads)
    sessions, wellness, injuries = simulate_season(profiles)
    daily = add_acwr(daily_load(sessions))

    players = profiles[["player_id", "source_game", "jersey", "position", "status", "max_speed_ms"]]
    real = loads[loads["player_id"].isin(players["player_id"])]
    tables = {
        "players": players,
        "match_loads": real[["player_id", "source_game", "minutes", "total_distance_m", "hsr_distance_m",
                             "sprint_distance_m", "sprint_efforts", "accels", "decels", "max_speed_ms"]],
        "sessions": sessions, "wellness": wellness, "injuries": injuries,
        "daily_load": daily[["player_id", "date", "srpe_au", "total_distance_m", "hsr_distance_m",
                             "acute_7d", "chronic_28d", "acwr", "acwr_ewma", "acwr_flag"]],
    }
    load_sqlite(tables)
    export_powerbi(tables)
    print(f"\nPlayers: {len(players)} | sessions: {len(sessions)} | injuries: {len(injuries)}")
    print(f"SQLite: {DB}\nPower BI CSVs: {OUT / 'powerbi'}")


if __name__ == "__main__":
    main()
