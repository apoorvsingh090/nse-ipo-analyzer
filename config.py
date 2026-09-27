"""Central configuration for NSE IPO Analyzer."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "ipo_analyzer.db"

# SQLite by default (zero-setup local dev). Set DATABASE_URL for PostgreSQL:
#   postgresql+psycopg2://user:pass@localhost:5432/ipo_analyzer
DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}"
)

NSE_BASE = "https://www.nseindia.com"
BSE_BASE = "https://www.bseindia.com"
SEBI_BASE = "https://www.sebi.gov.in"

# Data-source labels (must be used everywhere in UI/API)
SRC_OFFICIAL = "Official exchange data"
SRC_FILING = "Company/SEBI filing"
SRC_THIRD = "Third-party data"
SRC_GMP = "Unofficial GMP"

DATA_UNAVAILABLE = "Data unavailable"

# IST label helper
TIMEZONE_LABEL = "IST"

MODEL_DIR = BASE_DIR / "ml" / "artifacts"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
