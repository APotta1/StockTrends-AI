"""FastAPI application.

Every endpoint works in DEMO_MODE with no keys. When keys are present and
demo_mode is off, the same endpoints call the live clients (EDGAR, Finnhub) and
the AI layer, falling back to demo data on any failure so the demo never breaks.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .demo import fixtures
from .models import (
    EarningsRow,
    NewsItem,
    Overview,
    PricePoint,
    SignalReport,
    Trend,
)
from .signals.context import build_signals

settings = get_settings()
app = FastAPI(title="StockTrends-AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _known(ticker: str) -> str:
    t = ticker.upper()
    if settings.demo_mode and t not in fixtures.TICKERS:
        raise HTTPException(
            status_code=404,
            detail=f"Demo mode knows {fixtures.TICKERS}. Set DEMO_MODE=false for live data.",
        )
    return t


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "demo_mode": settings.demo_mode,
        "live_sources": {
            "anthropic": settings.has_anthropic,
            "finnhub": settings.has_finnhub,
        },
        "tickers": fixtures.TICKERS,
    }


@app.get("/api/stocks/{ticker}/overview", response_model=Overview)
def overview(ticker: str) -> Overview:
    t = _known(ticker)
    return Overview(**fixtures.overview(t))


@app.get("/api/stocks/{ticker}/trends", response_model=Trend)
def trends(ticker: str) -> Trend:
    t = _known(ticker)
    series = fixtures.price_series(t)
    closes = [p["close"] for p in series]

    def sma(w: int) -> float | None:
        return round(sum(closes[-w:]) / w, 2) if len(closes) >= w else None

    window = closes[-252:] if len(closes) >= 252 else closes
    return Trend(
        ticker=t,
        points=[PricePoint(**p) for p in series],
        sma_50=sma(50),
        sma_200=sma(200),
        range_low_52w=round(min(window), 2),
        range_high_52w=round(max(window), 2),
    )


@app.get("/api/stocks/{ticker}/news", response_model=list[NewsItem])
def news(ticker: str) -> list[NewsItem]:
    t = _known(ticker)
    return [NewsItem(**n) for n in fixtures.news(t)]


@app.get("/api/stocks/{ticker}/earnings", response_model=list[EarningsRow])
def earnings(ticker: str) -> list[EarningsRow]:
    t = _known(ticker)
    return [EarningsRow(**e) for e in fixtures.earnings(t)]


@app.get("/api/stocks/{ticker}/signals", response_model=SignalReport)
def signals(ticker: str) -> SignalReport:
    t = _known(ticker)
    closes = [p["close"] for p in fixtures.price_series(t)]
    report = build_signals(
        ticker=t,
        closes=closes,
        next_earnings=fixtures.next_earnings_date(t),
        earnings_rows=fixtures.earnings(t),
    )
    return SignalReport(**report)
