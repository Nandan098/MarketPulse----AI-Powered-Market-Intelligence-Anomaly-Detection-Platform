"""Ingestion helpers for bundled CSV data and optional Yahoo Finance history."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import csv

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import SAMPLE_DATA_DIR
from .models import MarketPrice, NewsArticle


def _as_float(value, default=0.0) -> float:
    try:
        result = float(value)
        return result if pd.notna(result) else float(default)
    except (TypeError, ValueError):
        return float(default)


def upsert_prices(db: Session, frame: pd.DataFrame, symbol: str, source: str) -> int:
    """Validate and upsert daily bars; returns number of input rows processed."""
    if frame is None or frame.empty:
        return 0
    frame = frame.copy()
    frame.columns = [str(column).strip().lower().replace(" ", "_") for column in frame.columns]
    if "date" not in frame.columns:
        if isinstance(frame.index, pd.DatetimeIndex):
            frame["date"] = frame.index
        else:
            raise ValueError("Price input must include a date column or a DatetimeIndex")
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Price input is missing columns: {', '.join(sorted(missing))}")

    symbol = symbol.strip().upper()
    processed = 0
    for _, record in frame.iterrows():
        raw_date = pd.to_datetime(record["date"], errors="coerce")
        if pd.isna(raw_date):
            continue
        day = raw_date.date()
        open_price = _as_float(record["open"])
        high = _as_float(record["high"])
        low = _as_float(record["low"])
        close = _as_float(record["close"])
        volume = int(max(0, _as_float(record["volume"])))
        if close <= 0 or min(open_price, high, low) < 0 or high < low:
            continue
        adj_close = _as_float(record.get("adj_close", record.get("adj close", close)), close)
        existing = db.scalar(select(MarketPrice).where(MarketPrice.symbol == symbol, MarketPrice.date == day))
        values = dict(
            open=open_price, high=high, low=low, close=close,
            adj_close=adj_close, volume=volume, data_source=source,
        )
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            db.add(MarketPrice(symbol=symbol, date=day, **values))
        processed += 1
    db.commit()
    return processed


def seed_sample_data(db: Session, data_dir: Path | None = None) -> dict[str, int]:
    """Load the included synthetic demonstration CSVs into the database."""
    data_dir = data_dir or SAMPLE_DATA_DIR
    price_path = data_dir / "sample_prices.csv"
    news_path = data_dir / "sample_news.csv"
    counts = {"prices": 0, "news": 0}
    if price_path.exists():
        frame = pd.read_csv(price_path)
        for symbol, symbol_frame in frame.groupby("symbol"):
            counts["prices"] += upsert_prices(
                db, symbol_frame.drop(columns=["symbol"], errors="ignore"), str(symbol), "sample_synthetic"
            )
    if news_path.exists():
        with news_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for record in csv.DictReader(handle):
                symbol = (record.get("symbol") or "").strip().upper()
                title = (record.get("title") or "").strip()
                published = pd.to_datetime(record.get("published_at"), errors="coerce", utc=True)
                if not symbol or not title or pd.isna(published):
                    continue
                exists = db.scalar(select(NewsArticle).where(
                    NewsArticle.symbol == symbol,
                    NewsArticle.published_at == published.to_pydatetime(),
                    NewsArticle.title == title,
                ))
                if exists:
                    continue
                db.add(NewsArticle(
                    symbol=symbol,
                    published_at=published.to_pydatetime(),
                    title=title,
                    summary=(record.get("summary") or "").strip(),
                    source=(record.get("source") or "Demo dataset — fictional example").strip(),
                    url=(record.get("url") or "").strip() or None,
                ))
                counts["news"] += 1
        db.commit()
    return counts


def fetch_yfinance_prices(symbol: str, period: str = "1y") -> pd.DataFrame:
    """Download recent daily OHLCV history from yfinance (optional dependency)."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("Live download requires yfinance. Install backend/requirements-live.txt.") from exc
    ticker = symbol.strip().upper()
    if not ticker or len(ticker) > 16:
        raise ValueError("Symbol must be 1–16 characters")
    allowed_periods = {"1mo", "3mo", "6mo", "1y", "2y", "5y"}
    if period not in allowed_periods:
        raise ValueError(f"Period must be one of: {', '.join(sorted(allowed_periods))}")
    raw = yf.download(ticker, period=period, interval="1d", auto_adjust=False, progress=False, threads=False)
    if raw is None or raw.empty:
        raise ValueError(f"No price history returned for {ticker}. Check the symbol or try again later.")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.reset_index()
    raw.columns = [str(c).strip().lower().replace(" ", "_") for c in raw.columns]
    rename = {"adj_close": "adj_close", "date": "date", "datetime": "date"}
    raw = raw.rename(columns=rename)
    if "date" not in raw.columns:
        raw = raw.rename(columns={raw.columns[0]: "date"})
    if "adj_close" not in raw.columns:
        raw["adj_close"] = raw["close"]
    return raw
