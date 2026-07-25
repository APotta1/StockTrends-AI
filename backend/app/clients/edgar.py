"""SEC EDGAR client — free, no key, the earnings ground-truth source.

EDGAR exposes every XBRL-tagged fact a company has filed. We use it two ways:
  1. As the live source for quarterly earnings figures.
  2. As the labels for the extraction eval harness (XBRL is machine-truth, so we
     can grade an LLM's reading of the human-facing filing against it with zero
     manual annotation).

Rules that will bite you if ignored:
  * A descriptive User-Agent naming a real email is REQUIRED. Missing/blank ->
    403 and a ~10 minute IP block.
  * Rate limit is ~10 requests/second. Be polite.
  * The same accounting concept is tagged with different (sometimes deprecated)
    XBRL tags across years, so we try a list of candidate tags per concept.
"""
from __future__ import annotations

import httpx

from ..config import get_settings

BASE = "https://data.sec.gov"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Candidate XBRL tags per concept, most-preferred first. Companies drift between
# these across filing years; we take the first that has data.
_CONCEPT_TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "net_income": ["NetIncomeLoss"],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
}


def _headers() -> dict:
    return {"User-Agent": get_settings().sec_user_agent, "Accept": "application/json"}


async def cik_for_ticker(ticker: str) -> str | None:
    """Resolve a ticker to a zero-padded 10-digit CIK."""
    async with httpx.AsyncClient(timeout=20, headers=_headers()) as client:
        r = await client.get(_TICKERS_URL)
        r.raise_for_status()
        for entry in r.json().values():
            if entry["ticker"].upper() == ticker.upper():
                return str(entry["cik_str"]).zfill(10)
    return None


async def company_facts(cik: str) -> dict:
    """Full companyfacts payload: every XBRL fact across all filings."""
    async with httpx.AsyncClient(timeout=30, headers=_headers()) as client:
        r = await client.get(f"{BASE}/api/xbrl/companyfacts/CIK{cik}.json")
        r.raise_for_status()
        return r.json()


def _extract_concept(facts: dict, concept: str) -> list[dict]:
    """Pull the quarterly USD (or per-share) values for one concept, trying each
    candidate tag until one yields data."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in _CONCEPT_TAGS[concept]:
        node = us_gaap.get(tag)
        if not node:
            continue
        # Units differ: USD for revenue/income, USD/shares for EPS.
        for _unit, rows in node.get("units", {}).items():
            quarterly = [r for r in rows if r.get("form") in ("10-Q", "10-K") and r.get("fp")]
            if quarterly:
                return quarterly
    return []


async def quarterly_earnings(ticker: str, limit: int = 8) -> list[dict]:
    """Assemble recent quarterly earnings rows from XBRL facts.

    Returns rows tagged source="edgar-xbrl". Raises on network/lookup failure so
    the caller can fall back to demo data.
    """
    cik = await cik_for_ticker(ticker)
    if not cik:
        raise ValueError(f"No CIK found for {ticker}")
    facts = await company_facts(cik)

    # Index each concept by (fiscal-year, fiscal-period) end date.
    by_period: dict[str, dict] = {}
    for concept in ("revenue", "net_income", "eps"):
        for row in _extract_concept(facts, concept):
            key = row.get("end")
            if not key:
                continue
            slot = by_period.setdefault(
                key,
                {"period_end": key, "fp": row.get("fp"), "fy": row.get("fy")},
            )
            slot[concept] = row.get("val")

    rows = []
    for key, slot in sorted(by_period.items(), reverse=True):
        fp, fy = slot.get("fp"), slot.get("fy")
        label = f"{fp} {fy}" if fp and fy else key
        rows.append(
            {
                "fiscal_period": label,
                "period_end": slot["period_end"],
                "revenue": slot.get("revenue"),
                "net_income": slot.get("net_income"),
                "eps": slot.get("eps"),
                "eps_estimate": None,   # estimates aren't in XBRL
                "surprise_pct": None,
                "source": "edgar-xbrl",
            }
        )
    return rows[:limit]
