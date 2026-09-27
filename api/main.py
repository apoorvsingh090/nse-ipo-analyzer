"""FastAPI backend (§24). Serves API + dashboard. Run:
    uvicorn nse_ipo_analyzer.api.main:app --reload
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import DATA_UNAVAILABLE, MODEL_DIR
from ..database import (IPO, IPOAnchor, IPODocument, IPOFinancial, IPOGMP,
                        IPOMarketData, IPOPrediction, IPORisk, IPOSubscription,
                        IPOValuation, Peer, get_session_factory, init_db)
from .service import build_report, llm_summary, persist_prediction

log = logging.getLogger(__name__)

HIST_CSV = Path(__file__).resolve().parent.parent / "data" / "historical_ipos.csv"


def train_from_history() -> dict:
    """Train listing model on bundled history + walk-forward backtest."""
    from ..ml.features import FEATURES
    from ..ml.train import backtest_report, train_final
    df = pd.read_csv(HIST_CSV, parse_dates=["listing_date"])
    df["ofs_pct"] = df["ofs_cr"] / df["issue_size_cr"] * 100
    df["fresh_pct"] = df["fresh_issue_cr"] / df["issue_size_cr"] * 100
    df["gmp_slope"] = 0.0
    df["debt_equity"] = df["debt_equity"].fillna(0.5)
    for c in FEATURES:
        if c not in df.columns:
            df[c] = 0.0
    meta = train_final(df)
    rep = backtest_report(df)
    (MODEL_DIR / "backtest.json").write_text(json.dumps(rep, indent=2, default=str))
    return {"meta": meta, "rep": rep}


def ensure_bootstrapped() -> dict:
    """Seed empty DB + train missing model. For ephemeral free-tier disks."""
    init_db()
    s = get_session_factory()()
    seeded = False
    try:
        if s.query(IPO).count() == 0:
            from ..scripts.seed import seed, seed_example
            seed()
            seed_example()
            seeded = True
    finally:
        s.close()
    trained = False
    if not (MODEL_DIR / "meta.json").exists():
        train_from_history()
        trained = True
    return {"seeded": seeded, "trained": trained}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("AUTO_SEED", "1") == "1":
        try:
            log.info("bootstrap: %s", ensure_bootstrapped())
        except Exception as e:  # never block startup on bootstrap failure
            log.warning("bootstrap failed: %s", e)
    yield


app = FastAPI(title="NSE IPO Analyzer", version="1.2.0", lifespan=lifespan)
FRONT = Path(__file__).resolve().parent.parent / "frontend"


def _sess():
    init_db()
    return get_session_factory()()


def _row(obj) -> dict:
    d = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        if isinstance(v, datetime):
            v = v.isoformat()
        elif hasattr(v, "isoformat"):
            try:
                v = v.isoformat()
            except Exception:
                pass
        d[c.name] = v
    return d


@app.get("/health")
def health():
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}


@app.get("/ipos")
def list_ipos(status: str | None = None, segment: str | None = None):
    s = _sess()
    try:
        q = s.query(IPO)
        if status:
            q = q.filter_by(status=status)
        if segment:
            q = q.filter_by(segment=segment)
        return [_row(r) for r in q.order_by(IPO.id.desc()).all()]
    finally:
        s.close()


@app.get("/ipos/{ipo_id}")
def get_ipo(ipo_id: int):
    s = _sess()
    try:
        r = s.query(IPO).filter_by(id=ipo_id).first()
        if not r:
            raise HTTPException(404, "IPO not found")
        return _row(r)
    finally:
        s.close()


@app.get("/ipos/{ipo_id}/financials")
def get_financials(ipo_id: int):
    s = _sess()
    try:
        rows = s.query(IPOFinancial).filter_by(ipo_id=ipo_id).order_by(
            IPOFinancial.fiscal_year).all()
        if not rows:
            return {"data": [], "note": DATA_UNAVAILABLE}
        return {"data": [_row(r) for r in rows],
                "source": "Company/SEBI filing"}
    finally:
        s.close()


@app.get("/ipos/{ipo_id}/valuation")
def get_valuation(ipo_id: int):
    rep = build_report(ipo_id)
    if "error" in rep:
        raise HTTPException(404, rep["error"])
    return {"valuation": rep["valuation"],
            "vs_peers": rep["valuation_vs_peers"],
            "peers": rep.get("peers", [])}


@app.get("/ipos/{ipo_id}/subscription")
def get_subscription(ipo_id: int):
    rep = build_report(ipo_id)
    if "error" in rep:
        raise HTTPException(404, rep["error"])
    return rep["demand"]


@app.get("/ipos/{ipo_id}/gmp")
def get_gmp(ipo_id: int):
    rep = build_report(ipo_id)
    if "error" in rep:
        raise HTTPException(404, rep["error"])
    return rep["gmp"]


@app.get("/ipos/{ipo_id}/prediction")
def get_prediction(ipo_id: int):
    rep = build_report(ipo_id)
    if "error" in rep:
        raise HTTPException(404, rep["error"])
    return rep["prediction"]


@app.get("/ipos/{ipo_id}/risks")
def get_risks(ipo_id: int):
    rep = build_report(ipo_id)
    if "error" in rep:
        raise HTTPException(404, rep["error"])
    return {"risks": rep["risks"], "red_flags": rep["red_flags"]}


@app.get("/ipos/{ipo_id}/sources")
def get_sources(ipo_id: int):
    s = _sess()
    try:
        docs = s.query(IPODocument).filter_by(ipo_id=ipo_id).all()
        fins = s.query(IPOFinancial).filter_by(ipo_id=ipo_id).all()
        prov = []
        for f in fins:
            prov.append({"metric": "financials", "year": f.fiscal_year,
                         "source": f.source, "doc": f.source_doc,
                         "page": f.source_page})
        return {"documents": [_row(d) for d in docs],
                "provenance": prov,
                "note": "Every important number is traceable (§26)."}
    finally:
        s.close()


@app.get("/ipos/{ipo_id}/history")
def get_history(ipo_id: int):
    s = _sess()
    try:
        preds = s.query(IPOPrediction).filter_by(ipo_id=ipo_id).order_by(
            IPOPrediction.predicted_at).all()
        return {"predictions": [_row(p) for p in preds],
                "note": "Every prediction timestamped (§23)."}
    finally:
        s.close()


class AnalyzeOut(BaseModel):
    ok: bool = True


@app.post("/ipos/{ipo_id}/analyze")
def analyze(ipo_id: int):
    rep = build_report(ipo_id)
    if "error" in rep:
        raise HTTPException(404, rep["error"])
    pid = persist_prediction(ipo_id, rep)
    rep["persisted_prediction_id"] = pid
    rep["narrative"] = llm_summary(rep)
    return rep


@app.post("/ipos/{ipo_id}/refresh")
def refresh(ipo_id: int):
    """Re-fetch live connectors (NSE/BSE/market), store snapshots, re-analyze."""
    from ..connectors.bse import BSEConnector
    from ..connectors.market import fetch_market_snapshot
    from ..connectors.nse import NSEConnector
    s = _sess()
    try:
        ipo = s.query(IPO).filter_by(id=ipo_id).first()
        if not ipo:
            raise HTTPException(404, "IPO not found")
        nse = NSEConnector().fetch_subscription(ipo.symbol or ipo.company_name)
        fetched = {"nse": nse.to_dict(),
                   "bse": BSEConnector().fetch_subscription().to_dict(),
                   "market": fetch_market_snapshot().to_dict()}
        s.add(IPODocument(ipo_id=ipo_id, doc_type="RefreshLog",
                          parse_status="ok",
                          parse_log=json.dumps(fetched, default=str)[:4000]))
        s.commit()
    finally:
        s.close()
    rep = build_report(ipo_id)
    rep["refreshed"] = True
    return rep


@app.get("/models/performance")
def model_performance():
    from ..config import MODEL_DIR
    meta_p = MODEL_DIR / "meta.json"
    if not meta_p.exists():
        return {"status": "untrained",
                "hint": "POST /models/train to train on historical IPOs."}
    return json.loads(meta_p.read_text())


@app.post("/models/train")
def train_model():
    out = train_from_history()
    rep = out["rep"]
    return {"meta": out["meta"], "walk_forward": rep.get("walk_forward"),
            "segments": {k: v for k, v in rep.items() if k in ("mainboard", "sme", "all")}}


@app.get("/models/backtest")
def backtest():
    from ..config import MODEL_DIR
    p = MODEL_DIR / "backtest.json"
    if not p.exists():
        raise HTTPException(404, "No backtest yet — POST /models/train first.")
    return json.loads(p.read_text())


# ---- live upcoming IPOs (real NSE data) ----
@app.get("/live/upcoming")
def live_upcoming(enrich: bool = True):
    from .live import preview_live
    return preview_live(enrich=enrich)


@app.get("/live/gmp")
def live_gmp():
    from .live import preview_gmp
    return preview_gmp()


class ImportReq(BaseModel):
    symbol: str | None = None
    company: str | None = None
    enrich: bool = True
    gmp: bool = True  # live GMP via Playwright; fail-soft, slower


@app.post("/ipos/import")
def import_ipo(req: ImportReq):
    from .live import import_live
    if not req.symbol and not req.company:
        raise HTTPException(422, "Provide symbol or company.")
    res = import_live(symbol=req.symbol, company=req.company,
                      enrich=req.enrich, gmp=req.gmp)
    if "error" in res and "ipo_id" not in res:
        raise HTTPException(502, res["error"])
    return res


# ---- frontend ----
if FRONT.exists():
    app.mount("/static", StaticFiles(directory=str(FRONT)), name="static")


@app.get("/", include_in_schema=False)
def index():
    idx = FRONT / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return JSONResponse({"msg": "API running. Frontend not built yet."})
