# MarketPulse — AI-Powered Market Intelligence & Anomaly Detection

A full-stack portfolio project for exploring market prices, flagging unusual price/volume patterns, and scoring the sentiment of imported financial headlines.

> **Data honesty:** The bundled `sample_prices.csv` and `sample_news.csv` are synthetic fictional examples, created solely to demonstrate the application. They are **not real market prices or real news**. Use the optional Yahoo Finance ingestion for market history, and import a properly licensed news dataset for real headline analysis. Anomaly flags are exploratory signals, not evidence of wrongdoing or investment advice.

## Contents

- **Frontend:** React + Vite dashboard, Recharts visualizations, risk-signal log, news-sentiment list, CSV import control.
- **Backend:** FastAPI REST API, SQLAlchemy data access, SQLite by default, PostgreSQL support, ingestion and analytical services.
- **Analytics:** Isolation Forest plus transparent statistical rules for unusual returns, ranges, and volume ratios.
- **Text scoring:** VADER sentiment with a simple fallback if VADER is unavailable.
- **Quality:** Pytest tests for analytics, sentiment, and API health endpoints.
- **Deployment:** Dockerfiles and Docker Compose for a PostgreSQL-backed stack.

## 1. Prerequisites

- Python 3.11 or newer (3.12 recommended)
- Node.js 20 or newer and npm
- Git (optional)
- Docker Desktop (optional, only for the container setup)

## 2. Run locally — easiest path

### A. Start the API

Open a terminal in the repository root:

```bash
cd backend
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install dependencies and start the API:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

On first startup, the app creates its tables and imports the bundled example dataset into `backend/marketpulse.db`. This seed step happens automatically when the price table is empty. Keep this terminal running.

Check these addresses:

- API health: <http://localhost:8000/health>
- Interactive API docs: <http://localhost:8000/docs>
- Available symbols: <http://localhost:8000/api/symbols>
- Example market response: <http://localhost:8000/api/market/AAPL?days=180>
- Example anomalies: <http://localhost:8000/api/anomalies?symbol=AAPL>

### B. Start the dashboard

Open a second terminal from the repository root:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The frontend calls `http://localhost:8000` by default. If your API runs elsewhere, create `frontend/.env` based on `frontend/.env.example` and set `VITE_API_BASE_URL` to your API URL; restart Vite after changing it.

### C. First things to try

1. Switch between AAPL, MSFT, NVDA, and TSLA.
2. Change the chart period between 1M, 3M, 6M, and 1Y.
3. Inspect the flagged sessions and read the reason for each anomaly.
4. Review the news sentiment. Bundled headlines are clearly labelled as fictional demo examples.
5. Try the **Sync live data** button after installing the optional live-data package (see below).
6. Import your own news CSV using **Import CSV**.

## 3. Optional: load market history from Yahoo Finance

Live download is optional so the demo runs without a provider dependency. Yahoo Finance access and availability can change, so failures are reported rather than hidden.

In the activated Python environment, from `backend/`:

```bash
pip install -r requirements-live.txt
```

Restart the API, then use the dashboard's **Sync live data** button or call:

```bash
curl -X POST 'http://localhost:8000/api/ingest/AAPL?period=1y'
```

Allowed periods: `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`. The supported provider source is Yahoo Finance via the community `yfinance` package. The project does not guarantee provider availability, timeliness, completeness, or usage rights. Verify price adjustments and exchange calendars before using this in any decision-making workflow.

The app retains existing dates and upserts fetched dates by `(symbol, date)`. A live import for the same symbol/date replaces the synthetic value and labels the row `yfinance` in the database; it does not silently label synthetic data as real. If you want a clean demo database again, stop the API, delete `backend/marketpulse.db`, and restart it. That re-seeds synthetic example data.

## 4. Import headline/news sentiment data

The dashboard accepts a CSV with these columns:

- **Required:** `symbol`, `published_at`, `title`
- **Optional:** `summary`, `source`, `url`

Example `news.csv`:

```csv
symbol,published_at,title,summary,source,url
AAPL,2026-09-15T12:00:00Z,Example title here,Short article summary,Your source,https://example.com/article
```

Use real headlines only when you have permission to use the data. The URL field is displayed as a link; only import URLs you trust. Sentiment is calculated across the title and summary using VADER. It is a simple text classification signal, not a financial forecast. The UI labels source data so that synthetic examples are identifiable.

