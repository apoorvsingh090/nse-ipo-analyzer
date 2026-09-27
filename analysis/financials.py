"""Financial-quality engine (§5): growth, profitability, cash conversion,
balance-sheet. Deterministic; exposes components, never hides behind one score."""
from __future__ import annotations


def cagr(start: float | None, end: float | None, years: int) -> float | None:
    if start is None or end is None or years <= 0:
        return None
    if start <= 0 or end <= 0:
        return None
    return round(((end / start) ** (1 / years) - 1) * 100, 2)


def analyze_growth(series: dict[str, float | None],
                   label: str = "") -> dict:
    """series: {FY22: x, FY23: y, FY24: z} chronological."""
    yrs = sorted(series.keys())
    vals = [series[y] for y in yrs]
    out: dict = {"label": label, "years": yrs, "values": vals}
    if len(vals) >= 3 and all(v is not None for v in vals):
        out["cagr_3y_pct"] = cagr(vals[-3], vals[-1], 2)
    elif len(vals) >= 2 and vals[-2] and vals[-1] is not None:
        out["cagr_3y_pct"] = None
    else:
        out["cagr_3y_pct"] = None
    if len(vals) >= 2 and vals[-2] not in (None, 0) and vals[-1] is not None:
        out["latest_yoy_pct"] = round((vals[-1] - vals[-2]) / abs(vals[-2]) * 100, 2)
    else:
        out["latest_yoy_pct"] = None
    return out


def cash_conversion_flags(ocf: dict[str, float | None],
                          pat: dict[str, float | None]) -> list[str]:
    flags: list[str] = []
    for fy in sorted(set(ocf) & set(pat)):
        o, p = ocf[fy], pat[fy]
        if o is None or p in (None, 0):
            continue
        ratio = o / p
        if p > 0 and o < 0:
            flags.append(f"{fy}: PAT positive (₹{p} cr) but OCF negative "
                         f"(₹{o} cr) — cash not converting.")
        elif ratio < 0.6:
            flags.append(f"{fy}: OCF/PAT = {ratio:.2f} — weak cash conversion.")
    # trend divergence
    fys = sorted(set(ocf) & set(pat))
    if len(fys) >= 2:
        o0, o1 = ocf[fys[-2]], ocf[fys[-1]]
        p0, p1 = pat[fys[-2]], pat[fys[-1]]
        if None not in (o0, o1, p0, p1) and p1 > p0 and o1 < o0:
            flags.append("PAT rising while OCF falling — potential red flag, "
                         "check receivables/inventory.")
    return flags


def financial_quality_score(g: dict) -> dict:
    """Transparent component scores (0-100 each) + weighted total.

    g keys: rev_cagr, pat_cagr, ebitda_margin, pat_margin, roe, roce,
    ocf_pat, debt_equity, interest_coverage. Missing -> component None
    and excluded from weighting (reported explicitly).
    """
    def band(v, lo, hi):
        if v is None:
            return None
        if v <= lo:
            return 20.0
        if v >= hi:
            return 90.0
        return round(20 + 70 * (v - lo) / (hi - lo), 1)

    de = g.get("debt_equity")
    comps = {
        "growth": band(g.get("rev_cagr"), 0, 30),
        "profitability": band(g.get("pat_margin"), 0, 20),
        "returns": band(g.get("roe"), 0, 25),
        "cash_conversion": band(g.get("ocf_pat"), 0.3, 1.2),
        # Missing debt data must stay missing: never coerce None -> 0,
        # which would score phantom "zero leverage" as 90/100.
        "leverage": band(-de, -2.0, 0.0) if de is not None else None,
    }
    weights = {"growth": 0.25, "profitability": 0.25, "returns": 0.2,
               "cash_conversion": 0.15, "leverage": 0.15}
    num = sum(comps[k] * weights[k] for k in comps if comps[k] is not None)
    den = sum(weights[k] for k in comps if comps[k] is not None)
    return {"components": comps, "weights": weights,
            "total": round(num / den, 1) if den else None,
            "note": "Components exposed individually; total is indicative only."}
