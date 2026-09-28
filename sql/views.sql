-- Reporting views. Run after the tables are loaded.

-- Weekly load per player with week-over-week % change (spikes > ~15% are a common talking point).
DROP VIEW IF EXISTS v_weekly_load;
CREATE VIEW v_weekly_load AS
WITH weekly AS (
    SELECT player_id,
           date(date, 'weekday 0', '-6 days') AS week_start,   -- Monday
           SUM(srpe_au)            AS srpe_au,
           SUM(total_distance_m)   AS total_distance_m,
           SUM(hsr_distance_m)     AS hsr_distance_m,
           SUM(session_type = 'Match') AS matches
    FROM sessions
    GROUP BY player_id, week_start
)
SELECT *,
       ROUND(100.0 * (srpe_au - LAG(srpe_au) OVER w) / NULLIF(LAG(srpe_au) OVER w, 0), 1) AS srpe_wow_pct
FROM weekly
WINDOW w AS (PARTITION BY player_id ORDER BY week_start);

-- Latest status per player: the "morning report" table for coaches.
DROP VIEW IF EXISTS v_latest_status;
CREATE VIEW v_latest_status AS
WITH ranked AS (
    SELECT d.*, ROW_NUMBER() OVER (PARTITION BY d.player_id ORDER BY d.date DESC) AS rn
    FROM daily_load d
)
SELECT r.player_id, p.position, r.date, ROUND(r.acwr, 2) AS acwr, ROUND(r.acwr_ewma, 2) AS acwr_ewma,
       r.acwr_flag, w.sleep_quality, w.fatigue, w.soreness,
       EXISTS (SELECT 1 FROM injuries i
               WHERE i.player_id = r.player_id AND r.date BETWEEN i.injury_date AND i.return_date) AS injured
FROM ranked r
JOIN players p USING (player_id)
LEFT JOIN wellness w ON w.player_id = r.player_id AND w.date = r.date
WHERE r.rn = 1;

-- Average load by matchday code: shows the weekly periodisation "shape".
DROP VIEW IF EXISTS v_md_profile;
CREATE VIEW v_md_profile AS
SELECT md_code,
       COUNT(*)                          AS sessions,
       ROUND(AVG(total_distance_m))      AS avg_distance_m,
       ROUND(AVG(hsr_distance_m))        AS avg_hsr_m,
       ROUND(AVG(sprint_distance_m))     AS avg_sprint_m,
       ROUND(AVG(accels + decels), 1)    AS avg_acc_dec,
       ROUND(AVG(srpe_au))               AS avg_srpe_au
FROM sessions
GROUP BY md_code;