The same import is available through `POST /api/news/import` with a multipart field named `file`:

```bash
curl -X POST http://localhost:8000/api/news/import -F 'file=@news.csv'
```

## 5. Run tests

From `backend/`, with dependencies installed:

```bash
pytest -q
```

The tests cover empty/typical anomaly-detector behavior, the presence of explanation fields, sentiment output shape, and API health checks. They are a starting point, not a substitute for data-quality tests and end-to-end browser tests.

## 6. Run with Docker Compose (optional)

From the repository root, with Docker running:

```bash
docker compose up --build
```

Services:

- Dashboard: <http://localhost:5173>
- API: <http://localhost:8000>
- API docs: <http://localhost:8000/docs>
- PostgreSQL: localhost port 5432 (development credentials are defined in `docker-compose.yml`)

This configuration is for local development. Change the example credentials and add appropriate secrets, TLS, restricted origins, migrations, and production process management before any shared or public deployment.

## 7. API reference

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/api/symbols` | Symbols stored in the database |
| `GET` | `/api/market/{symbol}?days=180` | Daily OHLCV data and data-source counts |
| `GET` | `/api/summary?symbol=AAPL` | Latest close, daily return, average volume, anomaly count |
| `GET` | `/api/anomalies?symbol=AAPL&limit=20` | Anomaly flags, severities, scores, and reasons |
| `GET` | `/api/news?symbol=AAPL` | Imported headlines and sentiment scores |
| `POST` | `/api/ingest/{symbol}?period=1y` | Optional Yahoo Finance history ingestion |
| `POST` | `/api/news/import` | Import a news CSV file |

## 8. How the anomaly detector works

1. Sort price bars chronologically and compute daily percentage return and intraday range as a percentage of close.
2. Compare volume to a rolling average of prior sessions; a ratio at or above 2.5× is a transparent rule-based flag.
3. Standardize recent returns relative to a rolling baseline and flag extreme moves; also flag unusually wide high-low ranges.
4. Fit an Isolation Forest over daily return, volume ratio, intraday range, and return z-score when enough observations exist.
5. Return an alert if a rule fires **or** the model flags an outlier. Each alert includes severity, method, score, and reason.

The model is intentionally a retrospective screening example. Isolation Forest is fit across the selected history, so its output should not be presented as an online real-time predictive model. Thresholds need careful validation for each market, security type, and time period. A real surveillance system would need calibrated models, corporate-action handling, exchange calendars, resilient data pipelines, audit logs, drift monitoring, and a rigorous human-review workflow.

## 9. Architecture

```text
Optional Yahoo Finance ──> Ingestion service ──> SQL database
                                                   │
Bundled synthetic CSV ──> Seed loader ──────────────┤
                                                   ▼
                                        Analytics + sentiment services
                                                   │
                                                   ▼
                                     FastAPI REST endpoints (/api/*)
                                                   │
                                                   ▼
                                     React dashboard (Vite + Recharts)
```

## 10. Project structure

```text
marketpulse/
├── README.md
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── requirements-live.txt
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── database.py
│   │   ├── config.py
│   │   ├── schemas.py
│   │   ├── ingestion.py
│   │   ├── analytics.py
│   │   └── sentiment.py
│   ├── data/
│   │   ├── sample_prices.csv
│   │   └── sample_news.csv
│   └── tests/
│       ├── test_api.py
│       ├── test_analytics.py
│       └── test_sentiment.py
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        └── styles.css
```

## 11. Useful next upgrades

- Add walk-forward anomaly evaluation and document precision/recall against reviewed examples.
- Add schema migrations with Alembic and scheduled ingestion with retry/backoff.
- Add typed API error states, end-to-end browser tests, logging, and monitoring.
- Use a licensed news provider and link the sentiment time series to market sessions without implying causation.
- Add user-configurable thresholds, alert deduplication, and a review/feedback workflow.
- Add an authentication and authorization layer before making the app public.

## Resume guidance

List only technologies and features that you actually run and can explain. After you have measured the system, add defensible numbers (for example, rows processed, test count, or measured latency) rather than inventing metrics. The included dataset is synthetic until you deliberately ingest external price data.

## License

MIT license; see `LICENSE`. Third-party packages and external market/news data remain subject to their respective licenses and terms.
