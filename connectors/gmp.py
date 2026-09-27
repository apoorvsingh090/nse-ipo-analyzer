"""GMP connector — UNOFFICIAL sentiment only (§10).

GMP is unregulated and never official exchange data. This module reuses the
proven multibagg.ai + investorgain parsing logic (see /ipo.py at repo root)
and always labels results `Unofficial GMP`. Momentum (slope/trend) is
computed alongside the latest value.
"""
from __future__ import annotations

import logging
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ..config import SRC_GMP

log = logging.getLogger(__name__)

try:
    from ipo import (  # reuse battle-tested parsers from existing ipo.py
        _est_gain, _linfit, parse_investorgain, parse_multibagg,
    )
    _IPO_PY = True
except Exception as e:  # pragma: no cover
    log.warning("Could not import ipo.py parsers: %s", e)
    _IPO_PY = False


def compute_gmp_momentum(series: list[dict]) -> dict:
    """Momentum classification: increasing / stable / declining / negative."""
    if not _IPO_PY or not series:
        return {"trend": "Data unavailable", "slope_per_day": None,
                "momentum": "Data unavailable", "source_kind": SRC_GMP}
    slope, trend, n = _linfit(series)
    if slope is None:
        return {"trend": "Data unavailable", "slope_per_day": None,
                "momentum": "Data unavailable", "source_kind": SRC_GMP}
    if slope > 0:
        momentum = "GMP increasing"
    elif slope < 0:
        momentum = "GMP declining"
    else:
        momentum = "GMP stable"
    last = series[-1].get("gmp")
    if isinstance(last, (int, float)) and last < 0:
        momentum = "GMP turning negative"
    return {"trend": trend, "slope_per_day": slope, "n_points": n,
            "momentum": momentum, "source_kind": SRC_GMP}


def implied_listing(ipo_price: float | None, gmp: float | None) -> dict:
    if ipo_price is None or gmp is None:
        return {"implied_listing_price": None, "gmp_pct": None,
                "disclaimer": "GMP is an unofficial, unregulated market indicator "
                              "and is not a guaranteed listing price.",
                "source_kind": SRC_GMP}
    imp = ipo_price + gmp
    return {"implied_listing_price": round(imp, 2),
            "gmp_pct": round(gmp / ipo_price * 100, 2) if ipo_price else None,
            "disclaimer": "GMP is an unofficial, unregulated market indicator "
                          "and is not a guaranteed listing price.",
            "source_kind": SRC_GMP}


def fetch_gmp_snapshot(multibagg_html: str = "", investorgain_html: str = "") -> list[dict]:
    """Parse provided HTML snapshots (live fetching lives in ipo.py)."""
    out: list[dict] = []
    if not _IPO_PY:
        return out
    if multibagg_html:
        for ip in parse_multibagg(multibagg_html):
            slope, trend, _ = _linfit(ip.get("gmp_series", []))
            out.append({"company": ip.get("company"), "symbol": ip.get("symbol"),
                        "gmp": ip.get("gmp"), "gmp_series": ip.get("gmp_series"),
                        "est_gain_pct": _est_gain(ip), "trend": trend,
                        "slope": slope, "source_kind": SRC_GMP})
    return out


GMP_DISCLAIMER = ("GMP is an unofficial, unregulated market indicator "
                  "and is not a guaranteed listing price.")
