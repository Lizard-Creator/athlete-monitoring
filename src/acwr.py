"""Daily load series + acute:chronic workload ratio (rolling-average and EWMA versions)."""
import pandas as pd

ACUTE_DAYS, CHRONIC_DAYS = 7, 28
HIGH, LOW = 1.5, 0.8  # common (and debated - see README) risk bands


def daily_load(sessions: pd.DataFrame, metrics=("srpe_au", "total_distance_m", "hsr_distance_m")) -> pd.DataFrame:
    """One row per player per calendar day; rest days filled with 0 so rolling windows count real days."""
    s = sessions.assign(date=pd.to_datetime(sessions["date"]))
    daily = s.groupby(["player_id", "date"])[list(metrics)].sum()
    all_days = pd.date_range(s["date"].min(), s["date"].max(), freq="D")
    idx = pd.MultiIndex.from_product([daily.index.levels[0], all_days], names=["player_id", "date"])
    return daily.reindex(idx, fill_value=0).reset_index()


def add_acwr(daily: pd.DataFrame, metric: str = "srpe_au") -> pd.DataFrame:
    """Add acute, chronic, rolling ACWR, EWMA ACWR and a risk flag for `metric`."""
    out = daily.sort_values(["player_id", "date"]).copy()
    g = out.groupby("player_id")[metric]
    out["acute_7d"] = g.transform(lambda s: s.rolling(ACUTE_DAYS, min_periods=ACUTE_DAYS).mean())
    out["chronic_28d"] = g.transform(lambda s: s.rolling(CHRONIC_DAYS, min_periods=CHRONIC_DAYS).mean())
    out["acwr"] = (out["acute_7d"] / out["chronic_28d"]).where(out["chronic_28d"] > 0)

    # EWMA (Williams et al. 2017): decay = 2 / (N + 1). Weights recent days more; no hard window edge.
    ewma_a = g.transform(lambda s: s.ewm(alpha=2 / (ACUTE_DAYS + 1), adjust=False).mean())
    ewma_c = g.transform(lambda s: s.ewm(alpha=2 / (CHRONIC_DAYS + 1), adjust=False).mean())
    out["acwr_ewma"] = (ewma_a / ewma_c).where(out["chronic_28d"].notna() & (ewma_c > 0))

    out["acwr_flag"] = pd.cut(out["acwr"], [0, LOW, HIGH, float("inf")],
                              labels=["Low", "Normal", "High"], right=False).astype("string")
    out["date"] = out["date"].dt.date
    return out
