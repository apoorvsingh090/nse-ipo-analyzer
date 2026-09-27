"""Anti-leakage guards (§12) + backtest helpers (§21)."""
from __future__ import annotations

from datetime import datetime

from .features import FORBIDDEN

LEAKAGE_RULES = (
    "Only pre-listing info. Listing price / post returns / post news forbidden. "
    "Walk-forward only; no shuffling across time."
)


def assert_no_leakage(feature_dict: dict, listing_date: datetime | None = None):
    bad = [k for k in feature_dict if str(k).lower() in FORBIDDEN]
    if bad:
        raise ValueError(f"Data leakage detected — forbidden features: {bad}")
    if listing_date:
        for k, v in feature_dict.items():
            ts = (v or {}).get("feature_timestamp") if isinstance(v, dict) else None
            if ts:
                try:
                    t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    ld = listing_date
                    if t.date() >= (ld.date() if hasattr(ld, "date") else ld):
                        raise ValueError(
                            f"Feature '{k}' timestamp {ts} not before listing {listing_date}")
                except ValueError as e:
                    if "not before listing" in str(e):
                        raise
    return True


def interval_calibration(y_true, lo, hi) -> dict:
    import numpy as np
    y = np.asarray(y_true, float)
    lo = np.asarray(lo, float)
    hi = np.asarray(hi, float)
    cov = float(np.mean((y >= lo) & (y <= hi)))
    return {"coverage_80pct_interval": round(cov, 3),
            "target": 0.8,
            "calibrated": abs(cov - 0.8) < 0.15}
