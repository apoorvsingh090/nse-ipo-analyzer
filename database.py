"""Database schema for NSE IPO Analyzer (§25).

SQLite by default; PostgreSQL via DATABASE_URL. Every table carries
created_at/updated_at. Data-point tables carry source / source_url /
observed_at for full provenance (§26).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import DATABASE_URL

Base = declarative_base()


def _now():
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)


class Company(Base, TimestampMixin):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    sector = Column(String(128))
    industry = Column(String(128))
    website = Column(String(512))
    promoter_names = Column(Text)  # JSON list stored as text
    notes = Column(Text)


class IPO(Base, TimestampMixin):
    """Core IPO record (§25 `ipos`)."""
    __tablename__ = "ipos"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    company_name = Column(String(255), nullable=False)
    symbol = Column(String(64))
    segment = Column(String(16), default="mainboard")  # mainboard | sme
    status = Column(String(32), default="upcoming")  # upcoming|open|closed|listed
    sector = Column(String(128))

    price_band_low = Column(Float)
    price_band_high = Column(Float)
    issue_price = Column(Float)  # final price, when fixed
    issue_size_cr = Column(Float)
    fresh_issue_cr = Column(Float)
    ofs_cr = Column(Float)
    lot_size = Column(Integer)
    min_investment = Column(Float)

    open_date = Column(Date)
    close_date = Column(Date)
    listing_date = Column(Date)
    listing_price = Column(Float)  # only after listing; NEVER a pre-listing feature

    retail_pct = Column(Float)
    nii_pct = Column(Float)
    qib_pct = Column(Float)
    employee_pct = Column(Float)
    shareholder_pct = Column(Float)

    promoter_holding_pre = Column(Float)
    promoter_holding_post = Column(Float)
    pre_ipo_shares = Column(Float)
    post_ipo_shares = Column(Float)

    drhp_url = Column(String(1024))
    rhp_url = Column(String(1024))
    prospectus_url = Column(String(1024))

    source = Column(String(64))
    source_url = Column(String(1024))

    company = relationship("Company", backref="ipos")


class IPOFinancial(Base, TimestampMixin):
    """One row per fiscal year per IPO (§25 `ipo_financials`)."""
    __tablename__ = "ipo_financials"
    id = Column(Integer, primary_key=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False)
    fiscal_year = Column(String(16), nullable=False)  # e.g. FY24
    revenue_cr = Column(Float)
    ebitda_cr = Column(Float)
    ebitda_margin = Column(Float)
    pat_cr = Column(Float)
    eps = Column(Float)
    diluted_eps = Column(Float)
    ocf_cr = Column(Float)
    fcf_cr = Column(Float)
    total_debt_cr = Column(Float)
    net_debt_cr = Column(Float)
    net_worth_cr = Column(Float)
    roe = Column(Float)
    roce = Column(Float)
    working_capital_cr = Column(Float)
    receivables_cr = Column(Float)
    inventory_cr = Column(Float)
    contingent_liab_cr = Column(Float)
    related_party_cr = Column(Float)
    source = Column(String(64))
    source_doc = Column(String(256))
    source_page = Column(String(64))
    observed_at = Column(DateTime)
    __table_args__ = (UniqueConstraint("ipo_id", "fiscal_year", name="uq_ipo_fy"),)


class IPOSubscription(Base, TimestampMixin):
    """Subscription snapshots (§25)."""
    __tablename__ = "ipo_subscription"
    id = Column(Integer, primary_key=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False)
    snapshot_at = Column(DateTime, default=_now, nullable=False)
    day_label = Column(String(32))  # Day1/Day2/Day3/Final
    retail_x = Column(Float)
    nii_x = Column(Float)
    qib_x = Column(Float)
    employee_x = Column(Float)
    shareholder_x = Column(Float)
    total_x = Column(Float)
    bid_amount_cr = Column(Float)
    source = Column(String(64))
    source_url = Column(String(1024))


class IPOAnchor(Base, TimestampMixin):
    __tablename__ = "ipo_anchor_investors"
    id = Column(Integer, primary_key=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False)
    investor_name = Column(String(255), nullable=False)
    category = Column(String(64))  # MF / Insurance / Sovereign / Other
    amount_cr = Column(Float)
    shares = Column(Float)
    pct_of_anchor = Column(Float)
    lockin_date = Column(Date)
    source = Column(String(64))
    source_url = Column(String(1024))


class IPOValuation(Base, TimestampMixin):
    __tablename__ = "ipo_valuation"
    id = Column(Integer, primary_key=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), unique=True, nullable=False)
    market_cap_cr = Column(Float)
    enterprise_value_cr = Column(Float)
    pe = Column(Float)
    forward_pe = Column(Float)
    ps = Column(Float)
    ev_ebitda = Column(Float)
    ev_sales = Column(Float)
    pb = Column(Float)
    peg = Column(Float)
    peer_median_pe = Column(Float)
    premium_discount_pct = Column(Float)
    computed_at = Column(DateTime, default=_now)
    source = Column(String(64))


class IPOGMP(Base, TimestampMixin):
    __tablename__ = "ipo_gmp"
    id = Column(Integer, primary_key=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False)
    observed_at = Column(DateTime, default=_now, nullable=False)
    gmp = Column(Float)
    ipo_price = Column(Float)
    implied_listing_price = Column(Float)
    gmp_pct = Column(Float)
    source = Column(String(128))


class IPOMarketData(Base, TimestampMixin):
    __tablename__ = "ipo_market_data"
    id = Column(Integer, primary_key=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False)
    observed_at = Column(DateTime, default=_now, nullable=False)
    nifty_close = Column(Float)
    nifty_return_5d = Column(Float)
    india_vix = Column(Float)
    sector_return_5d = Column(Float)
    recent_ipo_avg_gain = Column(Float)
    recent_ipo_avg_sub = Column(Float)
    source = Column(String(64))


class IPODocument(Base, TimestampMixin):
    __tablename__ = "ipo_documents"
    id = Column(Integer, primary_key=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False)
    doc_type = Column(String(64))  # DRHP/RHP/Prospectus/Anchor/Basis/AnnualReport
    url = Column(String(1024))
    local_path = Column(String(1024))
    pages = Column(Integer)
    parse_status = Column(String(64))
    parse_log = Column(Text)


class IPORisk(Base, TimestampMixin):
    __tablename__ = "ipo_risks"
    id = Column(Integer, primary_key=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False)
    category = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(16))  # high|medium|low
    source_doc = Column(String(256))
    source_page = Column(String(64))


class IPOPrediction(Base, TimestampMixin):
    __tablename__ = "ipo_predictions"
    id = Column(Integer, primary_key=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False)
    predicted_at = Column(DateTime, default=_now, nullable=False)
    model_version = Column(String(64))
    issue_price = Column(Float)
    exp_listing_price = Column(Float)
    exp_gain_pct = Column(Float)
    bear_price = Column(Float)
    bear_gain_pct = Column(Float)
    base_price = Column(Float)
    base_gain_pct = Column(Float)
    bull_price = Column(Float)
    bull_gain_pct = Column(Float)
    ci_low_pct = Column(Float)
    ci_high_pct = Column(Float)
    confidence = Column(String(16))
    drivers = Column(Text)  # JSON: {feature: contribution_pp}
    assumptions = Column(Text)


class IPOPredictionFeature(Base, TimestampMixin):
    """Feature store with explicit timestamp per feature (§12)."""
    __tablename__ = "ipo_prediction_features"
    id = Column(Integer, primary_key=True)
    prediction_id = Column(Integer, ForeignKey("ipo_predictions.id"), nullable=False)
    feature_name = Column(String(128), nullable=False)
    feature_value = Column(Float)
    feature_timestamp = Column(DateTime, nullable=False)  # when info was knowable
    source = Column(String(64))


class IPOHistoricalReturn(Base, TimestampMixin):
    __tablename__ = "ipo_historical_returns"
    id = Column(Integer, primary_key=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False)
    listing_gain_pct = Column(Float)
    ret_1w = Column(Float)
    ret_1m = Column(Float)
    ret_3m = Column(Float)
    ret_6m = Column(Float)
    ret_1y = Column(Float)
    source = Column(String(64))


class Peer(Base, TimestampMixin):
    __tablename__ = "peers"
    id = Column(Integer, primary_key=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False)
    peer_name = Column(String(255), nullable=False)
    peer_symbol = Column(String(64))
    market_cap_cr = Column(Float)
    pe = Column(Float)
    ev_ebitda = Column(Float)
    ps = Column(Float)
    pb = Column(Float)
    roe = Column(Float)
    match_score = Column(Float)
    source = Column(String(64))


class DataSource(Base, TimestampMixin):
    __tablename__ = "data_sources"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True, nullable=False)
    kind = Column(String(64))  # official|filing|third|gmp
    url = Column(String(1024))
    last_fetch_at = Column(DateTime)
    last_status = Column(String(64))
    notes = Column(Text)


def get_engine(url: str | None = None):
    url = url or DATABASE_URL
    kwargs = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


def get_session_factory(url: str | None = None):
    return sessionmaker(bind=get_engine(url), autoflush=False, expire_on_commit=False)


def init_db(url: str | None = None):
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    return engine
