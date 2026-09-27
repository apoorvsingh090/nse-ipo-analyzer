"""Tests for live upcoming-IPO fetch/parse/import (offline fixtures + mocked net)."""
import json
from datetime import date
from pathlib import Path

import pytest

from nse_ipo_analyzer.connectors.live import (
    chit_detail_links, match_chit_url, match_gmp_record, merge_live,
    normalize_nse_record, parse_chit_anchor, parse_chit_detail,
    parse_chit_financials, parse_nse_band, parse_nse_date,
)

FIX = Path(__file__).resolve().parent / "fixtures"


def _nse():
    return json.loads((FIX / "nse_upcoming.json").read_text())


def test_nse_date():
    assert parse_nse_date("25-Sep-2026") == date(2026, 9, 25)
    assert parse_nse_date("bogus") is None
    assert parse_nse_date(None) is None


def test_nse_band():
    assert parse_nse_band("Rs.290 to Rs.302") == (290.0, 302.0)
    assert parse_nse_band(None) == (None, None)


def test_normalize_segments():
    rows = _nse()
    main = normalize_nse_record(rows[0], {"TESTMAIN": 2.5})
    assert main["segment"] == "mainboard" and main["status"] == "open"
    assert main["price_band_low"] == 290.0 and main["total_sub_x"] == 2.5
    assert main["field_sources"]["price_band"] == "Official exchange data"
    sme = normalize_nse_record(rows[1], {})
    assert sme["segment"] == "sme" and sme["total_sub_x"] is None


def test_chit_links_and_match():
    links = chit_detail_links((FIX / "chit_list.html").read_text())
    assert links
    url = match_chit_url("Test Mainboard Limited", links)
    assert url == "https://www.chittorgarh.com/ipo/test-mainboard-ipo/9999/"
    assert match_chit_url("Completely Unrelated Xyz", links) is None


def test_chit_detail_parse():
    d = parse_chit_detail((FIX / "chit_detail.html").read_text(), "http://x")
    assert d["price_band_low"] == 290.0 and d["price_band_high"] == 302.0
    assert d["lot_size"] == 49
    assert d["issue_size_cr"] == 366.0
    assert d["fresh_issue_cr"] == 242.0 and d["ofs_cr"] == 124.0
    assert d["qib_pct"] == 50.0 and d["nii_pct"] == 15.0 and d["retail_pct"] == 35.0
    assert d["open_date"] == date(2026, 9, 24)
    assert d["listing_date"] == date(2026, 10, 1)
    assert abs(d["pre_ipo_shares"] - 5.0) < 0.01
    assert d["field_sources"]["lot_size"] == "Third-party data"


def test_merge_prefers_nse():
    nse = normalize_nse_record(_nse()[0], {"TESTMAIN": 2.5})
    chit = parse_chit_detail((FIX / "chit_detail.html").read_text(), "http://x")
    m = merge_live(nse, chit)
    assert m["price_band_low"] == 290.0  # NSE wins
    assert m["lot_size"] == 49 and m["fresh_issue_cr"] == 242.0
    assert m["min_investment"] == 49 * 302.0
    assert merge_live(nse, None)["enrichment"] == "Data unavailable"


def test_chit_financials_annuals_only():
    fins = parse_chit_financials((FIX / "chit_fin.html").read_text())
    assert [f["fiscal_year"] for f in fins] == ["FY24", "FY25", "FY26"]
    fy26 = fins[-1]
    assert fy26["revenue_cr"] == 3404.27 and fy26["pat_cr"] == 242.71
    assert fy26["ebitda_cr"] == 968.92 and fy26["net_worth_cr"] == 2225.42
    assert fy26["ebitda_margin"] == round(968.92 / 3404.27 * 100, 1)
    assert fy26["roe"] == round(242.71 / 2225.42 * 100, 1)
    assert fy26["field_sources"]["revenue_cr"] == "Third-party data"
    assert parse_chit_financials("<html><body>no table</body></html>") == []


