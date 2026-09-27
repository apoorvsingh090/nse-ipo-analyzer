"""Subscription (§8), anchor (§9), GMP (§10) analytics."""
from __future__ import annotations


def subscription_table(snaps: list[dict]) -> dict:
    """Latest snapshot + day progression + velocity. Never equates subs to gains."""
    if not snaps:
        return {"latest": None, "progression": [],
                "note": "Data unavailable"}
    ordered = sorted(snaps, key=lambda s: s.get("snapshot_at") or "")
    latest = ordered[-1]
    prog = [{"at": s.get("snapshot_at"), "day": s.get("day_label"),
             "retail": s.get("retail_x"), "nii": s.get("nii_x"),
             "qib": s.get("qib_x"), "total": s.get("total_x")} for s in ordered]
    velocity = None
    if len(ordered) >= 2 and ordered[-2].get("total_x") is not None \
            and latest.get("total_x") is not None:
        velocity = round(latest["total_x"] - ordered[-2]["total_x"], 2)
    verdict = []
    q, n, r = latest.get("qib_x"), latest.get("nii_x"), latest.get("retail_x")
    if q is not None and q >= 10:
        verdict.append("Strong QIB demand (institutional validation).")
    if q is not None and q < 1 and latest.get("day_label") == "Final":
        verdict.append("Weak QIB response — institutional caution.")
    if n is not None and n >= 20:
        verdict.append("Very strong HNI/NII demand (often leveraged bids).")
    if r is not None and r >= 5:
        verdict.append("Strong retail demand.")
    verdict.append("Subscription multiples measure demand, not listing gains.")
    return {"latest": latest, "progression": prog,
            "velocity_total_x": velocity, "verdict": verdict}


def anchor_summary(anchors: list[dict], issue_size_cr: float | None) -> dict:
    total = sum(a.get("amount_cr") or 0 for a in anchors)
    cats: dict[str, float] = {}
    for a in anchors:
        cats[a.get("category") or "Other"] = cats.get(a.get("category") or "Other", 0) + \
            (a.get("amount_cr") or 0)
    pct = round(total / issue_size_cr * 100, 1) if issue_size_cr else None
    majors = sorted(anchors, key=lambda a: a.get("amount_cr") or 0, reverse=True)[:10]
    return {"n_anchors": len(anchors), "total_cr": round(total, 2),
            "pct_of_issue": pct, "by_category_cr": cats,
            "top_anchors": [{"name": a.get("investor_name"),
                             "category": a.get("category"),
                             "amount_cr": a.get("amount_cr")} for a in majors],
            "note": "Investor quality is not inferred from brand alone."}


def gmp_assessment(gmp_rows: list[dict], ipo_price: float | None) -> dict:
    from ..connectors.gmp import (GMP_DISCLAIMER, compute_gmp_momentum,
                                  implied_listing)
    if not gmp_rows:
        return {"status": "Data unavailable", "disclaimer": GMP_DISCLAIMER,
                "source_kind": "Unofficial GMP"}
    last = gmp_rows[-1]
    g = last.get("gmp")
    impl = implied_listing(ipo_price, g)
    mom = compute_gmp_momentum([{"gmp": r.get("gmp"), "date": r.get("observed_at")}
                                for r in gmp_rows])
    hist = [{"at": r.get("observed_at"), "gmp": r.get("gmp")} for r in gmp_rows]
    return {"latest_gmp": g, "history": hist,
            "implied_listing_price": impl["implied_listing_price"],
            "gmp_pct": impl["gmp_pct"], "momentum": mom.get("momentum"),
            "trend": mom.get("trend"), "slope_per_day": mom.get("slope_per_day"),
            "disclaimer": GMP_DISCLAIMER, "source_kind": "Unofficial GMP"}
