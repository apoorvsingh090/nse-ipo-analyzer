"""Live import: preview real upcoming IPOs and upsert them into the DB (§23)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from difflib import SequenceMatcher

from ..config import SRC_OFFICIAL, SRC_THIRD
from ..connectors.live import (fetch_live_gmp, fetch_live_upcoming,
                               match_gmp_record)
from ..database import (Company, IPOAnchor, IPODocument, IPOFinancial, IPO,
                        IPOGMP, IPOSubscription, get_session_factory, init_db)


def _jsonable(rec: dict) -> dict:
    def conv(v):
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, date):
            return v.isoformat()
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [conv(x) for x in v]
        return v
    return {k: conv(v) for k, v in rec.items()}


def preview_live(enrich: bool = True) -> dict:
    recs = fetch_live_upcoming(enrich=enrich)
    return {"asof": datetime.now(timezone.utc).isoformat(),
            "count": len(recs),
            "records": [_jsonable(r) for r in recs],
            "sources": {"nse": "Official exchange data",
                        "chittorgarh": "Third-party data"}}


def preview_gmp() -> dict:
    rows = fetch_live_gmp()
    return {"asof": datetime.now(timezone.utc).isoformat(),
            "count": len(rows), "rows": rows,
            "disclaimer": "GMP is an unofficial, unregulated market indicator "
                          "and is not a guaranteed listing price.",
            "source_kind": "Unofficial GMP"}


def _match(records: list[dict], symbol: str | None,
           company: str | None) -> dict | None:
    if symbol:
        for r in records:
            if (r.get("symbol") or "").upper() == symbol.upper():
                return r
    if company:
        best, best_s = None, 0.0
        for r in records:
            s = SequenceMatcher(None, company.lower(),
                                (r.get("company_name") or "").lower()).ratio()
            if s > best_s:
                best_s, best = s, r
        if best_s >= 0.5:
            return best
    return None


def import_live(symbol: str | None = None, company: str | None = None,
                enrich: bool = True, gmp: bool = True,
                db_url: str | None = None) -> dict:
    init_db(db_url)
    records = fetch_live_upcoming(enrich=enrich)
    if not records:
        return {"error": "Live fetch failed — NSE unreachable. "
                         "Data unavailable, nothing imported."}
    rec = _match(records, symbol, company)
    if rec is None:
        return {"error": f"No live IPO matches symbol={symbol} company={company}.",
                "available": [r.get("symbol") for r in records]}
    Session = get_session_factory(db_url)
    s = Session()
    try:
        co = s.query(Company).filter_by(name=rec["company_name"]).first()
        if not co:
            co = Company(name=rec["company_name"])
            s.add(co)
            s.flush()
        ipo = s.query(IPO).filter_by(company_name=rec["company_name"]).first()
        created = False
        if ipo is None:
            ipo = IPO(company_id=co.id, company_name=rec["company_name"],
                      source=SRC_OFFICIAL, source_url=rec.get("source_url"))
            s.add(ipo)
            created = True
        # fill only empty fields from live data (never overwrite curated RHP data)
        for f in ("symbol", "segment", "status", "open_date", "close_date",
                  "listing_date", "price_band_low", "price_band_high",
                  "issue_price", "issue_size_cr", "fresh_issue_cr", "ofs_cr",
                  "lot_size", "min_investment", "retail_pct", "nii_pct",
                  "qib_pct", "pre_ipo_shares", "post_ipo_shares"):
            v = rec.get(f)
            try:
                if v is not None and getattr(ipo, f, None) is None:
                    setattr(ipo, f, v)
            except Exception:
                pass
        if rec.get("status") in ("open", "upcoming") and ipo.status == "listed":
            pass  # never downgrade a listed record from live data
        elif rec.get("status"):
            ipo.status = rec["status"]
        s.flush()
        if rec.get("total_sub_x") is not None:
            s.add(IPOSubscription(
                ipo_id=ipo.id, snapshot_at=datetime.now(timezone.utc),
                day_label="Live", total_x=rec["total_sub_x"],
                source=SRC_OFFICIAL, source_url=rec.get("source_url")))
        # restated financials (third-party) — only fills missing years
        added_fy = []
        for f in rec.get("financials") or []:
            if not f.get("fiscal_year") or s.query(IPOFinancial).filter_by(
                    ipo_id=ipo.id, fiscal_year=f["fiscal_year"]).first():
                continue
            s.add(IPOFinancial(
                ipo_id=ipo.id, fiscal_year=f["fiscal_year"],
                revenue_cr=f.get("revenue_cr"), ebitda_cr=f.get("ebitda_cr"),
                ebitda_margin=f.get("ebitda_margin"), pat_cr=f.get("pat_cr"),
                net_worth_cr=f.get("net_worth_cr"), roe=f.get("roe"),
                source=SRC_THIRD, source_doc="Chittorgarh",
                source_page="Financials table",
                observed_at=datetime.now(timezone.utc)))
            added_fy.append(f["fiscal_year"])
        # anchor book aggregate (investor-level list rarely public pre-listing)
        anch = rec.get("anchor") or {}
        if anch.get("anchor_total_cr") and not s.query(IPOAnchor).filter_by(
                ipo_id=ipo.id).first():
            s.add(IPOAnchor(
                ipo_id=ipo.id, investor_name="Anchor book (aggregate)",
                category="Mixed", amount_cr=anch["anchor_total_cr"],
                lockin_date=anch.get("lockin_30d"), source=SRC_THIRD,
                source_url=rec.get("chit_url")))
        s.add(IPODocument(
            ipo_id=ipo.id, doc_type="LiveImport",
            url=rec.get("chit_url") or rec.get("source_url"),
            parse_status="ok",
            parse_log=f"imported {datetime.now(timezone.utc).isoformat()} "
                      f"enrichment={rec.get('enrichment')}"))
        s.commit()
        ipo_id = ipo.id
    finally:
        s.close()
    gmp_info: dict = {"status": "skipped"}
    if gmp:
        try:
            gm = match_gmp_record(rec["company_name"], fetch_live_gmp())
            if gm:
                px = gm.get("ipo_price") or rec.get("issue_price")
                Session2 = get_session_factory(db_url)
                s2 = Session2()
                try:
                    s2.add(IPOGMP(
                        ipo_id=ipo_id, observed_at=datetime.now(timezone.utc),
                        gmp=gm["gmp"], ipo_price=px,
                        implied_listing_price=round(px + gm["gmp"], 2) if px else None,
                        gmp_pct=round(gm["gmp"] / px * 100, 2) if px else None,
                        source=f"Unofficial GMP (investorgain, matched "
                               f"'{gm['matched_name']}' score {gm['match_score']})"))
                    s2.commit()
                finally:
                    s2.close()
                gmp_info = {"status": "stored", **gm}
            else:
                gmp_info = {"status": "Data unavailable",
                            "note": "No GMP row matched this company"}
        except Exception as e:
            gmp_info = {"status": "Data unavailable", "note": f"GMP fetch failed: {e}"}
    return {"ipo_id": ipo_id, "created": created,
            "company": rec["company_name"], "symbol": rec.get("symbol"),
            "record": _jsonable(rec),
            "financials_added": added_fy, "gmp": gmp_info,
            "next": f"POST /ipos/{ipo_id}/analyze for the full report"}
