# Power BI Dashboard Spec

Build this yourself. Building it is the portfolio piece. Design principle: **a coach should get the answer
from each page in 10 seconds.** Use few colors and reserve red, amber, and green for flags only.

## Data model

Import from `outputs/powerbi/` (Get Data → Text/CSV):

```
players (1) ──< sessions      (player_id)
players (1) ──< daily_load    (player_id)
players (1) ──< wellness      (player_id)
players (1) ──< injuries      (player_id)
players (1) ──< match_loads   (player_id)
Date    (1) ──< sessions / daily_load / wellness   (date)
```

Create a **Date** table (Modeling → New table) and mark it as the date table:

```DAX
Date = ADDCOLUMNS(
    CALENDAR(MIN(sessions[date]), MAX(sessions[date])),
    "Week Start", [Date] - WEEKDAY([Date], 2) + 1,
    "Weekday", FORMAT([Date], "ddd")
)
```

`v_latest_status`, `v_weekly_load`, and `v_md_profile` are pre-aggregated, so you can use them directly or
rebuild them as DAX (good practice).

## Measures

```DAX
Total Distance (km)  = DIVIDE(SUM(sessions[total_distance_m]), 1000)
HSR (m)              = SUM(sessions[hsr_distance_m])
Sprint Efforts       = SUM(sessions[sprint_efforts])
sRPE (AU)            = SUM(sessions[srpe_au])
Sessions             = COUNTROWS(sessions)

ACWR (latest) =
VAR d = MAX(daily_load[date])
RETURN CALCULATE(AVERAGE(daily_load[acwr]), daily_load[date] = d)

ACWR Colour =
SWITCH(TRUE(),
    ISBLANK([ACWR (latest)]), "#9E9E9E",
    [ACWR (latest)] > 1.5, "#D32F2F",
    [ACWR (latest)] < 0.8, "#F9A825",
    "#388E3C")

Weekly Load WoW % =
VAR thisWk = [sRPE (AU)]
VAR lastWk = CALCULATE([sRPE (AU)], DATEADD('Date'[Date], -7, DAY))
RETURN DIVIDE(thisWk - lastWk, lastWk)

Wellness Score = AVERAGEX(wellness, (wellness[sleep_quality] + wellness[fatigue] + wellness[soreness]) / 3)
```

## Pages

### 1. Squad Morning Report *(most important page)*
- **Table:** player, position, ACWR, flag, sleep, fatigue, soreness, injured. Conditional formatting uses
  `ACWR Colour` for the background, and wellness scores of 2 or below are shown in red.
- **KPI cards:** available players, players flagged High, players flagged Low, current injuries
- **Slicer:** date (defaults to the latest date)

### 2. Player Profile
- **Slicer:** player
- **Combo chart:** daily sRPE (columns) + ACWR (line), with constant lines at 0.8 and 1.5 (Analytics pane)
- **Line chart:** wellness score over time
- **Cards:** season total distance, average match HSR, top speed
- Shade injury periods if you can (e.g. a scatter or error-bar overlay from the `injuries` table), which shows the
  ACWR spike that follows return-to-play

### 3. Weekly Periodization
- **Column chart:** average load by `md_code`, sorted MD-4 → MD-1, MD, MD+1. This shows the microcycle "shape".
  Add a sort-order column in Power Query.
- **Matrix:** player × week, weekly sRPE, with a heat-map background and a WoW % tooltip
- **Line chart:** squad average weekly load across the season (congested weeks stand out)

### 4. Match Physical Report (real data)
- Built from `match_loads`: bar charts of distance, HSR, and sprint efforts per player, plus a scatter of
  distance vs HSR per 90 to show different player "profiles"
- Label this page **"Source: Metrica Sports tracking data"** to separate real data from simulated

## Portfolio polish
- Add a short "About / Data notes" page that repeats the real-vs-simulated table from the README
- Screenshot each page into the README, and publish to the web or record a 2-minute walkthrough video
- In the write-up, explain *one decision* you'd make for a coach from the dashboard, e.g. "Player X is at
  ACWR 1.6 two days after returning from injury → modify MD-3 HSR volume"
