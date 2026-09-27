"""Live upcoming-IPO fetcher (§2, §23 step 1-2).

Sources (honestly labelled per field):
  - NSE `/api/all-upcoming-issues?category=ipo` + `/api/ipo-current-issue`
    -> Official exchange data (company, symbol, dates, price band, live total
    subscription). Verified live 27-Sep-2026.
  - Chittorgarh IPO detail pages -> Third-party data (lot size, issue size
    ₹cr, fresh/OFS split, pre/post shares, allocation %, listing date).
  - investorgain (via Playwright, reusing ipo.py parsers) -> Unofficial GMP
    + third-party subscription splits where NSE only gives totals.

Anything unreachable yields `Data unavailable` for those fields — never
fabricated, never silently stale.
"""
from __future__ import annotations

import html as html_mod
import logging
import re
from datetime import date, datetime, timezone
from difflib import SequenceMatcher

import httpx

from ..config import (DATA_UNAVAILABLE, NSE_BASE, SRC_GMP, SRC_OFFICIAL,
                      SRC_THIRD)

log = logging.getLogger(__name__)

NSE_UPCOMING_URL = f"{NSE_BASE}/api/all-upcoming-issues?category=ipo"
NSE_CURRENT_URL = f"{NSE_BASE}/api/ipo-current-issue"
NSE_PAGE_URL = f"{NSE_BASE}/market-data/all-upcoming-issues-ipo"
CHIT_LIST_URL = "https://www.chittorgarh.com/ipo/ipo_list.asp"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_PAGE_URL,
}
_HTML_HEADERS = {"User-Agent": _HEADERS["User-Agent"]}

_MONTHS = {m: i + 1 for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul",
     "aug", "sep", "oct", "nov", "dec"))}


# ---------------------------------------------------------------- parsing

def parse_nse_date(s: str | None) -> date | None:
    """'25-Sep-2026' -> date. Returns None (Data unavailable) on failure."""
    if not s:
        return None
    m = re.match(r"\s*(\d{1,2})-([A-Za-z]{3})-(\d{4})\s*", str(s))
    if not m:
        return None
    mon = _MONTHS.get(m.group(2).lower())
    if not mon:
        return None
    try:
        return date(int(m.group(3)), mon, int(m.group(1)))
    except ValueError:
        return None


def parse_nse_band(s: str | None) -> tuple[float | None, float | None]:
    """'Rs.290 to Rs.302' -> (290.0, 302.0)."""
    if not s:
        return None, None
    nums = re.findall(r"\d+(?:\.\d+)?", str(s).replace(",", ""))
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    if len(nums) == 1:
        return None, float(nums[0])
    return None, None


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def normalize_nse_record(rec: dict, bid_by_symbol: dict | None = None) -> dict:
    """One NSE upcoming-issue row -> IPO-ready dict with source labels."""
    series = (rec.get("series") or "").upper()
    segment = "sme" if "SME" in series else "mainboard"
    lo, hi = parse_nse_band(rec.get("issuePrice"))
    status = "open" if str(rec.get("status", "")).lower() == "active" else "upcoming"
    out = {
        "company_name": rec.get("companyName"),
        "symbol": rec.get("symbol"),
        "segment": segment,
        "status": status,
        "open_date": parse_nse_date(rec.get("issueStartDate")),
        "close_date": parse_nse_date(rec.get("issueEndDate")),
        "price_band_low": lo,
        "price_band_high": hi,
        "issue_price": hi,  # upper band = bid reference until basis fixed
        "total_sub_x": None,
        "field_sources": {
            "company_name": SRC_OFFICIAL, "symbol": SRC_OFFICIAL,
            "segment": SRC_OFFICIAL, "status": SRC_OFFICIAL,
            "open_date": SRC_OFFICIAL, "close_date": SRC_OFFICIAL,
            "price_band": SRC_OFFICIAL, "subscription_total": SRC_OFFICIAL,
        },
        "source_url": NSE_UPCOMING_URL,
    }
    bid = (bid_by_symbol or {}).get(rec.get("symbol") or "")
    if bid is not None:
        out["total_sub_x"] = _num(bid)
    return out


