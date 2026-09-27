"""Historical comparables (§19): similar IPOs, full distribution incl. losers."""
from __future__ import annotations


def similarity(target: dict, cand: dict) -> float:
    s = 0.0
    if (target.get("sector") or "") == (cand.get("sector") or ""):
        s += 30
    try:
        for k, w, tol in (("pe", 20, 10), ("issue_size_cr", 15, 500),
                          ("qib_x", 15, 5), ("gmp_pct", 10, 20)):
            a, b = target.get(k), cand.get(k)
            if a is not None and b is not None:
                d = abs(float(a) - float(b))
                s += max(0, w - w * d / tol)
    except Exception:
        pass
    if target.get("segment") == cand.get("segment"):
        s += 10
    return round(s, 1)


def find_comparables(target: dict, history: list[dict], top_n: int = 10) -> dict:
    scored = [{**h, "similarity": similarity(target, h)} for h in history
              if h.get("listing_gain_pct") is not None]
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    picks = scored[:top_n]
    gains = [p["listing_gain_pct"] for p in picks]
    dist = {}
    if gains:
        import statistics
        gains_sorted = sorted(gains)
        dist = {"n": len(gains),
                "min": min(gains), "max": max(gains),
                "median": statistics.median(gains_sorted),
                "mean": round(statistics.mean(gains_sorted), 2),
                "p25": gains_sorted[len(gains_sorted) // 4],
                "p75": gains_sorted[3 * len(gains_sorted) // 4],
                "neg_share_pct": round(sum(1 for g in gains if g < 0) / len(gains) * 100, 1)}
    return {"comparables": picks, "distribution": dist,
            "note": "Includes failed/negative listings; never cherry-picked."}
