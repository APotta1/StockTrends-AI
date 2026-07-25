"""Market data + news client (Finnhub free tier).

Free tier: ~60 req/min, US quotes, company news, basic fundamentals. No key ->
callers should stay in demo mode. Kept deliberately thin: the app's design
assumes you backfill into your own store rather than hammering this live.
"""
from __future__ import annotations

from datetime import date, timedelta

import httpx

from ..config import get_settings

BASE = "https://finnhub.io/api/v1"


async def _get(path: str, params: dict) -> dict | list:
    settings = get_settings()
    params = {**params, "token": settings.finnhub_api_key}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{BASE}{path}", params=params)
        r.raise_for_status()
        return r.json()


async def quote(ticker: str) -> dict:
    """Latest quote: current, previous close, etc."""
    return await _get("/quote", {"symbol": ticker})  # type: ignore[return-value]


async def company_news(ticker: str, days: int = 7) -> list[dict]:
    """Recent company news, normalized to the app's NewsItem shape.

    Sentiment is left neutral here — scoring it is the AI layer's job, not the
    data client's.
    """
    to = date.today()
    frm = to - timedelta(days=days)
    raw = await _get(
        "/company-news",
        {"symbol": ticker, "from": frm.isoformat(), "to": to.isoformat()},
    )
    items = []
    for a in raw[:20]:  # type: ignore[index]
        items.append(
            {
                "headline": a.get("headline", ""),
                "source": a.get("source", ""),
                "url": a.get("url", ""),
                "datetime": _epoch_to_iso(a.get("datetime", 0)),
                "summary": a.get("summary", ""),
                "sentiment": "neutral",
                "sentiment_score": 0.0,
            }
        )
    return items


def _epoch_to_iso(epoch: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
