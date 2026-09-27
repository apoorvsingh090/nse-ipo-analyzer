"""Feature builder with explicit timestamps (§12 anti-leakage).

Allowed (pre-listing only): IPO price, RHP financials, pre-listing GMP,
pre-close subscription, pre-listing market data.
FORBIDDEN: listing price, post-listing returns/news/subscription revisions.

Every feature carries `feature_timestamp` = when the info was knowable.
"""
from __future__ import annotations

from datetime import datetime, timezone

FEATURES = ["pe", "ev_ebitda", "rev_cagr", "pat_cagr", "roe", "roce",
            "debt_equity", "issue_size_cr", "ofs_pct", "fresh_pct",
            "val_premium", "qib_x", "nii_x", "retail_x", "total_x",
            "anchor_pct", "gmp_pct", "gmp_slope", "nifty_5d", "vix",
            "recent_gain", "recent_sub"]

FORBIDDEN = {"listing_price", "listing_gain", "post_return", "post_news",
             "listing_price_actual", "ret_1w", "ret_1m"}


def build_features(record: dict, asof: datetime | None = None) -> dict:
    """record: merged pre-listing observables. Raises on forbidden keys."""
    for k in record:
        if k.lower() in FORBIDDEN:
            raise ValueError(f"Leakage: forbidden feature '{k}'")
    asof = asof or datetime.now(timezone.utc)
    feats: dict = {}
    for f in FEATURES:
        v = record.get(f)
        try:
            v = None if v is None else float(v)
        except Exception:
            v = None
        feats[f] = {"value": v, "feature_timestamp": asof.isoformat(),
                    "source": record.get(f"{f}_source", "model-input")}
    return feats


def to_vector(feats: dict, medians: dict | None = None) -> list[float]:
    medians = medians or {}
    vec = []
    for f in FEATURES:
        v = (feats.get(f) or {}).get("value", None)
        if v is None:
            v = medians.get(f, 0.0)
        vec.append(float(v))
    return vec
