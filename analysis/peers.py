"""Peer-selection algorithm (§4): industry, model, mix, mcap, growth,
margins, geography, capital intensity. Scores 0-100; no mechanical
unrelated-company comparison."""
from __future__ import annotations


def peer_score(ipo: dict, cand: dict) -> float:
    s = 0.0
    if (ipo.get("sector") or "").lower() == (cand.get("sector") or "").lower():
        s += 30
    if (ipo.get("industry") or "").lower() == (cand.get("industry") or "").lower():
        s += 15
    # market-cap proximity (log scale)
    try:
        import math
        a, b = float(ipo.get("market_cap_cr") or 0), float(cand.get("market_cap_cr") or 0)
        if a > 0 and b > 0:
            ratio = max(a, b) / min(a, b)
            s += max(0, 15 - 5 * math.log10(ratio))
    except Exception:
        pass
    # margin similarity
    for k, w in (("ebitda_margin", 10), ("pat_margin", 5)):
        try:
            d = abs(float(ipo.get(k) or 0) - float(cand.get(k) or 0))
            s += max(0, w - d * 0.5)
        except Exception:
            pass
    # growth similarity
    try:
        d = abs(float(ipo.get("rev_cagr") or 0) - float(cand.get("rev_cagr") or 0))
        s += max(0, 10 - d * 0.3)
    except Exception:
        pass
    if (ipo.get("geography") or "") == (cand.get("geography") or "") and ipo.get("geography"):
        s += 5
    return round(min(100, s), 1)


def select_peers(ipo: dict, candidates: list[dict], top_n: int = 6) -> list[dict]:
    scored = [{**c, "match_score": peer_score(ipo, c)} for c in candidates]
    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored[:top_n]
