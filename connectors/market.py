"""Market-regime connector — NIFTY / VIX / sector context (§11 market vars).

Tries the public NSE chart API; on any failure returns Data unavailable
(rather than a stale substituted value).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ..config import NSE_BASE, SRC_OFFICIAL, SRC_THIRD
from .base import DataPoint

log = logging.getLogger(__name__)


def fetch_market_snapshot() -> DataPoint:
    url = f"{NSE_BASE}/api/equity-stockIndices?index=NIFTY%2050"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
               "Accept": "application/json"}
    try:
        with httpx.Client(timeout=20, headers=headers,
                          follow_redirects=True) as c:
            c.get(NSE_BASE + "/", timeout=10)
            r = c.get(url)
            if r.status_code == 200:
                return DataPoint(value=r.json(), source=SRC_OFFICIAL,
                                 source_url=url,
                                 observed_at=datetime.now(timezone.utc),
                                 data_type="market_snapshot")
    except Exception as e:  # pragma: no cover
        log.debug("Market snapshot failed: %s", e)
    return DataPoint(value=None, source=SRC_THIRD, source_url=url,
                     data_type="market_snapshot")


def market_regime(nifty_5d_return: float | None,
                  vix: float | None) -> dict:
    """Classify market regime from pre-listing observables only."""
    if nifty_5d_return is None and vix is None:
        return {"regime": "Data unavailable", "detail": "No market data"}
    if vix is not None and vix > 20:
        vol = "high volatility"
    elif vix is not None and vix > 14:
        vol = "elevated volatility"
    else:
        vol = "normal volatility"
    direction = ("rising market" if (nifty_5d_return or 0) > 1
                 else "falling market" if (nifty_5d_return or 0) < -1
                 else "flat market")
    return {"regime": f"{direction}, {vol}",
            "nifty_5d_pct": nifty_5d_return, "vix": vix}
