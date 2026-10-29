"""Market data preparation and anomaly detection."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


def detect_anomalies(prices: list[dict], contamination: float = 0.05) -> list[dict]:
    """Flag unusual sessions using Isolation Forest plus interpretable rules.

    Expected input is chronologically sorted or sortable dictionaries with date,
    open/high/low/close/volume and optional symbol. The detector is retrospective:
    its scores describe unusual observations in the supplied time window.
    """
    if not prices:
        return []

    df = pd.DataFrame(prices).copy()
    required = {"date", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required price columns: {', '.join(sorted(missing))}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df:
            df[col] = df["close"] if col == "open" else 0
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["date", "high", "low", "close", "volume"])
    df = df.sort_values("date").reset_index(drop=True)
    df = df[(df["close"] > 0) & (df["volume"] >= 0)]
    if df.empty:
        return []

    df["daily_return_pct"] = df["close"].pct_change().mul(100.0)
    df["range_pct"] = (df["high"] - df["low"]).clip(lower=0).div(df["close"]).mul(100.0)
    prior_mean = df["volume"].rolling(window=20, min_periods=5).mean().shift(1)
    expanding_mean = df["volume"].expanding(min_periods=2).mean().shift(1)
    baseline = prior_mean.fillna(expanding_mean).replace(0, np.nan)
    df["volume_ratio"] = (df["volume"] / baseline).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    returns = df["daily_return_pct"]
    return_mean = returns.rolling(window=20, min_periods=5).mean().shift(1)
    return_std = returns.rolling(window=20, min_periods=5).std(ddof=0).shift(1)
    return_mean = return_mean.fillna(returns.expanding(min_periods=2).mean().shift(1)).fillna(0)
    return_std = return_std.fillna(returns.expanding(min_periods=3).std(ddof=0).shift(1)).replace(0, np.nan).fillna(1.0)
    df["return_z"] = ((returns - return_mean) / return_std).replace([np.inf, -np.inf], np.nan).fillna(0)

    feature_cols = ["daily_return_pct", "volume_ratio", "range_pct", "return_z"]
    features = df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
    isolation_flags = np.zeros(len(df), dtype=bool)
    isolation_scores = np.zeros(len(df), dtype=float)
    if len(df) >= 30 and features.nunique().sum() > 1:
        model = IsolationForest(
            n_estimators=200,
            contamination=max(0.01, min(0.15, float(contamination))),
            random_state=42,
            n_jobs=-1,
        )
        model.fit(features)
        isolation_flags = model.predict(features) == -1
        # Higher values mean more isolated/unusual observations.
        isolation_scores = -model.decision_function(features)

    output: list[dict] = []
    for idx, row in df.iterrows():
        volume_spike = float(row["volume_ratio"]) >= 2.5
        return_outlier = abs(float(row["return_z"])) >= 3.0 or abs(float(row["daily_return_pct"] or 0)) >= 7.0
        wide_range = float(row["range_pct"]) >= 5.0
        rule_flag = volume_spike or return_outlier or wide_range
        is_flag = bool(rule_flag or isolation_flags[idx])
        if not is_flag:
            continue

        reasons = []
        if volume_spike:
            reasons.append(f"Volume was {float(row['volume_ratio']):.1f}× its prior baseline")
        if return_outlier:
            reasons.append(f"Daily return was {float(row['daily_return_pct']):+.2f}% (unusual vs. recent returns)")
        if wide_range:
            reasons.append(f"Intraday high-low range was {float(row['range_pct']):.1f}% of close")
        if not reasons:
            reasons.append("Isolation Forest identified a multivariate outlier")

        severity = "Low"
        if float(row["volume_ratio"]) >= 4.0 or abs(float(row["daily_return_pct"] or 0)) >= 7.0 or float(row["range_pct"]) >= 8.0:
            severity = "High"
        elif volume_spike or return_outlier or wide_range:
            severity = "Medium"

        output.append({
            "symbol": str(row.get("symbol", "UNKNOWN")),
            "date": row["date"].date().isoformat(),
            "close": round(float(row["close"]), 4),
            "volume": int(row["volume"]),
            "daily_return_pct": round(float(row["daily_return_pct"]) if pd.notna(row["daily_return_pct"]) else 0.0, 4),
            "volume_ratio": round(float(row["volume_ratio"]), 4),
            "anomaly_score": round(float(isolation_scores[idx]), 5),
            "severity": severity,
            "reason": "; ".join(reasons),
            "detector": "Rules + Isolation Forest" if isolation_flags[idx] and rule_flag else ("Isolation Forest" if isolation_flags[idx] else "Statistical rules"),
        })
    return output
