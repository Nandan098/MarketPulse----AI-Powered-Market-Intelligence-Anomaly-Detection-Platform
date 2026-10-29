"""MarketPulse API entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from io import BytesIO

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .analytics import detect_anomalies
from .config import APP_NAME, CORS_ORIGINS
from .database import Base, SessionLocal, engine, get_db
from .ingestion import fetch_yfinance_prices, seed_sample_data, upsert_prices
from .models import MarketPrice, NewsArticle
from .schemas import AnomaliesResponse, IngestResponse, MarketResponse, NewsItem, PricePoint
from .sentiment import score_sentiment

def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        price_count = db.scalar(select(func.count(MarketPrice.id))) or 0
        if price_count == 0:
            seed_sample_data(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title=APP_NAME,
    description=(
        "Market-data analytics demo with anomaly detection, news sentiment, and a dashboard. "
        "Bundled price/news records are synthetic examples, not actual market or news data."
    ),
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["system"])
def root():
    return {"name": APP_NAME, "version": "1.0.0", "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": "marketpulse-api"}


@app.get("/api/symbols", tags=["market"])
def list_symbols(db: Session = Depends(get_db)):
    rows = db.execute(
        select(MarketPrice.symbol, func.count(MarketPrice.id), func.max(MarketPrice.date))
        .group_by(MarketPrice.symbol).order_by(MarketPrice.symbol)
    ).all()
    return [{"symbol": row[0], "row_count": int(row[1]), "latest_date": row[2].isoformat() if row[2] else None} for row in rows]


def _get_prices(db: Session, symbol: str, days: int | None = 180) -> list[MarketPrice]:
    symbol = symbol.strip().upper()
    stmt = select(MarketPrice).where(MarketPrice.symbol == symbol).order_by(MarketPrice.date.desc())
    if days is not None:
        stmt = stmt.limit(days)
    rows = list(db.scalars(stmt).all())
    rows.reverse()
    return rows


def _row_price(row: MarketPrice) -> dict:
    return {
        "symbol": row.symbol,
        "date": row.date.isoformat(),
        "open": float(row.open), "high": float(row.high), "low": float(row.low),
        "close": float(row.close), "adj_close": float(row.adj_close) if row.adj_close is not None else None,
        "volume": int(row.volume), "data_source": row.data_source,
    }


@app.get("/api/market/{symbol}", response_model=MarketResponse, tags=["market"])
def market_history(
    symbol: str,
    days: int = Query(default=180, ge=10, le=2000),
    db: Session = Depends(get_db),
):
    symbol = symbol.strip().upper()
    rows = _get_prices(db, symbol, days)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}. Choose a listed symbol or ingest data first.")
    summary: dict[str, int] = {}
    for row in rows:
        summary[row.data_source] = summary.get(row.data_source, 0) + 1
    return {"symbol": symbol, "prices": [_row_price(row) for row in rows], "source_summary": summary}


def _anomalies_for_rows(rows: list[MarketPrice]) -> list[dict]:
    points = [_row_price(row) for row in rows]
    return detect_anomalies(points)


@app.get("/api/anomalies", response_model=AnomaliesResponse, tags=["analytics"])
def anomalies(
    symbol: str = Query(default="AAPL", min_length=1, max_length=16),
    days: int = Query(default=180, ge=10, le=2000),
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    symbol = symbol.strip().upper()
    rows = _get_prices(db, symbol, days)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}.")
    found = _anomalies_for_rows(rows)
    found.sort(key=lambda record: record["date"], reverse=True)
    found = found[:limit]
    return {"symbol": symbol, "count": len(found), "anomalies": found}


@app.get("/api/summary", tags=["analytics"])
def market_summary(
    symbol: str = Query(default="AAPL", min_length=1, max_length=16),
    days: int = Query(default=180, ge=10, le=2000),
    db: Session = Depends(get_db),
):
    symbol = symbol.strip().upper()
    rows = _get_prices(db, symbol, days)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}.")
    latest = rows[-1]
    previous = rows[-2] if len(rows) > 1 else None
    change = ((latest.close / previous.close) - 1) * 100 if previous and previous.close else 0.0
    avg_volume = sum(item.volume for item in rows[-20:]) / min(20, len(rows))
    found = _anomalies_for_rows(rows)
    return {
        "symbol": symbol,
        "latest_date": latest.date.isoformat(),
        "latest_close": round(float(latest.close), 4),
        "day_change_pct": round(float(change), 4),
        "average_volume_20d": int(avg_volume),
        "anomaly_count": len(found),
        "source_label": "Synthetic demo data" if all(row.data_source == "sample_synthetic" for row in rows) else "Market data (source shown per record)",
        "disclaimer": "Anomaly flags are exploratory signals, not proof of misconduct or investment advice.",
    }


@app.get("/api/news", response_model=list[NewsItem], tags=["news"])
def list_news(
    symbol: str = Query(default="AAPL", min_length=1, max_length=16),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    rows = list(db.scalars(
        select(NewsArticle).where(NewsArticle.symbol == symbol.strip().upper())
        .order_by(NewsArticle.published_at.desc()).limit(limit)
    ).all())
    output = []
    for row in rows:
        label, score = score_sentiment(f"{row.title}. {row.summary}")
        output.append({
            "id": row.id, "symbol": row.symbol, "published_at": row.published_at,
            "title": row.title, "summary": row.summary, "source": row.source, "url": row.url,
            "sentiment": label, "sentiment_score": score,
        })
    return output


@app.post("/api/ingest/{symbol}", response_model=IngestResponse, tags=["ingestion"])
def ingest_live_prices(
    symbol: str,
    period: str = Query(default="1y", pattern="^(1mo|3mo|6mo|1y|2y|5y)$"),
    db: Session = Depends(get_db),
):
    """Fetch data from Yahoo Finance. Requires optional yfinance dependency and internet access."""
    try:
        frame = fetch_yfinance_prices(symbol, period)
        count = upsert_prices(db, frame, symbol, "yfinance")
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # external providers can fail for network/provider reasons
        raise HTTPException(status_code=502, detail=f"Market-data provider request failed: {exc}") from exc
    return {
        "symbol": symbol.strip().upper(), "rows_inserted_or_updated": count,
        "source": "Yahoo Finance via yfinance", "message": f"Processed {count} daily rows for {symbol.strip().upper()}.",
    }


@app.post("/api/news/import", tags=["ingestion"])
async def import_news_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import user-provided news CSV with symbol,published_at,title,summary,source,url columns."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a .csv file.")
    raw = await file.read()
    if len(raw) > 5_000_000:
        raise HTTPException(status_code=413, detail="CSV must be 5 MB or smaller.")
    try:
        frame = pd.read_csv(BytesIO(raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read CSV: {exc}") from exc
    required = {"symbol", "published_at", "title"}
    if required - set(frame.columns):
        raise HTTPException(status_code=400, detail="CSV must include: symbol, published_at, title. summary/source/url are optional.")
    inserted = 0
    for _, record in frame.iterrows():
        symbol = str(record.get("symbol", "")).strip().upper()
        title = str(record.get("title", "")).strip()
        timestamp = pd.to_datetime(record.get("published_at"), errors="coerce", utc=True)
        if not symbol or symbol == "NAN" or not title or pd.isna(timestamp):
            continue
        existing = db.scalar(select(NewsArticle).where(
            NewsArticle.symbol == symbol, NewsArticle.title == title,
            NewsArticle.published_at == timestamp.to_pydatetime(),
        ))
        if existing:
            continue
        db.add(NewsArticle(
            symbol=symbol, published_at=timestamp.to_pydatetime(), title=title,
            summary=str(record.get("summary", "") if pd.notna(record.get("summary", "")) else ""),
            source=str(record.get("source", "User imported") if pd.notna(record.get("source", "User imported")) else "User imported"),
            url=str(record.get("url", "") if pd.notna(record.get("url", "")) else "").strip() or None,
        ))
        inserted += 1
    db.commit()
    return {"rows_imported": inserted, "message": f"Imported {inserted} news rows."}
