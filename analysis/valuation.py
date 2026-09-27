"""Valuation engine (§4): IPO multiples at issue price + peer comparison."""
from __future__ import annotations

from statistics import median


def ipo_valuation(issue_price: float | None, post_shares_cr: float | None,
                  fy: dict) -> dict:
    """fy keys: revenue_cr, ebitda_cr, pat_cr, net_worth_cr, total_debt_cr,
    cash_cr, diluted_eps."""
    out: dict = {"inputs": {"issue_price": issue_price,
                            "post_shares_cr": post_shares_cr}}
    if issue_price is None or post_shares_cr in (None, 0):
        out["error"] = "Missing issue price or post-IPO shares"
        return out
    mcap = issue_price * post_shares_cr
    out["market_cap_cr"] = round(mcap, 2)
    debt = fy.get("total_debt_cr") or 0
    cash = fy.get("cash_cr") or 0
    out["enterprise_value_cr"] = round(mcap + debt - cash, 2)
    rev, ebitda, pat = fy.get("revenue_cr"), fy.get("ebitda_cr"), fy.get("pat_cr")
    nw = fy.get("net_worth_cr")
    eps = fy.get("diluted_eps") or fy.get("eps")
    if not eps and pat and post_shares_cr:
        # Fallback EPS from latest PAT / post-issue shares (labelled estimate
        # only when no reported EPS exists; never overrides a filing figure).
        eps = pat / post_shares_cr
        out["eps_source"] = "computed PAT/post-shares (no reported EPS)"
    ev = out["enterprise_value_cr"]
    out["pe"] = round(issue_price / eps, 2) if eps else None
    out["ps"] = round(mcap / rev, 2) if rev else None
    out["ev_ebitda"] = round(ev / ebitda, 2) if ebitda else None
    out["ev_sales"] = round(ev / rev, 2) if rev else None
    out["pb"] = round(mcap / nw, 2) if nw else None
    # PEG needs growth; caller passes pat_cagr optionally
    g = fy.get("pat_cagr")
    out["peg"] = round(out["pe"] / g, 2) if out["pe"] and g else None
    out["roe"] = fy.get("roe")
    out["roce"] = fy.get("roce")
    return out


def vs_peers(ipo_mults: dict, peers: list[dict]) -> dict:
    """Compare IPO multiples vs peer median; premium/discount %."""
    out: dict = {"n_peers": len(peers)}
    for key in ("pe", "ev_ebitda", "ps", "pb"):
        vals = [p[key] for p in peers if p.get(key) is not None]
        if not vals or ipo_mults.get(key) is None:
            out[key] = {"peer_median": None, "premium_discount_pct": None}
            continue
        med = median(vals)
        prem = round((ipo_mults[key] - med) / med * 100, 1) if med else None
        out[key] = {"ipo": ipo_mults[key], "peer_median": round(med, 2),
                    "premium_discount_pct": prem}
    out["verdict"] = _verdict(out)
    return out


def _verdict(cmp: dict) -> str:
    pe = (cmp.get("pe") or {}).get("premium_discount_pct")
    if pe is None:
        return "Data unavailable — insufficient peer multiples"
    if pe > 30:
        return f"Priced at {pe}% premium to peers — demands superior growth/returns"
    if pe < -20:
        return f"Priced at {abs(pe)}% discount to peers — valuation comfort"
    return f"Roughly in line with peers ({pe:+.1f}%)"