def test_chit_anchor():
    from datetime import date
    a = parse_chit_anchor((FIX / "chit_fin.html").read_text())
    assert a["anchor_total_cr"] == 327.50
    assert a["lockin_30d"] == date(2026, 10, 29)
    assert a["lockin_90d"] == date(2026, 12, 28)


def test_gmp_match():
    rows = [{"name": "Moneyview", "gmp": 14, "price": "34"}]
    m = match_gmp_record("Moneyview Limited", rows)
    assert m and m["gmp"] == 14 and m["ipo_price"] == 34.0
    assert match_gmp_record("Unknown Co", rows) is None
    assert match_gmp_record("Moneyview Limited",
                            [{"name": "Moneyview", "gmp": None}]) is None


def test_import_upsert_no_duplicates(tmp_path, monkeypatch):
    import nse_ipo_analyzer.api.live as live
    import nse_ipo_analyzer.database as db
    url = f"sqlite:///{(tmp_path / 'imp.db').as_posix()}"
    recs = [normalize_nse_record(r, {"TESTMAIN": 2.5}) for r in _nse()]
    monkeypatch.setattr(live, "fetch_live_upcoming", lambda enrich=True: recs)
    r1 = live.import_live(symbol="TESTMAIN", enrich=False, db_url=url)
    assert "ipo_id" in r1 and r1["created"] is True
    r2 = live.import_live(symbol="TESTMAIN", enrich=False, db_url=url)
    assert r2["ipo_id"] == r1["ipo_id"] and r2["created"] is False
    # no-match path is honest
    r3 = live.import_live(symbol="NOPE", enrich=False, db_url=url)
    assert "error" in r3 and "available" in r3
    Session = db.get_session_factory(url)
    s = Session()
    try:
        from nse_ipo_analyzer.database import IPO, IPOSubscription
        assert s.query(IPO).count() == 1
        assert s.query(IPOSubscription).filter_by(ipo_id=r1["ipo_id"]).count() == 2
        assert s.query(IPO).first().lot_size is None  # no enrichment in this path
    finally:
        s.close()


def test_import_persists_fin_anchor_gmp(tmp_path, monkeypatch):
    import nse_ipo_analyzer.api.live as live
    import nse_ipo_analyzer.database as db
    url = f"sqlite:///{(tmp_path / 'imp2.db').as_posix()}"
    recs = [normalize_nse_record(r, {"TESTMAIN": 2.5}) for r in _nse()]
    recs[0]["financials"] = parse_chit_financials(
        (FIX / "chit_fin.html").read_text())
    recs[0]["anchor"] = parse_chit_anchor(
        (FIX / "chit_fin.html").read_text())
    monkeypatch.setattr(live, "fetch_live_upcoming", lambda enrich=True: recs)
    monkeypatch.setattr(live, "fetch_live_gmp",
                        lambda: [{"name": "Test Mainboard", "gmp": 20, "price": "300"}])
    r = live.import_live(symbol="TESTMAIN", enrich=False, db_url=url)
    assert r["financials_added"] == ["FY24", "FY25", "FY26"]
    assert r["gmp"]["status"] == "stored"
    Session = db.get_session_factory(url)
    s = Session()
    try:
        from nse_ipo_analyzer.database import (IPOAnchor, IPOFinancial, IPOGMP)
        fins = s.query(IPOFinancial).filter_by(ipo_id=r["ipo_id"]).all()
        assert len(fins) == 3 and fins[-1].source == "Third-party data"
        anch = s.query(IPOAnchor).filter_by(ipo_id=r["ipo_id"]).all()
        assert len(anch) == 1 and anch[0].amount_cr == 327.50
        g = s.query(IPOGMP).filter_by(ipo_id=r["ipo_id"]).all()
        assert len(g) == 1 and g[0].gmp == 20
        assert "Unofficial GMP" in g[0].source
    finally:
        s.close()
