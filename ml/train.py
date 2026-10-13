"""Model training with walk-forward validation (§11, §21).

Models: LinearRegression, RandomForest, GradientBoosting (+quantile
regressors for intervals). NEVER shuffles across time; expanding-window
walk-forward only. SME and mainboard evaluated separately.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import (GradientBoostingRegressor, RandomForestRegressor)
from sklearn.linear_model import LinearRegression, QuantileRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from ..config import MODEL_DIR
from .features import FEATURES

log = logging.getLogger(__name__)


def _metrics(y, p) -> dict:
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    rmse = float(np.sqrt(mean_squared_error(y, p)))
    return {"mae": round(float(mean_absolute_error(y, p)), 3),
            "rmse": round(rmse, 3),
            "r2": round(float(r2_score(y, p)) if len(y) > 2 else 0.0, 3),
            "dir_acc": round(float(np.mean(np.sign(y) == np.sign(p))), 3),
            "n": len(y)}


def walk_forward(df: pd.DataFrame, target: str = "listing_gain_pct",
                 min_train: int = 15, step: int = 5) -> dict:
    """Expanding-window evaluation sorted by listing_date.

    Imputation medians come from the train fold only — full-sample
    statistics would leak test-fold information into training.
    """
    df = df.sort_values("listing_date").reset_index(drop=True)
    feats = df[FEATURES]
    y = df[target].values
    preds = {"linear": [], "rf": [], "gbr": []}
    idx = []
    for end in range(min_train, len(df), step):
        tr, te = slice(0, end), slice(end, min(end + step, len(df)))
        if te.stop - te.start == 0:
            break
        med = feats.iloc[tr].median()
        Xtr = feats.iloc[tr].fillna(med).values
        Xte = feats.iloc[te].fillna(med).values
        m1 = LinearRegression().fit(Xtr, y[tr])
        m2 = RandomForestRegressor(n_estimators=200, min_samples_leaf=3,
                                   random_state=7, n_jobs=-1).fit(Xtr, y[tr])
        m3 = GradientBoostingRegressor(random_state=7).fit(Xtr, y[tr])
        preds["linear"].extend(m1.predict(Xte))
        preds["rf"].extend(m2.predict(Xte))
        preds["gbr"].extend(m3.predict(Xte))
        idx.extend(range(te.start, te.stop))
    yt = y[idx]
    return {m: {"idx": idx, **_metrics(yt, preds[m])} for m in preds}


def train_final(df: pd.DataFrame, target: str = "listing_gain_pct",
                out_dir: Path | None = None) -> dict:
    out_dir = out_dir or MODEL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    df = df.sort_values("listing_date").reset_index(drop=True)
    med = df[FEATURES].median().to_dict()
    X = df[FEATURES].fillna(med).values
    y = df[target].values
    models = {
        "linear": LinearRegression().fit(X, y),
        "rf": RandomForestRegressor(n_estimators=300, min_samples_leaf=2,
                                    random_state=7, n_jobs=-1).fit(X, y),
        "gbr": GradientBoostingRegressor(random_state=7).fit(X, y),
        "q10": GradientBoostingRegressor(loss="quantile", alpha=0.1,
                                         random_state=7).fit(X, y),
        "q90": GradientBoostingRegressor(loss="quantile", alpha=0.9,
                                         random_state=7).fit(X, y),
    }
    for k, m in models.items():
        joblib.dump(m, out_dir / f"{k}.pkl")
    means = {f: float(np.mean(X[:, i])) for i, f in enumerate(FEATURES)}
    coefs = {}
    if hasattr(models["linear"], "coef_"):
        coefs = {f: float(c) for f, c in zip(FEATURES, models["linear"].coef_)}
    meta = {"features": FEATURES, "medians": {k: float(v) for k, v in med.items()},
            "means": means, "linear_coefs": coefs,
            "intercept": float(models["linear"].intercept_),
            "n_train": len(df),
            "target": f"Listing Return = (Listing Price / IPO Price) - 1 (as %)",
            "version": "v1"}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def backtest_report(df: pd.DataFrame) -> dict:
    """MAE/RMSE/R²/directional accuracy + interval calibration, split by segment."""
    rep: dict = {"walk_forward": walk_forward(df)}
    for seg in ("mainboard", "sme"):
        sub = df[df["segment"] == seg]
        rep[seg] = walk_forward(sub) if len(sub) >= 20 else {"note": "insufficient data"}
    rep["all"] = walk_forward(df)
    return rep
