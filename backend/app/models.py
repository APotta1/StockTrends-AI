"""Pydantic response schemas shared across the API.

These are the contract the frontend depends on. Keep field names stable.
"""
from __future__ import annotations

from pydantic import BaseModel


class Overview(BaseModel):
    ticker: str
    name: str
    sector: str
    exchange: str
    currency: str
    price: float
    change: float          # absolute change vs. previous close
    change_pct: float      # percent change vs. previous close
    market_cap: float | None = None


class PricePoint(BaseModel):
    date: str              # ISO date
    close: float


class Trend(BaseModel):
    ticker: str
    points: list[PricePoint]
    sma_50: float | None = None
    sma_200: float | None = None
    range_low_52w: float | None = None
    range_high_52w: float | None = None


class NewsItem(BaseModel):
    headline: str
    source: str
    url: str
    datetime: str          # ISO timestamp
    summary: str = ""
    sentiment: str = "neutral"   # positive | neutral | negative
    sentiment_score: float = 0.0  # -1..1


class EarningsRow(BaseModel):
    fiscal_period: str     # e.g. "Q2 2025"
    period_end: str        # ISO date
    revenue: float | None = None
    net_income: float | None = None
    eps: float | None = None
    eps_estimate: float | None = None
    surprise_pct: float | None = None
    # Provenance: where each headline number was sourced from.
    source: str = "demo"   # "edgar-xbrl" | "ai-extracted" | "demo"


class Signal(BaseModel):
    """A single transparent context flag.

    Deliberately NOT a buy/sell call. Each flag reports an observable condition,
    the raw numbers behind it, and a caveat naming what it does not tell you.
    """
    key: str
    label: str
    level: str             # info | watch | caution
    detail: str            # plain-English explanation with the arithmetic
    inputs: dict           # the raw numbers, so the UI can show the math
    caveat: str


class SignalReport(BaseModel):
    ticker: str
    as_of: str
    signals: list[Signal]
    disclaimer: str
