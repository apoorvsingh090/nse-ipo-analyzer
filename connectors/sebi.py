"""SEBI + company IR connector — DRHP/RHP filing discovery."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ..config import SEBI_BASE, SRC_FILING
from .base import BaseConnector, DataPoint

log = logging.getLogger(__name__)


class SEBIConnector(BaseConnector):
    name = "sebi"
    kind = "filing"

    def fetch_filings_index(self, company: str) -> DataPoint:
        url = f"{SEBI_BASE}/sebiweb/home/HomeAction.do?doListing=yes&sid=3&ssid=15&smid=12"
        return DataPoint(
            value={"company": company, "filings_index": url,
                   "note": "SEBI DIPAM offer-document index; fetch the actual "
                           "DRHP/RHP PDF URL and store it on the IPO record."},
            source=SRC_FILING, source_url=url,
            observed_at=datetime.now(timezone.utc), data_type="filings_index")

    def download_document(self, url: str, dest_path: str) -> DataPoint:
        try:
            with httpx.Client(timeout=60, follow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0"}) as c:
                with c.stream("GET", url) as r:
                    r.raise_for_status()
                    with open(dest_path, "wb") as fh:
                        for chunk in r.iter_bytes():
                            fh.write(chunk)
            return DataPoint(value={"local_path": dest_path}, source=SRC_FILING,
                             source_url=url,
                             observed_at=datetime.now(timezone.utc),
                             data_type="document")
        except Exception as e:
            log.warning("Document download failed %s: %s", url, e)
            return DataPoint(value=None, source=SRC_FILING, source_url=url,
                             data_type="document")
