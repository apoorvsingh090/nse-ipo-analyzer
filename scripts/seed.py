"""Seed DB from historical CSV + create an example live IPO (§23, deliverables)."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from ..config import SRC_FILING, SRC_OFFICIAL, SRC_THIRD
from ..database import (Company, DataSource, IPO, IPOHistoricalReturn,
                        IPOSubscription, get_session_factory, init_db)

CSV = Path(__file__).resolve().parent.parent / "data" / "historical_ipos.csv"


def _d(s: str):
    return datetime.strptime(s, "%Y-%m-%d").date() if s else None


def _f(s: str):
    try:
        return float(s) if s not in ("", None) else None
    except Exception:
        return None


def seed(db_url: str | None = None) -> dict:
    init_db(db_url)
    Session = get_session_factory(db_url)
    s = Session()
    n_ipos = 0
    with open(CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            co = s.query(Company).filter_by(name=row["company"]).first()
            if not co:
                co = Company(name=row["company"], sector=row["sector"])
                s.add(co)
                s.flush()
            if s.query(IPO).filter_by(company_name=row["company"]).first():
                continue
            ipo = IPO(
                company_id=co.id, company_name=row["company"],
                segment=row.get("segment") or "mainboard", status="listed",
                sector=row["sector"],
                price_band_low=_f(row["price_band_low"]),
                price_band_high=_f(row["price_band_high"]),
                issue_price=_f(row["issue_price"]),
                issue_size_cr=_f(row["issue_size_cr"]),
                fresh_issue_cr=_f(row["fresh_issue_cr"]),
                ofs_cr=_f(row["ofs_cr"]), lot_size=int(float(row["lot_size"] or 0) or 0) or None,
                open_date=_d(row["open_date"]), close_date=_d(row["close_date"]),
                listing_date=_d(row["listing_date"]),
                listing_price=_f(row["listing_price"]),
                source=SRC_OFFICIAL)
            s.add(ipo)
            s.flush()
            s.add(IPOSubscription(
                ipo_id=ipo.id, snapshot_at=datetime.combine(_d(row["close_date"]),
                                                            datetime.min.time()),
                day_label="Final", qib_x=_f(row["qib_x"]), nii_x=_f(row["nii_x"]),
                retail_x=_f(row["retail_x"]), total_x=_f(row["total_x"]),
                source=SRC_OFFICIAL))
            s.add(IPOHistoricalReturn(
                ipo_id=ipo.id, listing_gain_pct=_f(row["listing_gain_pct"]),
                ret_1m=_f(row["ret_1m"]), source=SRC_OFFICIAL))
            n_ipos += 1
    for name, kind, url in (
            ("NSE", "official", "https://www.nseindia.com"),
            ("BSE", "official", "https://www.bseindia.com"),
            ("SEBI filings", "filing", "https://www.sebi.gov.in"),
            ("GMP aggregators", "gmp", None)):
        if not s.query(DataSource).filter_by(name=name).first():
            s.add(DataSource(name=name, kind=kind, url=url,
                             last_status="seeded"))
    s.commit()
    total = s.query(IPO).count()
    s.close()
    return {"seeded_new": n_ipos, "total_ipos": total}


def seed_example(db_url: str | None = None) -> int:
    """Create one worked example: 'Narmada AgroTech Ltd' (upcoming)."""
    from ..database import IPOFinancial, IPOGMP, Peer
    init_db(db_url)
    Session = get_session_factory(db_url)
    s = Session()
    ex = s.query(IPO).filter_by(company_name="Narmada AgroTech Ltd").first()
    if ex:
        s.close()
        return ex.id
    co = Company(name="Narmada AgroTech Ltd", sector="FMCG",
                 industry="Agri-processing",
                 promoter_names='["R. Patel", "S. Patel"]')
    s.add(co)
    s.flush()
    ex = IPO(company_id=co.id, company_name="Narmada AgroTech Ltd",
             symbol="NARMADA", segment="mainboard", status="open",
             sector="FMCG", price_band_low=280, price_band_high=295,
             issue_price=295, issue_size_cr=950,
             fresh_issue_cr=620, ofs_cr=330, lot_size=50,
             min_investment=14750,
             open_date=_d("2026-09-24"), close_date=_d("2026-09-29"),
             listing_date=_d("2026-10-06"),
             retail_pct=35, nii_pct=15, qib_pct=50,
             promoter_holding_pre=78.5, promoter_holding_post=68.2,
             pre_ipo_shares=4.10, post_ipo_shares=4.79,
             rhp_url="https://www.sebi.gov.in/example-narmada-rhp.pdf",
             source=SRC_FILING)
    s.add(ex)
    s.flush()
    fins = [
        ("FY23", 820, 118, 62, 12.5, 95, 60, 180, 320, 14.0, 15.5, 140, 95, 60, 40, 8),
        ("FY24", 1015, 158, 89, 17.2, 130, 85, 165, 395, 17.5, 18.2, 175, 120, 72, 55, 10),
        ("FY25", 1245, 205, 122, 23.1, 168, 110, 150, 505, 21.0, 20.4, 210, 148, 85, 60, 12),
    ]
    for fy, rev, eb, pat, eps, ocf, fcf, debt, nw, roe, roce, wc, rec, inv, cont, rpt in fins:
        s.add(IPOFinancial(ipo_id=ex.id, fiscal_year=fy, revenue_cr=rev,
                           ebitda_cr=eb, ebitda_margin=round(eb / rev * 100, 1),
                           pat_cr=pat, eps=eps, diluted_eps=eps,
                           ocf_cr=ocf, fcf_cr=fcf, total_debt_cr=debt,
                           net_debt_cr=debt - 25, net_worth_cr=nw,
                           roe=roe, roce=roce, working_capital_cr=wc,
                           receivables_cr=rec, inventory_cr=inv,
                           contingent_liab_cr=cont, related_party_cr=rpt,
                           source="Company/SEBI filing", source_doc="RHP",
                           source_page="183"))
    s.add(IPOSubscription(ipo_id=ex.id, day_label="Day2",
                          snapshot_at=datetime(2026, 9, 26, 17, 0),
                          retail_x=3.8, nii_x=5.2, qib_x=1.9, total_x=3.4,
                          source=SRC_OFFICIAL))
    for day, g in ((24, 42), (25, 55), (26, 68)):
        s.add(IPOGMP(ipo_id=ex.id, observed_at=datetime(2026, 9, day, 18, 0),
                     gmp=g, ipo_price=295, implied_listing_price=295 + g,
                     gmp_pct=round(g / 295 * 100, 2), source="Unofficial GMP"))
    for nm, sym, mc, pe in (("Sahyadri Foods", "SAHYADRI", 4200, 23.0),
                            ("Annapurna Dairy", "ANNAPURNA", 3100, 21.0),
                            ("Krishi Seeds", "KRISHI", 1800, 20.0)):
        s.add(Peer(ipo_id=ex.id, peer_name=nm, peer_symbol=sym,
                   market_cap_cr=mc, pe=pe, ev_ebitda=11.5, match_score=72.0,
                   source=SRC_THIRD))
    s.commit()
    ipo_id = ex.id
    s.close()
    return ipo_id


if __name__ == "__main__":
    print(seed())
    print("example:", seed_example())
