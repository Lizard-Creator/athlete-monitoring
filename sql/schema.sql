-- Athlete monitoring warehouse (SQLite). Loaded by src/pipeline.py.

DROP TABLE IF EXISTS players;
CREATE TABLE players (
    player_id     TEXT PRIMARY KEY,
    source_game   TEXT NOT NULL,   -- which real Metrica match the physical profile came from
    jersey        INTEGER,
    position      TEXT,            -- GK / Outfield
    status        TEXT,            -- Regular / Squad
    max_speed_ms  REAL
);

DROP TABLE IF EXISTS match_loads;   -- REAL tracking-derived outputs
CREATE TABLE match_loads (
    player_id          TEXT REFERENCES players(player_id),
    source_game        TEXT,
    minutes            REAL,
    total_distance_m   REAL,
    hsr_distance_m     REAL,
    sprint_distance_m  REAL,
    sprint_efforts     INTEGER,
    accels             INTEGER,
    decels             INTEGER,
    max_speed_ms       REAL
);

DROP TABLE IF EXISTS sessions;      -- SIMULATED season
CREATE TABLE sessions (
    player_id          TEXT REFERENCES players(player_id),
    date               DATE,
    session_type       TEXT,        -- Match / Training / Rehab
    md_code            TEXT,        -- MD, MD-1 ... MD-4, MD+1, COMP, REHAB
    duration_min       INTEGER,
    total_distance_m   REAL,
    hsr_distance_m     REAL,
    sprint_distance_m  REAL,
    sprint_efforts     INTEGER,
    accels             INTEGER,
    decels             INTEGER,
    max_speed_ms       REAL,
    rpe                INTEGER,
    srpe_au            INTEGER
);

DROP TABLE IF EXISTS wellness;
CREATE TABLE wellness (
    player_id      TEXT REFERENCES players(player_id),
    date           DATE,
    sleep_quality  INTEGER,  -- 1-5, higher = better
    fatigue        INTEGER,
    soreness       INTEGER
);

DROP TABLE IF EXISTS injuries;
CREATE TABLE injuries (
    player_id    TEXT REFERENCES players(player_id),
    injury_date  DATE,
    return_date  DATE,
    days_out     INTEGER
);

DROP TABLE IF EXISTS daily_load;
CREATE TABLE daily_load (
    player_id         TEXT REFERENCES players(player_id),
    date              DATE,
    srpe_au           REAL,
    total_distance_m  REAL,
    hsr_distance_m    REAL,
    acute_7d          REAL,
    chronic_28d       REAL,
    acwr              REAL,
    acwr_ewma         REAL,
    acwr_flag         TEXT,
    PRIMARY KEY (player_id, date)
);
