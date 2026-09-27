"""NSE connector — issue info, subscription stats, market data, announcements.

Uses only public endpoints. NSE blocks naive clients, so we send browser
headers + cookie bootstrap. Every failure returns Data-unavailable, never
a fabricated number.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ..config import NSE_BASE, SRC_OFFICIAL
from .base import BaseConnector, DataPoint

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


class NSEConnector(BaseConnector):
    name = "nse"
    kind = "official"

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout

    def _client(self) -> httpx.Client:
        c = httpx.Client(base_url=NSE_BASE, headers=_HEADERS, timeout=self.timeout,
                         follow_redirects=True)
        try:  # cookie bootstrap; ignore failures
            c.get("/", timeout=10)
        except Exception as e:  # pragma: no cover
            log.debug("NSE cookie bootstrap failed: %s", e)
        return c

    def fetch_subscription(self, symbol: str) -> DataPoint:
        """Fetch IPO subscription / bid details (best-effort public endpoints)."""
        urls = [
            f"/api/ipo-subscription?symbol={symbol}",
            f"/api/ipo-bid-details?symbol={symbol}",
        ]
        c = self._client()
        try:
            for u in urls:
                try:
                    r = c.get(u)
                    if r.status_code == 200:
                        try:
                            payload = r.json()
                        except Exception:
                            continue
                        return DataPoint(value=payload, source=SRC_OFFICIAL,
                                         source_url=NSE_BASE + u,
                                         observed_at=datetime.now(timezone.utc),
                                         data_type="ipo_subscription")
                except Exception as e:
                    log.debug("NSE subscription fetch failed %s: %s", u, e)
        finally:
            try:
                c.close()
            except Exception:
                pass
        return DataPoint(value=None, source=SRC_OFFICIAL,
                         source_url=NSE_BASE, data_type="ipo_subscription")

    def fetch_quote(self, symbol: str) -> DataPoint:
        url = f"/api/quote-equity?symbol={symbol}"
        c = self._client()
        try:
            r = c.get(url)
            if r.status_code == 200:
                return DataPoint(value=r.json(), source=SRC_OFFICIAL,
                                 source_url=NSE_BASE + url,
                                 observed_at=datetime.now(timezone.utc),
                                 data_type="market_quote")
        except Exception as e:  # pragma: no cover
            log.debug("NSE quote failed: %s", e)
        finally:
            try:
                c.close()
            except Exception:
                pass
        return DataPoint(value=None, source=SRC_OFFICIAL,
                         source_url=NSE_BASE + url, data_type="market_quote")

    def fetch_ipo_master(self) -> DataPoint:
        """Upcoming-IPO master list (endpoint availability varies)."""
        url = "/api/ipo-current"
        c = self._client()
        try:
            r = c.get(url)
            if r.status_code == 200:
                return DataPoint(value=r.json(), source=SRC_OFFICIAL,
                                 source_url=NSE_BASE + url,
                                 observed_at=datetime.now(timezone.utc),
                                 data_type="ipo_master")
        except Exception as e:  # pragma: no cover
            log.debug("NSE IPO master failed: %s", e)
        finally:
            try:
                c.close()
            except Exception:
                pass
        return DataPoint(value=None, source=SRC_OFFICIAL,
                         source_url=NSE_BASE + url, data_type="ipo_master")
