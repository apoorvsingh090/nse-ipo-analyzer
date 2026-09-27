"""RHP/DRHP PDF extraction pipeline (§3).

Identifies revenue, EBITDA, PAT, EPS, OCF/FCF, debt, net worth, ROE/ROCE,
working capital, receivables, inventory, contingent liabilities, promoter
holding, share counts, dilution, RPTs — each with exact source/page
reference, e.g. `FY26 Revenue: ₹1,245 crore (RHP, page 183)`.

Strategy: PyMuPDF text per page -> table-ish line scan -> regex patterns
for financial labels. All numbers normalized to ₹ crore. Failures are
logged; missing fields return None (never guessed).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

LABEL_PATTERNS: dict[str, list[str]] = {
    "revenue": [r"revenue from operations", r"total revenue", r"\brevenue\b",
                r"total income"],
    "ebitda": [r"\bebitda\b", r"earnings before interest.*tax.*depreciation"],
    "pat": [r"profit after tax", r"\bpat\b", r"net profit", r"profit for the year"],
    "eps": [r"basic earnings per share", r"\beps\b"],
    "diluted_eps": [r"diluted earnings per share"],
    "ocf": [r"operating cash flow", r"net cash.*operating activities",
            r"cash generated from operations"],
    "fcf": [r"free cash flow"],
    "total_debt": [r"total debt", r"total borrowings", r"aggregate borrowings"],
    "net_worth": [r"net worth", r"total equity", r"shareholders.? funds"],
    "roe": [r"return on equity", r"\broe\b"],
    "roce": [r"return on capital employed", r"\broce\b"],
    "working_capital": [r"working capital"],
    "receivables": [r"trade receivables"],
    "inventory": [r"inventor"],
    "contingent": [r"contingent liabilit"],
    "promoter_holding": [r"promoter.*holding", r"promoter.*shareholding"],
    "related_party": [r"related party"],
}

NUM = r"\(?([\d,]+\.\d+|[\d,]+)\)?"  # (1,234) = negative in Indian filings


@dataclass
class ExtractedFigure:
    metric: str
    fiscal_year: str | None
    raw_value: str
    normalized_cr: float | None
    source_doc: str
    source_page: int

    def cite(self) -> str:
        v = f"₹{self.normalized_cr:,.1f} cr" if self.normalized_cr is not None else self.raw_value
        fy = f"{self.fiscal_year} " if self.fiscal_year else ""
        return f"{fy}{self.metric}: {v} ({self.source_doc}, page {self.source_page})"


@dataclass
class ParseResult:
    figures: list[ExtractedFigure] = field(default_factory=list)
    risks: list[dict] = field(default_factory=list)
    use_of_proceeds: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    pages: int = 0


def _to_cr(num_str: str, unit_hint: str = "") -> float | None:
    try:
        neg = num_str.strip().startswith("(")
        v = float(num_str.replace(",", "").strip("() "))
        h = unit_hint.lower()
        if "lakh" in h:
            v = v / 100.0
        elif "million" in h:
            v = v / 10.0
        if neg:
            v = -v
        return round(v, 2)
    except Exception:
        return None


def _detect_fy(text: str) -> str | None:
    m = re.search(r"FY\s?(\d{2,4})", text, re.I)
    if m:
        y = m.group(1)
        return f"FY{y[-2:]}" if len(y) == 4 else f"FY{y}"
    m = re.search(r"(20\d{2}[-–]?\d{0,2})", text)
    return m.group(1) if m else None


def extract_financials_from_text(pages_text: list[str],
                                 doc_name: str = "RHP") -> ParseResult:
    res = ParseResult(pages=len(pages_text))
    for i, txt in enumerate(pages_text, start=1):
        low = txt.lower()
        fy = _detect_fy(txt)
        for metric, pats in LABEL_PATTERNS.items():
            for p in pats:
                for m in re.finditer(p + r"[^\d]{0,60}" + NUM, low):
                    raw = m.group(1)
                    # unit hint: look 200 chars around
                    ctx = low[max(0, m.start() - 200):m.end() + 200]
                    unit = ""
                    if "lakh" in ctx:
                        unit = "lakh"
                    elif "million" in ctx:
                        unit = "million"
                    res.figures.append(ExtractedFigure(
                        metric=metric, fiscal_year=fy, raw_value=raw,
                        normalized_cr=_to_cr(raw, unit),
                        source_doc=doc_name, source_page=i))
                    break  # one hit per pattern per page
    return res


def extract_risks_from_text(pages_text: list[str],
                            doc_name: str = "RHP") -> list[dict]:
    """Pull numbered risk-factor sentences with page refs."""
    risks: list[dict] = []
    in_risks = False
    for i, txt in enumerate(pages_text, start=1):
        if re.search(r"risk factors", txt, re.I):
            in_risks = True
        if not in_risks:
            continue
        for m in re.finditer(r"(?m)^\s*(\d{1,3})\.\s+([A-Z][^\n]{30,300})", txt):
            risks.append({"category": "Unclassified",
                          "description": m.group(2).strip(),
                          "severity": "medium", "source_doc": doc_name,
                          "source_page": i})
        if len(risks) > 120:
            break
    return risks


def extract_use_of_proceeds(pages_text: list[str],
                            doc_name: str = "RHP") -> list[dict]:
    out: list[dict] = []
    for i, txt in enumerate(pages_text, start=1):
        if re.search(r"objects of the (offer|issue)|use of proceeds", txt, re.I):
            for m in re.finditer(
                    r"(debt repayment|capex|capital expenditure|working capital|"
                    r"acquisition|general corporate purposes|offer for sale|efs|"
                    r"repayment of borrowings)[^\d]{0,80}" + NUM, txt, re.I):
                out.append({"purpose": m.group(1), "amount_raw": m.group(2),
                            "source_doc": doc_name, "source_page": i})
    return out


def parse_pdf(path: str | Path, doc_name: str = "RHP") -> ParseResult:
    """Full PDF pipeline: text -> financials + risks + proceeds."""
    import fitz  # PyMuPDF
    res = ParseResult()
    try:
        doc = fitz.open(path)
        res.pages = len(doc)
        texts = [page.get_text("text") or "" for page in doc]
        doc.close()
    except Exception as e:
        log.error("PDF open failed %s: %s", path, e)
        res.errors.append(f"PDF open failed: {e}")
        return res
    try:
        fin = extract_financials_from_text(texts, doc_name)
        res.figures.extend(fin.figures)
        res.risks.extend(extract_risks_from_text(texts, doc_name))
        res.use_of_proceeds.extend(extract_use_of_proceeds(texts, doc_name))
    except Exception as e:  # pragma: no cover
        log.error("PDF extraction failed: %s", e)
        res.errors.append(f"extraction failed: {e}")
    return res
