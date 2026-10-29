"""Application configuration for MarketPulse."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Load the repository-root .env when launched from the project, and backend/.env
# when launched from the backend directory. Environment variables still win.
_candidates = [Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]
for _candidate in _candidates:
    if _candidate.exists():
        load_dotenv(_candidate, override=False)

APP_NAME = os.getenv("APP_NAME", "MarketPulse API")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./marketpulse.db")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]
SAMPLE_DATA_DIR = Path(os.getenv("SAMPLE_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data")))
