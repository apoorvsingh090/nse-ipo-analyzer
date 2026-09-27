"""Recommendation logic (§14): structured evidence for/against, no hidden verdict.

Six pillars: Fundamentals, Valuation, IPO structure, Demand,
Market environment, Risk factors.
"""
from __future__ import annotations


def build_assessment(ctx: dict) -> dict:
    pillars: dict[str, dict] = {}
    for_evidence: list[str] = []
    against_evidence: list[str] = []

    def pillar(name, score, summary, facts):
        pillars[name] = {"score": score, "summary": summary, "facts": facts}

    fq = ctx.get("financial_quality") or {}
    q_total = (fq.get("total") if isinstance(fq, dict) else None)
    if q_total is not None:
        pillar("Fundamentals",
               "Strong" if q_total >= 65 else "Mixed" if q_total >= 45 else "Weak",
               f"Financial-quality total {q_total}/100 (components exposed).",
               fq.get("components", {}))
        (for_evidence if q_total >= 55 else against_evidence).append(
            f"Financial quality {q_total}/100 with evidence in components.")
    else:
        pillar("Fundamentals", "Unknown", "Insufficient financials.",
               {"note": "Data unavailable"})

    vd = ctx.get("valuation_vs_peers") or {}
    pe = ((vd.get("pe") or {}).get("premium_discount_pct"))
    if pe is not None:
        pillar("Valuation", "Expensive" if pe > 30 else "Fair" if pe > -20 else "Cheap",
               vd.get("verdict", ""), vd)
        (against_evidence if pe > 30 else for_evidence).append(
            f"IPO P/E premium/discount vs peers: {pe:+.1f}%.")
    else:
        pillar("Valuation", "Unknown", "Peer comparison unavailable.",
               {"note": "Data unavailable"})

    st = ctx.get("structure") or {}
    ofs = st.get("ofs_pct")
    pillar("IPO structure",
           "OFS-heavy" if (ofs or 0) >= 70 else "Balanced",
           f"Fresh {st.get('fresh_pct')}%, OFS {ofs}%.", st)
    if (ofs or 0) >= 70:
        against_evidence.append(f"OFS-heavy issue ({ofs}%): mostly an exit.")
    elif st.get("fresh_pct") and st["fresh_pct"] >= 50:
        for_evidence.append(f"Fresh-issue heavy ({st['fresh_pct']}%): funds the company.")

    dem = ctx.get("demand") or {}
    lat = (dem.get("latest") or {})
    tot = lat.get("total_x")
    pillar("Demand", "Strong" if (tot or 0) >= 10 else "Moderate" if (tot or 0) >= 2 else "Weak",
           f"Total subscription {tot}x; QIB {lat.get('qib_x')}x, "
           f"NII {lat.get('nii_x')}x, Retail {lat.get('retail_x')}x.", dem)
    if (tot or 0) >= 10:
        for_evidence.append(f"Strong demand: total subscription {tot}x.")
    elif tot is not None and tot < 1:
        against_evidence.append(f"Weak demand: total subscription {tot}x.")

    mkt = ctx.get("market") or {}
    pillar("Market environment", mkt.get("regime", "Unknown"),
           str(mkt), mkt)

    risks = ctx.get("risks") or []
    reds = ctx.get("red_flags") or []
    pillar("Risk factors",
           "Elevated" if len(reds) >= 3 else "Moderate" if reds or len(risks) > 5 else "Contained",
           f"{len(risks)} risks extracted, {len(reds)} potential red flags.", {
               "n_risks": len(risks), "n_red_flags": len(reds),
               "top": [r.get("description", "")[:160] for r in risks[:5]]})
    for r in reds[:5]:
        against_evidence.append(f"Red flag ({r['rule']}): {r['evidence'][:140]}")

    g = ctx.get("gmp") or {}
    if g.get("latest_gmp") is not None:
        trend = g.get("momentum") or "single snapshot — trend needs history"
        for_evidence.append(
            f"GMP ₹{g['latest_gmp']} ({trend}) — unofficial sentiment only.")

    return {"pillars": pillars,
            "evidence_for": for_evidence,
            "evidence_against": against_evidence,
            "note": "Structured evidence for your own decision; no automated BUY/SELL."}
