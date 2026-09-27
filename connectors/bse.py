"""BSE connector — fallback when NSE data is missing/incomplete."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ..config import BSE_BASE, SRC_OFFICIAL
from .base import BaseConnector, DataPoint

log = logging.getLogger(__name__)


class BSEConnector(BaseConnector):
    name = "bse"
    kind = "official"

    def fetch_subscription(self, scripcode: str | None = None) -> DataPoint:
        url = "https://www.bseindia.com/markets/MarketInfo/DispNewNoticesCirculars.aspx"
        try:
            with httpx.Client(timeout=20, follow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0"}) as c:
                r = c.get(url)
                if r.status_code == 200:
                    return DataPoint(value={"info": "BSE subscription page reachable; "
                                                   "per-IPO bid API requires scrip mapping."},
                                     source=SRC_OFFICIAL, source_url=url,
                                     observed_at=datetime.now(timezone.utc),
                                     data_type="ipo_subscription")
        except Exception as e:  # pragma: no cover
            log.debug("BSE fetch failed: %s", e)
        return DataPoint(value=None, source=SRC_OFFICIAL, source_url=url,
                         data_type="ipo_subscription")
