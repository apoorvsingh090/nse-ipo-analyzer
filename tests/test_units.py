"""Unit tests: financial calculations (§29 rules 11)."""
from nse_ipo_analyzer.analysis.financials import (analyze_growth, cagr,
                                                  cash_conversion_flags,
                                                  financial_quality_score)
from nse_ipo_analyzer.analysis.structure import analyze_structure
from nse_ipo_analyzer.analysis.valuation import ipo_valuation, vs_peers


def test_cagr():
    assert cagr(100, 133.1, 3) is not None
    assert abs(cagr(100, 121, 2) - 10.0) < 0.01
    assert cagr(None, 100, 2) is None
    assert cagr(-5, 10, 2) is None


def test_growth_latest():
    g = analyze_growth({"FY23": 100, "FY24": 120, "FY25": 150}, "Revenue")
    assert g["latest_yoy_pct"] == 25.0
    assert g["cagr_3y_pct"] is not None


def test_cash_flags_pat_up_ocf_down():
    flags = cash_conversion_flags({"FY24": 100, "FY25": 60},
                                  {"FY24": 50, "FY25": 80})
    assert any("OCF falling" in f or "OCF/PAT" in f for f in flags)


def test_quality_exposes_components():
    q = financial_quality_score({"rev_cagr": 20, "pat_margin": 10,
                                 "roe": 18, "ocf_pat": 0.9,
                                 "debt_equity": 0.4})
    assert "components" in q and q["total"] is not None
    assert set(q["components"]) == {"growth", "profitability", "returns",
                                    "cash_conversion", "leverage"}


def test_valuation_math():
    v = ipo_valuation(100, 10, {"revenue_cr": 500, "ebitda_cr": 100,
                                "pat_cr": 50, "net_worth_cr": 400,
                                "diluted_eps": 5})
    assert v["market_cap_cr"] == 1000
    assert v["pe"] == 20.0
    assert v["ev_ebitda"] is not None


def test_vs_peers_premium():
    cmp = vs_peers({"pe": 30, "ev_ebitda": 15, "ps": 5, "pb": 4},
                   [{"pe": 20, "ev_ebitda": 10, "ps": 4, "pb": 3}])
    assert cmp["pe"]["premium_discount_pct"] == 50.0


def test_quality_all_missing_stays_unknown():
    q = financial_quality_score({})
    assert q["total"] is None
    assert all(v is None for v in q["components"].values())


def test_valuation_eps_fallback():
    v = ipo_valuation(34, 176.0, {"revenue_cr": 3404, "ebitda_cr": 969,
                                  "pat_cr": 242.71, "net_worth_cr": 2225,
                                  "pat_cagr": 19.0})
    assert abs(v["pe"] - 34 / (242.71 / 176.0)) < 0.01
    assert v["eps_source"].startswith("computed")
    assert v["peg"] is not None


def test_structure_ofs_flag():
    s = analyze_structure({"fresh_issue_cr": 100, "ofs_cr": 900,
                           "issue_size_cr": 1000})
    assert s["ofs_pct"] == 90.0
    assert any("OFS" in f for f in s["flags"])
