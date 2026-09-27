"""Integration tests: DB, connectors (offline-safe), API, parser."""
from fastapi.testclient import TestClient


def _seeded_client(tmp_path):
    import nse_ipo_analyzer.database as db
    url = f"sqlite:///{(tmp_path / 't.db').as_posix()}"
    from nse_ipo_analyzer.scripts.seed import seed, seed_example
    seed(url)
    eid = seed_example(url)
    # point API at test DB via monkeypatch of factory
    import nse_ipo_analyzer.api.service as svc
    import nse_ipo_analyzer.api.main as main
    orig = db.DATABASE_URL
    svc_orig = svc.build_report
    return url, eid


def test_seed_and_report(tmp_path):
    url, eid = _seeded_client(tmp_path)
    from nse_ipo_analyzer.api.service import build_report
    rep = build_report(eid, url)
    assert "valuation" in rep and "demand" in rep and "gmp" in rep
    assert rep["gmp"]["source_kind"] == "Unofficial GMP"
    assert "assessment" in rep


def test_nse_connector_offline_safe():
    from nse_ipo_analyzer.connectors.nse import NSEConnector
    dp = NSEConnector().fetch_subscription("FAKE-SYMBOL-XYZ")
    assert dp.value is None or isinstance(dp.value, dict)
    assert dp.source  # always labelled


def test_gmp_disclaimer():
    from nse_ipo_analyzer.connectors.gmp import implied_listing, GMP_DISCLAIMER
    assert "unofficial" in GMP_DISCLAIMER.lower()
    r = implied_listing(100, 20)
    assert r["implied_listing_price"] == 120
    assert r["gmp_pct"] == 20.0


def test_pdf_parser_missing_file():
    from nse_ipo_analyzer.parser.rhp_parser import parse_pdf
    res = parse_pdf("nonexistent-xyz.pdf")
    assert res.errors  # logged, not fabricated


def test_api_endpoints(tmp_path, monkeypatch):
    url, eid = _seeded_client(tmp_path)
    import nse_ipo_analyzer.database as db
    monkeypatch.setattr(db, "DATABASE_URL", url)
    import nse_ipo_analyzer.api.service as svc
    import importlib
    # build_report takes db_url param; patch _sess via DATABASE_URL is not
    # enough since get_session_factory() reads at call time -> OK.
    from nse_ipo_analyzer.api.main import app
    c = TestClient(app)
    # seed into the *default* DB too so API finds rows
    from nse_ipo_analyzer.scripts.seed import seed as _seed, seed_example as _ex
    _seed()
    _ex()
    r = c.get("/ipos")
    assert r.status_code == 200 and len(r.json()) >= 1
    rid = _ex()
    assert c.get(f"/ipos/{rid}").status_code == 200
    assert c.get(f"/ipos/{rid}/financials").status_code == 200
    assert c.get(f"/ipos/{rid}/subscription").status_code == 200
    assert c.get(f"/ipos/{rid}/gmp").status_code == 200
    assert c.get(f"/ipos/{rid}/risks").status_code == 200
    assert c.get(f"/ipos/{rid}/sources").status_code == 200
    assert c.get(f"/ipos/{rid}/history").status_code == 200
    assert c.post(f"/ipos/{rid}/analyze").status_code == 200
