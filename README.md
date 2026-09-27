# NSE IPO Analyzer

Production-quality analyzer for **Indian NSE/BSE IPOs** (mainboard + SME):
subscription assessment with transparent evidence, plus an uncertainty-aware
listing-gain estimate. No fabricated data, no look-ahead leakage.

## Quick start (Windows PowerShell)

```powershell
cd C:\Users\Apoorv
pip install -r nse_ipo_analyzer\requirements.txt

# 1. Seed historical DB (42 IPOs) + worked example (Narmada AgroTech Ltd)
python -m nse_ipo_analyzer.scripts.seed

# 2. Train listing model (walk-forward validated, artifacts in ml/artifacts)
#    (or POST /models/train once the server runs)
python -c "from fastapi.testclient import TestClient; ..."  # see below

# 3. Run the server
uvicorn nse_ipo_analyzer.api.main:app --reload --port 8000
# Dashboard: http://localhost:8000/   API docs: http://localhost:8000/docs
```

Train via API instead:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/models/train
```

Run tests:

```powershell
python -m pytest nse_ipo_analyzer/tests/ -q
```

PostgreSQL (optional): set `DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/ipo_analyzer`
before seeding/running. Default is SQLite at `nse_ipo_analyzer/data/ipo_analyzer.db`
(zero-setup local dev).

## Architecture

```
nse_ipo_analyzer/
  config.py            labels, DB URL, GMP disclaimer constants
  database.py          15 tables (§25): ipos, financials, subscription, anchors,
                       valuation, gmp, market, documents, risks, predictions,
                       prediction_features (per-feature timestamps, §12),
                       historical_returns, companies, peers, data_sources
  connectors/          base, nse, bse, sebi (filing download), gmp (UNOFFICIAL,
                       reuses proven parsers from /ipo.py), market (NIFTY/VIX regime)
  parser/rhp_parser.py PyMuPDF pipeline -> figures with (doc, page) cites (§3)
  analysis/            financials, valuation, peers (scored selection), structure,
                       demand (subscription/anchor/gmp), risks+redflags,
                       comparables, explain, recommendation (6 pillars, §14)
  ml/                  features (+FORBIDDEN set), train (walk-forward, §11/§21),
                       predict (bear/base/bull + quantile interval), leakage guards
  api/                 main.py (all §24 endpoints), service.py (§28 report builder,
                       deterministic numbers only; LLM hook = template, §27),
                       workflow endpoint = §23 pipeline
  frontend/index.html  dashboard: overview, valuation, financials, demand,
                       bear/base/bull, drivers, evidence for/against, provenance
  data/historical_ipos.csv  42 IPOs (34 mainboard + 8 SME), includes losers
  scripts/seed.py      historical seed + example IPO
  scripts/workflow.py  §23 automated pipeline (re-runnable, timestamped preds)
  tests/               unit + leakage + integration (17 tests)
```

## Live upcoming IPOs (real NSE data)

```powershell
# Preview what is live right now (official NSE list)
Invoke-RestMethod "http://localhost:8000/live/upcoming?enrich=false"

# Import a real IPO into the DB (NSE official + Chittorgarh third-party enrich)
Invoke-RestMethod -Method Post http://localhost:8000/ipos/import `
  -ContentType "application/json" -Body '{"symbol":"MONEYVIEW"}'

# Then analyze it like any other IPO
Invoke-RestMethod -Method Post http://localhost:8000/ipos/44/analyze
```

Or click **Fetch live IPOs** in the dashboard, then **Import** on any row —
it appears in the dropdown ready to analyze.

How it works: `connectors/live.py` pulls NSE's official
`/api/all-upcoming-issues?category=ipo` (company, symbol, dates, price band)
plus `/api/ipo-current-issue` (live total subscription), and enriches with
lot size, issue size ₹cr, fresh/OFS split, allocation % and listing date from
Chittorgarh detail pages (labelled Third-party data). Import additionally
stores:
- **restated financials** (revenue/PAT/EBITDA/net-worth FY rows → growth,
  ROE, P/E via computed EPS, P/S, EV/EBITDA, P/B),
- **anchor aggregate** (₹cr + lock-in dates; investor-level names are rarely
  public pre-listing),
- **live GMP snapshot** (Playwright + `ipo.py` parsers, fail-soft).
`POST /ipos/import` upserts the record (never overwrites curated RHP data) and stores a live
subscription snapshot. `/live/gmp` renders investorgain's table via
Playwright for unofficial GMP (reuses `ipo.py` parsers). Anything unreachable
is `Data unavailable` — see `tests/test_live.py` (offline fixtures).

## API (§24)

| Method | Endpoint | Notes |
|---|---|---|
| GET | `/ipos` | `?status=&segment=` filters |
| GET | `/ipos/{id}` | IPO record |
| GET | `/ipos/{id}/financials` | Per-FY figures + page cites |
| GET | `/ipos/{id}/valuation` | Multiples + peer premium/discount |
| GET | `/ipos/{id}/subscription` | Table + velocity + verdict |
| GET | `/ipos/{id}/gmp` | Latest + momentum + disclaimer |
| GET | `/ipos/{id}/prediction` | Bear/base/bull + CI + drivers |
| GET | `/ipos/{id}/risks` | Ranked risks + red flags |
| GET | `/ipos/{id}/sources` | Provenance (§26) |
| GET | `/ipos/{id}/history` | All timestamped predictions |
| POST | `/ipos/{id}/analyze` | Full §28 report + persist |
| POST | `/ipos/{id}/refresh` | Re-fetch connectors, re-analyze |
| POST | `/models/train` | Train + walk-forward backtest |
| GET | `/live/upcoming` | Real live IPOs (`?enrich=true` adds Chittorgarh detail) |
| GET | `/live/gmp` | Live unofficial GMP table |
| POST | `/ipos/import` | `{"symbol":...}` or `{"company":...}` → upsert + snapshot |
| GET | `/models/performance` | Model meta |
| GET | `/models/backtest` | Full backtest report |

## Data labels (§2)

Every value carries `Official exchange data`, `Company/SEBI filing`,
`Third-party data`, or `Unofficial GMP`. Missing = `Data unavailable`
— never estimated, never silently stale.

## Anti-leakage (§12)

`ml/features.py::FORBIDDEN` = {listing_price, post returns/news, ...};
`build_features` raises on them; every stored feature has a
`feature_timestamp` that must predate listing (`ml/leakage.py`);
training uses expanding-window walk-forward sorted by `listing_date`
— never shuffled. Leakage tests in `tests/test_leakage.py`.

## GMP (§10)

Unofficial sentiment only. Stored with price/implied/GMP%/timestamp/source;
momentum classified (increasing/stable/declining/negative); always shown
with: *"GMP is an unofficial, unregulated market indicator and is not a
guaranteed listing price."* Never the sole prediction input.

## Example IPO

`Narmada AgroTech Ltd` (id from seed): band ₹280–295, size ₹950 cr
(fresh 65% / OFS 35%), Day-2 demand 3.4x, GMP ₹68 increasing —
base listing estimate ≈ +18% with 11.5–23.4% interval (see
`scripts/verify_example.py`).

## GMP helper reuse

`connectors/gmp.py` imports the proven multibagg/investorgain parsers
(`_linfit`, `_est_gain`, `parse_multibagg`, `parse_investorgain`) from
the existing `/ipo.py` at the workspace root instead of reimplementing them.
