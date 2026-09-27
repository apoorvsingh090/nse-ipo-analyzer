"""Inference: bear/base/bull + interval + drivers (§11, §20)."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np

from ..config import MODEL_DIR
from .features import FEATURES, to_vector


def load_artifacts(model_dir: Path | None = None):
    model_dir = model_dir or MODEL_DIR
    meta = json.loads((model_dir / "meta.json").read_text())
    models = {}
    for k in ("linear", "rf", "gbr", "q10", "q90"):
        p = model_dir / f"{k}.pkl"
        models[k] = joblib.load(p) if p.exists() else None
    return models, meta


def predict_listing_gain(feat_values: dict[str, float | None],
                         issue_price: float | None,
                         model_dir: Path | None = None) -> dict:
    from ..analysis.explain import explain_linear
    models, meta = load_artifacts(model_dir)
    medians = meta["medians"]
    feats = {f: {"value": feat_values.get(f)} for f in FEATURES}
    vec = np.array([to_vector(feats, medians)])
    preds = {}
    for k, m in models.items():
        preds[k] = float(m.predict(vec)[0]) if m is not None else None
    cands = [p for p in (preds.get("rf"), preds.get("gbr"), preds.get("linear"))
             if p is not None]
    base = float(np.median(cands)) if cands else 0.0
    q10 = preds.get("q10")
    q90 = preds.get("q90")
    spread = max(8.0, abs((q90 or base + 10) - (q10 or base - 10)) / 2)
    bear_g = (q10 if q10 is not None else base - spread)
    bull_g = (q90 if q90 is not None else base + spread)

    def price(g):
        return round(issue_price * (1 + g / 100), 2) if issue_price else None

    drivers = explain_linear(meta.get("linear_coefs", {}), meta.get("means", {}),
                             {k: (feat_values.get(k) if feat_values.get(k) is not None
                                   else medians.get(k, 0)) for k in FEATURES})
    unc = spread
    conf = "High" if unc < 10 else "Medium" if unc < 20 else "Low"
    return {
        "expected_gain_pct": round(base, 2),
        "expected_listing_price": price(base),
        "bear": {"price": price(bear_g), "gain_pct": round(bear_g, 2)},
        "base": {"price": price(base), "gain_pct": round(base, 2)},
        "bull": {"price": price(bull_g), "gain_pct": round(bull_g, 2)},
        "ci_low_pct": round(bear_g, 2), "ci_high_pct": round(bull_g, 2),
        "confidence": conf,
        "drivers": drivers,
        "model_preds": {k: round(v, 2) if v is not None else None
                        for k, v in preds.items()},
        "model_version": meta.get("version", "v1"),
        "note": "Estimate with uncertainty — not a precise prediction.",
    }
