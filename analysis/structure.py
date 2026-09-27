"""IPO structure (§6) + use-of-proceeds (§7) analysis."""
from __future__ import annotations


def analyze_structure(ipo: dict) -> dict:
    fresh = ipo.get("fresh_issue_cr") or 0
    ofs = ipo.get("ofs_cr") or 0
    total = ipo.get("issue_size_cr") or (fresh + ofs) or None
    fresh_pct = round(fresh / total * 100, 1) if total else None
    ofs_pct = round(ofs / total * 100, 1) if total else None
    pre = ipo.get("pre_ipo_shares")
    post = ipo.get("post_ipo_shares")
    dilution = round((post - pre) / post * 100, 1) if pre and post else None
    flags: list[str] = []
    if ofs_pct is not None and ofs_pct >= 70:
        flags.append(f"Very high OFS ({ofs_pct}%) — mostly an exit; "
                     "check who is selling and why.")
    elif ofs_pct is not None and ofs_pct >= 40:
        flags.append(f"Material OFS ({ofs_pct}%) — review seller identity.")
    if fresh_pct is not None and fresh_pct >= 60:
        flags.append(f"Fresh-issue heavy ({fresh_pct}%) — money goes to the company.")
    return {"fresh_issue_cr": fresh, "ofs_cr": ofs, "issue_size_cr": total,
            "fresh_pct": fresh_pct, "ofs_pct": ofs_pct,
            "dilution_pct": dilution,
            "promoter_pre": ipo.get("promoter_holding_pre"),
            "promoter_post": ipo.get("promoter_holding_post"),
            "flags": flags,
            "note": "Fresh issue = money to company. OFS = selling shareholders exit."}


PROCEEDS_CLASSES = ("Debt repayment", "Capex", "Working capital",
                    "Acquisitions", "General corporate purposes",
                    "Existing shareholder exit (OFS)", "Other")


def classify_proceeds(items: list[dict]) -> dict:
    buckets: dict[str, float] = {k: 0.0 for k in PROCEEDS_CLASSES}
    for it in items:
        p = str(it.get("purpose", "")).lower()
        amt = float(it.get("amount_cr") or 0)
        if "debt" in p or "borrow" in p:
            buckets["Debt repayment"] += amt
        elif "capex" in p or "capital expend" in p or "plant" in p:
            buckets["Capex"] += amt
        elif "working capital" in p:
            buckets["Working capital"] += amt
        elif "acquis" in p:
            buckets["Acquisitions"] += amt
        elif "general corporate" in p or "gcp" in p:
            buckets["General corporate purposes"] += amt
        elif "offer for sale" in p or p.strip() == "ofs":
            buckets["Existing shareholder exit (OFS)"] += amt
        else:
            buckets["Other"] += amt
    total = sum(buckets.values())
    assessment = []
    if total > 0:
        if buckets["Debt repayment"] / total > 0.4:
            assessment.append("Debt-heavy use — deleveraging is value-accretive "
                              "only if interest burden was material.")
        if buckets["Capex"] / total > 0.3:
            assessment.append("Capex-heavy — value depends on disclosed project "
                              "returns; do not assume undisclosed benefits.")
        if buckets["General corporate purposes"] / total > 0.35:
            assessment.append("Large GCP bucket — low visibility on use.")
    return {"buckets_cr": buckets, "total_cr": round(total, 2),
            "assessment": assessment,
            "note": "Based only on disclosed objects; no speculation on "
                    "undisclosed intentions."}
