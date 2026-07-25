"""Deterministic demo data.

Powers DEMO_MODE so the whole stack runs with zero API keys, and is the same
shape the live clients return. Numbers are illustrative, not real quotes.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

TICKERS = ["AAPL", "MSFT", "NVDA"]

_PROFILES = {
    "AAPL": {
        "name": "Apple Inc.",
        "sector": "Technology",
        "exchange": "NASDAQ",
        "base_price": 212.0,
        "market_cap": 3.22e12,
    },
    "MSFT": {
        "name": "Microsoft Corporation",
        "sector": "Technology",
        "exchange": "NASDAQ",
        "base_price": 458.0,
        "market_cap": 3.41e12,
    },
    "NVDA": {
        "name": "NVIDIA Corporation",
        "sector": "Technology",
        "exchange": "NASDAQ",
        "base_price": 128.0,
        "market_cap": 3.15e12,
    },
}


def _seeded_series(ticker: str, days: int = 260) -> list[dict]:
    """Generate a stable pseudo-random price path (no RNG state, fully
    reproducible from the ticker + day index)."""
    profile = _PROFILES[ticker]
    base = profile["base_price"]
    seed = sum(ord(c) for c in ticker)
    points: list[dict] = []
    today = date.today()
    for i in range(days):
        d = today - timedelta(days=(days - 1 - i))
        # Smooth trend + deterministic wobble.
        trend = 1.0 + 0.12 * (i / days)
        wobble = 0.06 * math.sin((i + seed) / 11.0) + 0.03 * math.sin((i + seed) / 3.0)
        close = round(base * trend * (1 + wobble), 2)
        points.append({"date": d.isoformat(), "close": close})
    return points


def price_series(ticker: str) -> list[dict]:
    return _seeded_series(ticker)


def overview(ticker: str) -> dict:
    profile = _PROFILES[ticker]
    series = _seeded_series(ticker)
    last, prev = series[-1]["close"], series[-2]["close"]
    change = round(last - prev, 2)
    return {
        "ticker": ticker,
        "name": profile["name"],
        "sector": profile["sector"],
        "exchange": profile["exchange"],
        "currency": "USD",
        "price": last,
        "change": change,
        "change_pct": round(change / prev * 100, 2),
        "market_cap": profile["market_cap"],
    }


_NEWS = {
    "AAPL": [
        ("Apple's services revenue hits record as hardware cools", "Reuters", "positive", 0.55),
        ("Analysts trim iPhone unit estimates ahead of launch", "Bloomberg", "negative", -0.35),
        ("Apple expands India manufacturing footprint", "WSJ", "positive", 0.4),
        ("Regulatory scrutiny of App Store fees continues in EU", "FT", "negative", -0.3),
    ],
    "MSFT": [
        ("Azure growth reaccelerates on AI demand", "CNBC", "positive", 0.6),
        ("Microsoft raises Copilot pricing for enterprise", "The Verge", "neutral", 0.1),
        ("Cloud capex guidance spooks some investors", "Bloomberg", "negative", -0.25),
        ("Microsoft closes gaming acquisition integration", "Reuters", "positive", 0.3),
    ],
    "NVDA": [
        ("NVIDIA data-center revenue tops estimates again", "Reuters", "positive", 0.7),
        ("Supply constraints ease for next-gen accelerators", "Bloomberg", "positive", 0.45),
        ("Export-control questions cloud China outlook", "WSJ", "negative", -0.4),
        ("Competition in AI silicon intensifies", "FT", "neutral", -0.1),
    ],
}


def news(ticker: str) -> list[dict]:
    items = []
    now = datetime.now()
    for i, (headline, source, sentiment, score) in enumerate(_NEWS[ticker]):
        items.append(
            {
                "headline": headline,
                "source": source,
                "url": f"https://example.com/{ticker.lower()}/news/{i}",
                "datetime": (now - timedelta(hours=6 * i + 2)).isoformat(),
                "summary": "",
                "sentiment": sentiment,
                "sentiment_score": score,
            }
        )
    return items


# Quarterly earnings. `source` marks provenance — in a live run these would come
# from EDGAR XBRL ("edgar-xbrl") or the AI extractor ("ai-extracted").
_EARNINGS = {
    "AAPL": [
        ("Q3 2025", "2025-06-28", 85.8e9, 21.4e9, 1.40, 1.35),
        ("Q2 2025", "2025-03-29", 90.8e9, 23.6e9, 1.53, 1.50),
        ("Q1 2025", "2024-12-28", 124.3e9, 36.3e9, 2.40, 2.35),
        ("Q4 2024", "2024-09-28", 94.9e9, 14.7e9, 0.97, 1.60),
    ],
    "MSFT": [
        ("Q4 2025", "2025-06-30", 64.7e9, 22.0e9, 2.95, 2.90),
        ("Q3 2025", "2025-03-31", 61.9e9, 21.9e9, 2.94, 2.83),
        ("Q2 2025", "2024-12-31", 62.0e9, 20.4e9, 2.72, 2.65),
        ("Q1 2025", "2024-09-30", 65.6e9, 24.7e9, 3.30, 3.10),
    ],
    "NVDA": [
        ("Q1 2026", "2025-04-27", 44.1e9, 18.8e9, 0.76, 0.75),
        ("Q4 2025", "2025-01-26", 39.3e9, 22.1e9, 0.89, 0.84),
        ("Q3 2025", "2024-10-27", 35.1e9, 19.3e9, 0.78, 0.75),
        ("Q2 2025", "2024-07-28", 30.0e9, 16.6e9, 0.68, 0.64),
    ],
}


def earnings(ticker: str) -> list[dict]:
    rows = []
    for period, end, rev, ni, eps, est in _EARNINGS[ticker]:
        surprise = round((eps - est) / est * 100, 1) if est else None
        rows.append(
            {
                "fiscal_period": period,
                "period_end": end,
                "revenue": rev,
                "net_income": ni,
                "eps": eps,
                "eps_estimate": est,
                "surprise_pct": surprise,
                "source": "demo",
            }
        )
    return rows


# Next scheduled report date, used by the earnings-proximity signal.
def next_earnings_date(ticker: str) -> str:
    return (date.today() + timedelta(days={"AAPL": 12, "MSFT": 5, "NVDA": 21}[ticker])).isoformat()
