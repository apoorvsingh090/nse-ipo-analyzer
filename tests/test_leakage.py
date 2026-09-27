"""Leakage tests (§29 rule 10): forbidden features rejected, timestamps enforced."""
import pytest
from datetime import datetime, timezone

from nse_ipo_analyzer.ml.features import FORBIDDEN, build_features
from nse_ipo_analyzer.ml.leakage import assert_no_leakage


def test_forbidden_rejected():
    with pytest.raises(ValueError):
        build_features({"pe": 20, "listing_price": 500})


def test_all_forbidden_names_known():
    assert "listing_price" in FORBIDDEN and "ret_1m" in FORBIDDEN


def test_timestamp_after_listing_rejected():
    feats = {"pe": {"value": 20,
                    "feature_timestamp": "2026-10-10T00:00:00+00:00"}}
    with pytest.raises(ValueError):
        assert_no_leakage(feats, datetime(2026, 10, 6, tzinfo=timezone.utc))


def test_clean_features_pass():
    feats = build_features({"pe": 20, "qib_x": 5})
    assert assert_no_leakage(feats) is True


def test_walkforward_no_shuffle():
    """Training module must sort by listing_date (inspect source)."""
    import inspect
    from nse_ipo_analyzer.ml import train as t
    src = inspect.getsource(t.walk_forward)
    assert "sort_values" in src and "listing_date" in src
