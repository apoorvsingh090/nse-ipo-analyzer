"""Risk taxonomy (§15) + red-flag detector (§16)."""
from __future__ import annotations

import re

RISK_CATEGORIES = ("Regulatory", "Legal", "Customer concentration",
                    "Supplier concentration", "Promoter dependence",
                    "Related-party transactions", "Debt", "Working capital",
                    "Litigation", "Cyclicality", "Commodity exposure",
                    "Foreign exchange", "Technology", "Competition",
                    "Key-person dependence", "Other")

_CATEGORY_HINTS = {
    "Regulatory": ["regulatory", "regulation", "approval", "license", "compliance", "sebi"],
    "Legal": ["litigat", "legal", "lawsuit", "court", "arbitration"],
    "Customer concentration": ["customer", "client concentration", "top 5 customer", "top 10 customer"],
    "Supplier concentration": ["supplier", "vendor concentration", "raw material supplier"],
    "Promoter dependence": ["promoter"],
    "Related-party transactions": ["related party", "rpt", "related-party"],
    "Debt": ["debt", "borrowings", "leverage", "interest"],
    "Working capital": ["working capital"],
    "Litigation": ["litigat", "dispute", "claim"],
    "Cyclicality": ["cyclical", "downturn", "economic cycle"],
    "Commodity exposure": ["commodity", "raw material price", "steel price", "oil price"],
    "Foreign exchange": ["foreign exchange", "forex", "currency"],
    "Technology": ["technology", "obsolescence", "cyber"],
    "Competition": ["competition", "competitor", "market share"],
    "Key-person dependence": ["key person", "key managerial", "dependence on management"],
}


def classify_risk(text: str) -> str:
    low = text.lower()
    for cat, hints in _CATEGORY_HINTS.items():
        if any(h in low for h in hints):
            return cat
    return "Other"


def rank_risks(risks: list[dict]) -> list[dict]:
    order = {"high": 0, "medium": 1, "low": 2}
    for r in risks:
        if not r.get("category") or r["category"] == "Unclassified":
            r["category"] = classify_risk(r.get("description", ""))
    return sorted(risks, key=lambda r: order.get(r.get("severity", "medium"), 1))


def detect_red_flags(fin_years: list[dict], ipo: dict,
                     risks: list[dict]) -> list[dict]:
    """Explicit rules; every hit is 'Potential red flag — requires review'
    with filing evidence, never a fraud label."""
    flags: list[dict] = []

    def add(rule: str, evidence: str):
        flags.append({"rule": rule, "status": "Potential red flag — requires review",
                      "evidence": evidence})

    by_fy = {f.get("fiscal_year"): f for f in fin_years}
    fys = sorted(by_fy)
    if len(fys) >= 2:
        a, b = by_fy[fys[-2]], by_fy[fys[-1]]
        for k in ("receivables_cr", "inventory_cr"):
            try:
                if a.get(k) and b.get(k) and a[k] > 0 and (b[k] - a[k]) / a[k] > 0.4:
                    rev_g = None
                    if a.get("revenue_cr") and b.get("revenue_cr") and a["revenue_cr"] > 0:
                        rev_g = (b["revenue_cr"] - a["revenue_cr"]) / a["revenue_cr"]
                    if rev_g is None or (b[k] - a[k]) / a[k] - rev_g > 0.25:
                        add(f"Rapid {k} growth",
                            f"{k} {a[k]} → {b[k]} cr outpacing revenue "
                            f"({fys[-2]}→{fys[-1]}).")
            except Exception:
                pass
        # margin jump
        try:
            m0 = (a.get("ebitda_cr") or 0) / (a.get("revenue_cr") or 1) * 100
            m1 = (b.get("ebitda_cr") or 0) / (b.get("revenue_cr") or 1) * 100
            if m1 - m0 > 8:
                add("Sudden margin expansion",
                    f"EBITDA margin {m0:.1f}% → {m1:.1f}% in one year; "
                    "verify sustainability in RHP MD&A.")
        except Exception:
            pass
        # OCF negative while PAT positive
        for fy in fys[-2:]:
            f = by_fy[fy]
            if (f.get("pat_cr") or 0) > 0 and (f.get("ocf_cr") or 0) < 0:
                add("Negative operating cash flow",
                    f"{fy}: PAT ₹{f['pat_cr']} cr but OCF ₹{f['ocf_cr']} cr.")
    for f in fin_years:
        if f.get("contingent_liab_cr") and f.get("net_worth_cr"):
            if f["contingent_liab_cr"] > 0.5 * f["net_worth_cr"]:
                add("Material contingent liabilities",
                    f"{f['fiscal_year']}: contingent ₹{f['contingent_liab_cr']} cr "
                    f"vs net worth ₹{f['net_worth_cr']} cr.")
        if f.get("related_party_cr") and f.get("revenue_cr"):
            if f["related_party_cr"] > 0.15 * f["revenue_cr"]:
                add("Large related-party transactions",
                    f"{f['fiscal_year']}: RPT ₹{f['related_party_cr']} cr "
                    f"({f['related_party_cr']/f['revenue_cr']*100:.1f}% of revenue).")
    ofs_pct = 0
    try:
        tot = (ipo.get("fresh_issue_cr") or 0) + (ipo.get("ofs_cr") or 0)
        if tot:
            ofs_pct = (ipo.get("ofs_cr") or 0) / tot * 100
    except Exception:
        pass
    if ofs_pct >= 70:
        add("High OFS %", f"OFS is {ofs_pct:.1f}% of issue size.")
    if any(re.search(r"auditor.*qualif|qualified opinion|going concern", r.get("description", ""), re.I)
           for r in risks):
        add("Auditor qualification / going-concern mention",
            "Phrase found in extracted risk factors — verify in auditor report.")
    return flags
