"""Typed API response models."""
from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, Field


class PricePoint(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float | None = None
    volume: int
    data_source: str


class MarketResponse(BaseModel):
    symbol: str
    prices: list[PricePoint]
    source_summary: dict[str, int]


class AnomalyPoint(BaseModel):
    symbol: str
    date: date
    close: float
    volume: int
    daily_return_pct: float
    volume_ratio: float
    anomaly_score: float
    severity: str
    reason: str
    detector: str


class AnomaliesResponse(BaseModel):
    symbol: str
    count: int
    anomalies: list[AnomalyPoint]


class NewsItem(BaseModel):
    id: int
    symbol: str
    published_at: datetime
    title: str
    summary: str
    source: str
    url: str | None = None
    sentiment: str
    sentiment_score: float


class IngestResponse(BaseModel):
    symbol: str
    rows_inserted_or_updated: int
    source: str
    message: str
