# Athlete Monitoring: Tracking Data → Load Metrics → Coach Dashboard

A sports-science data pipeline that turns raw player-tracking coordinates into the load metrics a performance
department uses daily: total distance, high-speed running, sprints, accelerations, sRPE, and acute:chronic
workload ratio (ACWR). It stores them in a SQL warehouse and feeds a Power BI coach dashboard.

**Stack:** Python (pandas, numpy) · SQLite (window functions, views) · Power BI · pytest

## What's real vs. simulated (read this first)

| Layer | Source |
|---|---|
| Match physical profiles (distance, HSR, sprints, accels, top speed per player) | **Real**: computed from Metrica Sports' open 25 Hz tracking data (2 matches, 26 players) |
| Season calendar: training sessions, matches, sRPE, wellness, injuries | **Simulated**: calibrated from each player's real per-90 output |

Public tracking data covers a few matches, but load monitoring needs months of daily data. So the pipeline
scales each player's *real* physical profile through a realistic weekly microcycle (MD-4 … MD+1, congested
weeks, rotation, injuries with rehab and return). Injuries are random (not driven by load), so **any load–injury
relationship you find in this data is not real evidence**. Say this upfront when presenting the project.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python src/pipeline.py          # downloads ~65 MB tracking data on first run
pytest -q
```

Outputs:
- `outputs/athlete_monitoring.db`: SQLite warehouse (tables + views)
- `outputs/powerbi/*.csv`: the same tables/views as CSV for Power BI

## Pipeline

```
Metrica raw tracking (x,y @ 25 Hz)
  └─ src/tracking.py   speed/accel per frame → per-player match loads          [REAL]
      └─ src/season.py per-90 rates → 30-week simulated season                 [SIMULATED]
          └─ src/acwr.py  daily series (rest days = 0) → rolling + EWMA ACWR
              └─ src/pipeline.py → SQLite (sql/schema.sql, sql/views.sql) → Power BI CSVs
```

## Metric definitions

| Metric | Definition |
|---|---|
| Total distance | Sum of smoothed speed × frame time |
| High-speed running (HSR) | Distance at ≥ 5.5 m/s (19.8 km/h) |
| Sprint distance / efforts | ≥ 7.0 m/s (25.2 km/h); an effort = ≥ 1 s continuous |
| Accels / decels | ≥ +3 / ≤ −3 m/s², lasting ≥ 0.5 s |
| Max speed | Best 1-second average speed (removes single-frame tracking noise) |
| sRPE | Session RPE (1–10) × duration (min), in arbitrary units (AU) |
| ACWR (rolling) | 7-day mean load ÷ 28-day mean load (Gabbett 2016) |
| ACWR (EWMA) | Exponentially weighted, decay 2/(N+1) (Williams et al. 2017) |
| Flags | Low < 0.8, Normal 0.8–1.5, High > 1.5 |

Thresholds differ by vendor and sport (e.g. HSR is often 5.5 or 5.8 m/s). They're constants at the top of
`tracking.py` and `acwr.py`.

**The ACWR caveat (a good interview topic):** ACWR is widely used but heavily criticized. The rolling version
is mathematically coupled (the acute week sits inside the chronic window), ratios can create spurious
correlations, and its link to injury risk is weak (Impellizzeri et al. 2020, Lolli et al. 2019). Treat it as a
*communication tool* for spotting sudden load changes, not as an injury predictor.

## SQL views

- `v_weekly_load`: weekly totals per player with week-over-week % change (`LAG` window)
- `v_latest_status`: "morning report" with latest ACWR, flag, wellness, and injury status (`ROW_NUMBER`)
- `v_md_profile`: average load per matchday code, showing the weekly periodization shape

## Dashboard

See [powerbi/DASHBOARD_SPEC.md](powerbi/DASHBOARD_SPEC.md) for pages, visuals, the data model, and DAX measures.

## Extension ideas

- [ ] Uncoupled ACWR (acute week excluded from chronic) and compare it with the coupled version
- [ ] Rolling z-scores against each player's own baseline, as an alternative to ACWR
- [ ] Positional benchmarks (split outfield players by average position from tracking)
- [ ] Add Metrica away teams / game 3 (EPTS format) to grow the squad
- [ ] Deploy: Power BI Service with scheduled refresh, or a Streamlit version

## References

- Gabbett (2016). The training–injury prevention paradox. *BJSM*
- Williams et al. (2017). Better way to determine the acute:chronic workload ratio? *BJSM*
- Impellizzeri et al. (2020). Acute:chronic workload ratio: conceptual issues and fundamental pitfalls. *IJSPP*
- Metrica Sports sample data: https://github.com/metrica-sports/sample-data
