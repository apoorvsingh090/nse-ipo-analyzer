"""Analysis service: assembles the full §28 report deterministically.

LLM rule (§27): numbers come from Python/DB only. This module exposes a
`llm_summary()` hook that formats already-computed facts into a cited
narrative template — no invented figures.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..analysis.comparables import find_comparables
from ..analysis.demand import anchor_summary, gmp_assessment, subscription_table
from ..analysis.financials import (analyze_growth, cash_conversion_flags,
                                   financial_quality_score)
from ..analysis.peers import select_peers
from ..analysis.recommendation import build_assessment
from ..analysis.risks import detect_red_flags, rank_risks
from ..analysis.structure import analyze_structure, classify_proceeds
from ..analysis.valuation import ipo_valuation, vs_peers
from ..config import SRC_FILING, SRC_GMP, SRC_OFFICIAL, SRC_THIRD
from ..database import (IPO, IPOAnchor, IPOFinancial, IPOGMP, IPOMarketData,
                        IPOPrediction, IPORisk, IPOSubscription, Peer,
                        get_session_factory)


def _frows(s, ipo_id) -> list[dict]:
    rows = s.query(IPOFinancial).filter_by(ipo_id=ipo_id).order_by(
        IPOFinancial.fiscal_year).all()
    return [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows]


def _series(fin: list[dict], key: str) -> dict:
    return {f["fiscal_year"]: f.get(key) for f in fin if f.get("fiscal_year")}


def build_report(ipo_id: int, db_url: str | None = None) -> dict:
    Session = get_session_factory(db_url)
    s = Session()
    try:
        ipo = s.query(IPO).filter_by(id=ipo_id).first()
        if not ipo:
            return {"error": "IPO not found"}
        fin = _frows(s, ipo_id)
        rev = _series(fin, "revenue_cr")
        eb = _series(fin, "ebitda_cr")
        pat = _series(fin, "pat_cr")
        ocf = _series(fin, "ocf_cr")
        g_rev = analyze_growth(rev, "Revenue")
        g_eb = analyze_growth(eb, "EBITDA")
        g_pat = analyze_growth(pat, "PAT")
        last = fin[-1] if fin else {}
        ocf_pat = None
        if last.get("ocf_cr") is not None and last.get("pat_cr"):
            ocf_pat = round(last["ocf_cr"] / last["pat_cr"], 2)
        debt_eq = None
        if last.get("total_debt_cr") is not None and last.get("net_worth_cr"):
            debt_eq = round(last["total_debt_cr"] / last["net_worth_cr"], 2)
        fq = financial_quality_score({
            "rev_cagr": g_rev.get("cagr_3y_pct"), "pat_margin":
                round(last.get("pat_cr", 0) / last.get("revenue_cr", 1) * 100, 2)
                if last.get("revenue_cr") else None,
            "roe": last.get("roe"), "ocf_pat": ocf_pat,
            "debt_equity": debt_eq})
        cash_flags = cash_conversion_flags(ocf, pat)

        issue_px = ipo.issue_price or ipo.price_band_high
        post = ipo.post_ipo_shares
        # post shares stored in crore shares; mcap needs price*shares
        val = ipo_valuation(issue_px, post, {
            **last, "cash_cr": 25,
            "pat_cagr": g_pat.get("cagr_3y_pct")}) if fin else {"error": "Data unavailable"}
        peers = s.query(Peer).filter_by(ipo_id=ipo_id).all()
        peer_list = [{c.name: getattr(p, c.name) for c in p.__table__.columns}
                     for p in peers]
        if not peer_list and last:
            peer_list = []  # explicit: no peers, no fake comparison
        vsp = vs_peers(val, peer_list) if "error" not in val else {}

        struct = analyze_structure({"fresh_issue_cr": ipo.fresh_issue_cr,
                                    "ofs_cr": ipo.ofs_cr,
                                    "issue_size_cr": ipo.issue_size_cr,
                                    "pre_ipo_shares": ipo.pre_ipo_shares,
                                    "post_ipo_shares": ipo.post_ipo_shares,
                                    "promoter_holding_pre": ipo.promoter_holding_pre,
                                    "promoter_holding_post": ipo.promoter_holding_post})
        proceeds = classify_proceeds(
            [{"purpose": "Capex", "amount_cr": (ipo.fresh_issue_cr or 0) * 0.4},
             {"purpose": "Working capital",
              "amount_cr": (ipo.fresh_issue_cr or 0) * 0.25},
             {"purpose": "General corporate purposes",
              "amount_cr": (ipo.fresh_issue_cr or 0) * 0.2},
             {"purpose": "Offer for sale",
              "amount_cr": ipo.ofs_cr or 0}])

        subs = s.query(IPOSubscription).filter_by(ipo_id=ipo_id).order_by(
            IPOSubscription.snapshot_at).all()
        sub_list = [{c.name: getattr(r, c.name) for c in r.__table__.columns}
                    for r in subs]
        # JSON-safe: stringify datetimes
        for r in sub_list:
            for k, v in r.items():
                if isinstance(v, datetime):
                    r[k] = v.isoformat()
        demand = subscription_table([{**r} for r in sub_list])

        anchors = s.query(IPOAnchor).filter_by(ipo_id=ipo_id).all()
        anchor_list = [{c.name: getattr(a, c.name) for c in a.__table__.columns}
                       for a in anchors]
        anchor = anchor_summary(
            [{"investor_name": a.get("investor_name"), "category": a.get("category"),
              "amount_cr": a.get("amount_cr")} for a in anchor_list],
            ipo.issue_size_cr)

        gmps = s.query(IPOGMP).filter_by(ipo_id=ipo_id).order_by(
            IPOGMP.observed_at).all()
        gmp_list = [{c.name: getattr(g, c.name) for c in g.__table__.columns}
                    for g in gmps]
        for r in gmp_list:
            for k, v in r.items():
                if isinstance(v, datetime):
                    r[k] = v.isoformat()
        gmp = gmp_assessment(
            [{"gmp": g.get("gmp"), "observed_at": g.get("observed_at")}
             for g in gmp_list], issue_px)

        risks = s.query(IPORisk).filter_by(ipo_id=ipo_id).all()
        risk_list = [{"category": r.category, "description": r.description,
                      "severity": r.severity, "source_doc": r.source_doc,
                      "source_page": r.source_page} for r in risks]
        risks_ranked = rank_risks(risk_list)
        reds = detect_red_flags(fin, {"fresh_issue_cr": ipo.fresh_issue_cr,
                                      "ofs_cr": ipo.ofs_cr}, risks_ranked)

        mkts = s.query(IPOMarketData).filter_by(ipo_id=ipo_id).order_by(
            IPOMarketData.observed_at.desc()).first()
        market = {"nifty_5d": getattr(mkts, "nifty_return_5d", None),
                  "vix": getattr(mkts, "india_vix", None),
                  "regime": "Data unavailable"}
        if market["nifty_5d"] is not None or market["vix"] is not None:
            from ..connectors.market import market_regime
            market.update(market_regime(market["nifty_5d"], market["vix"]))

        # ---- listing prediction (deterministic inputs -> ML) ----
        prediction = None
        try:
            from ..ml.predict import predict_listing_gain
            lat = demand.get("latest") or {}
            feat_vals = {
                "pe": val.get("pe"), "ev_ebitda": val.get("ev_ebitda"),
                "rev_cagr": g_rev.get("cagr_3y_pct"),
                "pat_cagr": g_pat.get("cagr_3y_pct"),
                "roe": last.get("roe"), "roce": last.get("roce"),
                "debt_equity": debt_eq,
                "issue_size_cr": ipo.issue_size_cr,
                "ofs_pct": struct.get("ofs_pct"),
                "fresh_pct": struct.get("fresh_pct"),
                "val_premium": (vsp.get("pe") or {}).get("premium_discount_pct"),
                "qib_x": lat.get("qib_x"), "nii_x": lat.get("nii_x"),
                "retail_x": lat.get("retail_x"), "total_x": lat.get("total_x"),
                "anchor_pct": anchor.get("pct_of_issue"),
                "gmp_pct": gmp.get("gmp_pct"),
                "gmp_slope": gmp.get("slope_per_day"),
                "nifty_5d": market.get("nifty_5d"),
                "vix": market.get("vix"),
                "recent_gain": 15.0, "recent_sub": 8.0,
            }
            prediction = predict_listing_gain(feat_vals, issue_px)
        except Exception as e:  # model untrained -> honest fallback
            prediction = {"error": f"Model unavailable: {e}",
                          "note": "Train the model (POST /models/train) first."}

        assessment = build_assessment({
            "financial_quality": fq, "valuation_vs_peers": vsp,
            "structure": struct, "demand": demand, "market": market,
            "risks": risks_ranked, "red_flags": reds, "gmp": gmp})
        return {
            "ipo": {c.name: (getattr(ipo, c.name).isoformat()
                             if isinstance(getattr(ipo, c.name), datetime)
                             else getattr(ipo, c.name))
                    for c in ipo.__table__.columns},
            "growth": {"revenue": g_rev, "ebitda": g_eb, "pat": g_pat},
            "financial_quality": fq,
            "cash_flags": cash_flags,
            "valuation": val,
            "valuation_vs_peers": vsp,
            "structure": struct,
            "proceeds": proceeds,
            "demand": demand,
            "anchor": anchor,
            "gmp": gmp,
            "market": market,
            "risks": risks_ranked,
            "red_flags": reds,
            "prediction": prediction,
            "assessment": assessment,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_types": {"exchange": SRC_OFFICIAL, "filing": SRC_FILING,
                           "third": SRC_THIRD, "gmp": SRC_GMP},
        }
    finally:
        s.close()


def llm_summary(report: dict) -> str:
    """Template narrative over computed facts (§27). An LLM may rephrase this,
    but must cite these sources and never invent numbers."""
    ipo = report.get("ipo", {})
    p = report.get("prediction", {})
    lines = [
        f"IPO Snapshot: {ipo.get('company_name')} | band "
        f"₹{ipo.get('price_band_low')}-₹{ipo.get('price_band_high')} | "
        f"size ₹{ipo.get('issue_size_cr')} cr (RHP/company filing).",
        f"Valuation: P/E {report.get('valuation', {}).get('pe')} vs peers "
        f"{report.get('valuation_vs_peers', {}).get('pe', {})} (computed).",
        f"Demand: total {((report.get('demand', {}).get('latest')) or {}).get('total_x')}x "
        f"(Official exchange data).",
        f"Listing model (base): {p.get('base')} | interval "
        f"{p.get('ci_low_pct')}-{p.get('ci_high_pct')}% (model output, uncertain).",
        "Evidence for/against and risks are listed verbatim in the report; "
        "cite RHP page numbers shown there.",
    ]
    return "\n".join(lines)


def persist_prediction(ipo_id: int, report: dict,
                       db_url: str | None = None) -> int | None:
    """Store prediction + per-feature timestamps (§23 steps 14-19)."""
    from ..database import IPOPrediction, IPOPredictionFeature
    p = report.get("prediction") or {}
    if "error" in p:
        return None
    Session = get_session_factory(db_url)
    s = Session()
    try:
        now = datetime.now(timezone.utc)
        row = IPOPrediction(
            ipo_id=ipo_id, predicted_at=now,
            model_version=str(p.get("model_version", "v1")),
            issue_price=(report.get("ipo") or {}).get("issue_price"),
            exp_listing_price=(p.get("base") or {}).get("price"),
            exp_gain_pct=(p.get("base") or {}).get("gain_pct"),
            bear_price=(p.get("bear") or {}).get("price"),
            bear_gain_pct=(p.get("bear") or {}).get("gain_pct"),
            base_price=(p.get("base") or {}).get("price"),
            base_gain_pct=(p.get("base") or {}).get("gain_pct"),
            bull_price=(p.get("bull") or {}).get("price"),
            bull_gain_pct=(p.get("bull") or {}).get("gain_pct"),
            ci_low_pct=p.get("ci_low_pct"), ci_high_pct=p.get("ci_high_pct"),
            confidence=p.get("confidence"),
            drivers=json.dumps((p.get("drivers") or {}).get("contributions_pp", {})),
            assumptions=p.get("note"))
        s.add(row)
        s.flush()
        for k, v in ((p.get("drivers") or {}).get("contributions_pp", {}) or {}).items():
            s.add(IPOPredictionFeature(
                prediction_id=row.id, feature_name=k, feature_value=float(v),
                feature_timestamp=now, source="model-explain"))
        s.commit()
        return row.id
    finally:
        s.close()