def chit_detail_links(list_html: str) -> dict[str, str]:
    """Map lowercase company slug -> absolute detail URL from list page."""
    out: dict[str, str] = {}
    for m in re.finditer(
            r'href="(https://www\.chittorgarh\.com/ipo/([^"/]+)/\d+/)"[^>]*'
            r'title="([^"]+?)\s*IPO"', list_html):
        url, slug, name = m.group(1), m.group(2), m.group(3)
        out[name.strip().lower()] = url
        out[slug.replace("-", " ")] = url
    return out


def match_chit_url(company: str, links: dict[str, str],
                   thresh: float = 0.55) -> str | None:
    base = re.sub(r"\s+(limited|ltd\.?|india)$", "", company.lower()).strip()
    best, best_s = None, 0.0
    for name, url in links.items():
        s = SequenceMatcher(None, base, name).ratio()
        if s > best_s:
            best_s, best = s, url
    return best if best_s >= thresh else None


def _clean(html: str) -> str:
    t = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.I)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.DOTALL | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html_mod.unescape(t)
    return re.sub(r"\s+", " ", t)


def parse_chit_detail(html: str, url: str) -> dict:
    """Chittorgarh detail page -> enrichment dict (Third-party data)."""
    t = _clean(html)
    d: dict = {"source_url": url, "field_sources": {}}

    def grab(pat: str, cast=_num, label: str = ""):
        m = re.search(pat, t, re.I)
        v = cast(m.group(1)) if m else None
        if label:
            d["field_sources"][label] = SRC_THIRD if v is not None else DATA_UNAVAILABLE
        return v

    band = re.search(r"Price Band\s*₹?\s*([\d,]+)\s*to\s*₹?\s*([\d,]+)", t, re.I)
    if band:
        d["price_band_low"] = _num(band.group(1))
        d["price_band_high"] = _num(band.group(2))
        d["field_sources"]["price_band"] = SRC_THIRD
    d["lot_size"] = grab(r"Lot Size\s*([\d,]+)\s*Shares?", label="lot_size")
    d["face_value"] = grab(r"Face Value\s*₹?\s*([\d,]+)", label="face_value")
    d["listing_date"] = None
    m = re.search(r"Listing Date\s*\w{3},\s*(\w{3,9})\s*(\d{1,2}),\s*(\d{4})", t)
    if m and m.group(1)[:3].lower() in _MONTHS:
        try:
            d["listing_date"] = date(int(m.group(3)),
                                     _MONTHS[m.group(1)[:3].lower()],
                                     int(m.group(2)))
            d["field_sources"]["listing_date"] = SRC_THIRD
        except ValueError:
            pass
    m = re.search(r"IPO Date\s*(\d{1,2})\s*to\s*(\d{1,2})\s*(\w{3,9}),?\s*(\d{4})", t)
    if m and m.group(3)[:3].lower() in _MONTHS:
        try:
            mon, yr = _MONTHS[m.group(3)[:3].lower()], int(m.group(4))
            d["open_date"] = date(yr, mon, int(m.group(1)))
            d["close_date"] = date(yr, mon, int(m.group(2)))
            d["field_sources"]["open_date"] = SRC_THIRD
            d["field_sources"]["close_date"] = SRC_THIRD
        except ValueError:
            pass
    # issue size / fresh / OFS in ₹ cr ("agg. up to ₹ 1,092 Cr")
    tot = re.search(r"Total Issue Size\s*[\d,]+\s*shares?\s*\(agg\.\s*up to\s*₹?\s*([\d,]+)\s*Cr\)", t, re.I)
    d["issue_size_cr"] = _num(tot.group(1)) if tot else None
    fr = re.search(r"Fresh Issue\s*[\d,]+\s*shares?\s*\(agg\.\s*up to\s*₹?\s*([\d,]+)\s*Cr\)", t, re.I)
    d["fresh_issue_cr"] = _num(fr.group(1)) if fr else None
    of = re.search(r"Offer for Sale\s*[\d,]+\s*shares?(?:\s*of\s*₹?\s*[\d,]+)?\s*\(agg\.\s*up to\s*₹?\s*([\d,]+)\s*Cr\)", t, re.I)
    d["ofs_cr"] = _num(of.group(1)) if of else None
    for k in ("issue_size_cr", "fresh_issue_cr", "ofs_cr"):
        d["field_sources"][k] = SRC_THIRD if d.get(k) is not None else DATA_UNAVAILABLE
    pre = re.search(r"Share Holding Pre Issue\s*([\d,]+)\s*shares?", t, re.I)
    post = re.search(r"(?:Share Holding Post Issue|Post Issue)\s*([\d,]+)\s*shares?", t, re.I)
    d["pre_ipo_shares"] = _num(pre.group(1)) / 1e7 if pre else None  # -> crore shares
    d["post_ipo_shares"] = _num(post.group(1)) / 1e7 if post else None
    # allocation % (QIB 50.00% / NII 15% / RII 35%)
    for key, pat in (("qib_pct", r"(\d+(?:\.\d+)?)%?\)?\s*(?:are\s+)?allocated to QIB"),
                     ("nii_pct", r"(\d+(?:\.\d+)?)%?\)?\s*allocated to NII"),
                     ("retail_pct", r"(\d+(?:\.\d+)?)%?\)?\s*allocated to RI?I")):
        m = re.search(pat, t, re.I)
        d[key] = _num(m.group(1)) if m else None
        d["field_sources"][key] = SRC_THIRD if d[key] is not None else DATA_UNAVAILABLE
    d["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return d


def merge_live(nse: dict, chit: dict | None) -> dict:
    """NSE (official) wins on conflicts; Chittorgarh fills gaps (labelled)."""
    out = dict(nse)
    if not chit:
        out["enrichment"] = DATA_UNAVAILABLE
        return out
    for k in ("lot_size", "issue_size_cr", "fresh_issue_cr", "ofs_cr",
              "pre_ipo_shares", "post_ipo_shares", "qib_pct", "nii_pct",
              "retail_pct", "face_value", "listing_date"):
        if out.get(k) is None and chit.get(k) is not None:
            out[k] = chit[k]
    # Chittorgarh band only if NSE lacked one
    if out.get("price_band_low") is None and chit.get("price_band_low") is not None:
        out["price_band_low"], out["price_band_high"] = \
            chit["price_band_low"], chit["price_band_high"]
        out["issue_price"] = chit.get("price_band_high")
    if out.get("open_date") is None and chit.get("open_date") is not None:
        out["open_date"], out["close_date"] = chit["open_date"], chit["close_date"]
    if out.get("listing_date") is None and chit.get("listing_date") is not None:
        out["listing_date"] = chit["listing_date"]
    if out.get("lot_size") and out.get("issue_price"):
        out["min_investment"] = round(out["lot_size"] * out["issue_price"], 2)
    fs = dict(nse.get("field_sources", {}))
    fs.update(chit.get("field_sources", {}))
    out["field_sources"] = fs
    out["chit_url"] = chit.get("source_url")
    out["enrichment"] = "NSE official + Chittorgarh third-party"
    for k in ("financials", "anchor"):
        if chit.get(k) is not None:
            out[k] = chit[k]
    return out


# ---------------------------------------------------------------- fetching

def parse_chit_financials(html: str) -> list[dict]:
    """Restated financials table on Chittorgarh detail pages (Third-party data).

    Header: 'Period Ended 30 Jun 2026 31 Mar 2026 ...'. Annual '31 Mar YYYY'
    columns -> FY rows with revenue/PAT/EBITDA/net-worth (Rs cr). Quarter
    columns are skipped for growth math. Empty list when absent.
    """
    t = _clean(html)
    m = re.search(r"Period Ended((?:\s+\d{1,2}\s+\w{3,9}\s+\d{4}){2,})", t, re.I)
    if not m:
        return []
    cols = re.findall(r"(\d{1,2})\s+(\w{3,9})\s+(\d{4})", m.group(1), re.I)
    body = t[m.end():m.end() + 4000]

    def row_vals(label: str) -> list[float | None]:
        mm = re.search(label + r"((?:\s+[\d,]+\.\d+|\s+\-)+)", body, re.I)
        if not mm:
            return []
        return [_num(x) for x in re.findall(r"[\d,]+\.\d+", mm.group(1))]

    specs = [("total income", "revenue_cr"), ("profit after tax", "pat_cr"),
             ("ebitda", "ebitda_cr"), ("net worth", "net_worth_cr")]
    series = {k: row_vals(lbl) for lbl, k in specs}
    out: list[dict] = []
    for i, (dd, mon, yy) in enumerate(cols):
        if mon[:3].lower() not in _MONTHS or _MONTHS[mon[:3].lower()] == 6:
            continue  # June columns are quarters, not full years
        if mon[:3].lower() != "mar":
            continue
        fy = f"FY{yy[-2:]}"
        row = {"fiscal_year": fy, "field_sources": {}}
        for _, key in specs:
            vals = series[key]
            v = vals[i] if i < len(vals) else None
            row[key] = v
            row["field_sources"][key] = SRC_THIRD if v is not None else DATA_UNAVAILABLE
        if row.get("revenue_cr") and row.get("ebitda_cr"):
            row["ebitda_margin"] = round(row["ebitda_cr"] / row["revenue_cr"] * 100, 1)
        if row.get("pat_cr") and row.get("net_worth_cr"):
            row["roe"] = round(row["pat_cr"] / row["net_worth_cr"] * 100, 1)
        out.append(row)
    # oldest-first for CAGR math
    out.sort(key=lambda r: r["fiscal_year"])
    return out


def parse_chit_anchor(html: str) -> dict:
    """Anchor portion ₹cr + lock-in end dates (Third-party data)."""
    t = _clean(html)
    out: dict = {"field_sources": {}}
    m = re.search(r"Anchor Portion\s*\(.*?Cr\.?\)\s*([\d,]+(?:\.\d+)?)", t, re.I)
    out["anchor_total_cr"] = _num(m.group(1)) if m else None
    out["field_sources"]["anchor_total_cr"] = \
        SRC_THIRD if out["anchor_total_cr"] is not None else DATA_UNAVAILABLE
    for key, pat in (("lockin_30d", r"lock-in period end date for 50% shares\s*\(30 Days\)\s*\w{3},\s*(\w{3,9})\s*(\d{1,2}),\s*(\d{4})"),
                     ("lockin_90d", r"lock-in period end date for remaining shares\s*\(90 Days\)\s*\w{3},\s*(\w{3,9})\s*(\d{1,2}),\s*(\d{4})")):
        mm = re.search(pat, t, re.I)
        if mm and mm.group(1)[:3].lower() in _MONTHS:
            try:
                out[key] = date(int(mm.group(3)), _MONTHS[mm.group(1)[:3].lower()],
                                int(mm.group(2)))
            except ValueError:
                out[key] = None
        else:
            out[key] = None
    return out


def match_gmp_record(company: str, rows: list[dict],
                     thresh: float = 0.5) -> dict | None:
    """Fuzzy-match a company to live investorgain GMP rows (Unofficial GMP)."""
    base = re.sub(r"\s+(limited|ltd\.?|india)$", "", company.lower()).strip()
    best, best_s = None, 0.0
    for r in rows or []:
        s = SequenceMatcher(None, base, (r.get("name") or "").lower()).ratio()
        if s > best_s:
            best_s, best = s, r
    if best is None or best_s < thresh or not isinstance(best.get("gmp"), (int, float)):
        return None
    try:
        px = float(str(best.get("price")).replace(",", ""))
    except (TypeError, ValueError):
        px = None
    return {"gmp": best["gmp"], "ipo_price": px,
            "match_score": round(best_s, 2),
            "matched_name": best.get("name"),
            "source_kind": SRC_GMP}

def _nse_client() -> httpx.Client:
    c = httpx.Client(base_url=NSE_BASE, headers=_HEADERS, timeout=25,
                     follow_redirects=True)
    try:
        c.get("/", timeout=15)  # cookie bootstrap
    except Exception as e:  # pragma: no cover
        log.debug("NSE cookie bootstrap failed: %s", e)
    return c


def fetch_nse_upcoming() -> tuple[list[dict], dict[str, float | None]]:
    """Returns (upcoming rows, {symbol: total_sub_x}). Empty list on failure."""
    c = _nse_client()
    try:
        r = c.get("/api/all-upcoming-issues?category=ipo")
        rows = r.json() if r.status_code == 200 else []
        if not isinstance(rows, list):
            rows = []
    except Exception as e:
        log.warning("NSE upcoming fetch failed: %s", e)
        rows = []
    bids: dict[str, float | None] = {}
    try:
        r2 = c.get("/api/ipo-current-issue")
        if r2.status_code == 200 and isinstance(r2.json(), list):
            for d in r2.json():
                if d.get("symbol") and d.get("category") == "Total":
                    bids[d["symbol"]] = _num(d.get("noOfTime"))
                elif d.get("symbol") and d.get("symbol") not in bids:
                    bids[d["symbol"]] = _num(d.get("noOfTime"))
    except Exception as e:
        log.debug("NSE bid fetch failed: %s", e)
    finally:
        try:
            c.close()
        except Exception:
            pass
    return rows, bids


def fetch_chit_list() -> dict[str, str]:
    try:
        with httpx.Client(timeout=25, follow_redirects=True,
                          headers=_HTML_HEADERS) as c:
            r = c.get(CHIT_LIST_URL)
            if r.status_code == 200:
                return chit_detail_links(r.text)
    except Exception as e:
        log.warning("Chittorgarh list fetch failed: %s", e)
    return {}


def fetch_chit_detail(url: str) -> dict | None:
    try:
        with httpx.Client(timeout=25, follow_redirects=True,
                          headers=_HTML_HEADERS) as c:
            r = c.get(url)
            if r.status_code == 200:
                d = parse_chit_detail(r.text, url)
                d["financials"] = parse_chit_financials(r.text)
                d["anchor"] = parse_chit_anchor(r.text)
                return d
    except Exception as e:
        log.warning("Chittorgarh detail fetch failed %s: %s", url, e)
    return None


def fetch_live_upcoming(enrich: bool = True,
                        max_enrich: int = 12) -> list[dict]:
    """Full live pipeline: NSE official list + optional Chittorgarh enrich."""
    rows, bids = fetch_nse_upcoming()
    records = [normalize_nse_record(r, bids) for r in rows
               if r.get("companyName")]
    if enrich and records:
        links = fetch_chit_list()
        for rec in records[:max_enrich]:
            url = match_chit_url(rec["company_name"], links)
            chit = fetch_chit_detail(url) if url else None
            merged = merge_live(rec, chit)
            rec.update(merged)
            if url and not chit:
                rec["enrichment"] = "Chittorgarh fetch failed — NSE only"
    for rec in records:
        rec["gmp_note"] = ("See /live/gmp for unofficial GMP (investorgain, "
                           "requires JS render).")
    return records


def fetch_live_gmp() -> list[dict]:
    """Live GMP via investorgain JS table (Playwright) + ipo.py parsers.

    Returns [] when the page cannot be rendered — labelled Unofficial GMP.
    """
    try:
        from playwright.sync_api import sync_playwright
        import sys as _sys
        from pathlib import Path as _P
        _sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
        from ipo import parse_investorgain
    except Exception as e:
        log.warning("GMP live fetch unavailable: %s", e)
        return []
    url = "https://www.investorgain.com/report/ipo-gmp-live/331/"
    html = None
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            try:
                pg = b.new_page(viewport={"width": 1280, "height": 800})
                pg.goto(url, wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_function(
                    "() => { const tb=document.getElementById('tableBody'); "
                    "return tb && tb.querySelector('tr') && !/No data/.test(tb.innerText); }",
                    timeout=30000)
                html = pg.content()
            finally:
                b.close()
    except Exception as e:
        log.warning("investorgain render failed: %s", e)
        return []
    try:
        out = parse_investorgain(html or "")
        for r in out:
            r["source_kind"] = SRC_GMP
        return out
    except Exception as e:  # pragma: no cover
        log.warning("investorgain parse failed: %s", e)
        return []
