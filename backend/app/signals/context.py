"""Context-flag engine — the honest version of a 'when to buy' feature.

Deliberately NOT a predictive model and NOT a buy/sell signal. Each flag:
  * reports an OBSERVABLE condition (no forecasting),
  * exposes the raw numbers so the UI can show the arithmetic,
  * carries a caveat naming what it does NOT tell you.

Why build it this way: in an interview, "I deliberately did not ship a signal,
here is the reasoning" is a far stronger answer than defending a backtest that
leaks look-ahead bias. Everything here is deterministic and explainable.
"""
from __future__ import annotations

import statistics
from datetime import date


def _sma(closes: list[float], window: int) -> float | None:
    if len(closes) < window:
        return None
    return round(statistics.fmean(closes[-window:]), 2)


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


DISCLAIMER = (
    "These are transparent context flags, not investment advice and not a "
    "prediction of price. Each flag shows the numbers behind it and what it "
    "does not account for. Do your own research."
)


def build_signals(
    ticker: str,
    closes: list[float],
    next_earnings: str | None,
    earnings_rows: list[dict],
    as_of: str | None = None,
) -> dict:
    """Assemble the flag list from price history + earnings context."""
    as_of = as_of or date.today().isoformat()
    signals: list[dict] = []
    last = closes[-1] if closes else None

    # 1) Price vs. its own moving averages -------------------------------
    sma50, sma200 = _sma(closes, 50), _sma(closes, 200)
    if last and sma50 and sma200:
        above50 = last > sma50
        above200 = last > sma200
        if above50 and above200:
            level, verb = "info", "above"
        elif not above50 and not above200:
            level, verb = "watch", "below"
        else:
            level, verb = "watch", "mixed vs."
        signals.append(
            {
                "key": "moving_averages",
                "label": "Price vs. moving averages",
                "level": level,
                "detail": (
                    f"Last close ${last:,.2f} is {verb} the 50-day (${sma50:,.2f}) "
                    f"and 200-day (${sma200:,.2f}) averages."
                ),
                "inputs": {"last": last, "sma_50": sma50, "sma_200": sma200},
                "caveat": (
                    "Moving averages are lagging by construction; being above or "
                    "below them says nothing about future direction."
                ),
            }
        )

    # 2) Position within the 52-week range -------------------------------
    if last and len(closes) >= 20:
        window = closes[-252:] if len(closes) >= 252 else closes
        lo, hi = min(window), max(window)
        if hi > lo:
            pct = (last - lo) / (hi - lo) * 100
            level = "caution" if pct >= 90 else "watch" if pct <= 15 else "info"
            signals.append(
                {
                    "key": "range_position",
                    "label": "Position in 52-week range",
                    "level": level,
                    "detail": (
                        f"Trading at the {_ordinal(round(pct))} percentile of its "
                        f"~52-week range (${lo:,.2f}–${hi:,.2f})."
                    ),
                    "inputs": {"last": last, "low_52w": round(lo, 2), "high_52w": round(hi, 2),
                               "percentile": round(pct, 1)},
                    "caveat": (
                        "Range position is descriptive only — cheap stocks get "
                        "cheaper and strong ones keep making highs."
                    ),
                }
            )

    # 3) Realized volatility (recent daily moves) ------------------------
    if len(closes) >= 21:
        rets = [(closes[i] / closes[i - 1] - 1) for i in range(-20, 0)]
        vol = statistics.pstdev(rets) * 100
        level = "caution" if vol >= 3.5 else "info"
        signals.append(
            {
                "key": "volatility",
                "label": "Recent volatility",
                "level": level,
                "detail": (
                    f"20-day daily-return volatility is {vol:.2f}%. Higher volatility "
                    f"means wider swings in both directions."
                ),
                "inputs": {"daily_vol_pct": round(vol, 2), "window_days": 20},
                "caveat": (
                    "Volatility describes past dispersion, not risk of loss, and "
                    "clusters — calm and stormy periods both persist."
                ),
            }
        )

    # 4) Earnings proximity ----------------------------------------------
    if next_earnings:
        try:
            days_out = (date.fromisoformat(next_earnings) - date.fromisoformat(as_of)).days
        except ValueError:
            days_out = None
        if days_out is not None and 0 <= days_out <= 14:
            # Historical average absolute EPS surprise, if available.
            surprises = [abs(r["surprise_pct"]) for r in earnings_rows
                         if r.get("surprise_pct") is not None]
            avg_surprise = round(statistics.fmean(surprises), 1) if surprises else None
            detail = f"Next earnings report is ~{days_out} day(s) away ({next_earnings})."
            if avg_surprise is not None:
                detail += f" Past EPS surprises have averaged {avg_surprise}% in absolute size."
            signals.append(
                {
                    "key": "earnings_proximity",
                    "label": "Earnings coming up",
                    "level": "caution",
                    "detail": detail,
                    "inputs": {"next_earnings": next_earnings, "days_out": days_out,
                               "avg_abs_surprise_pct": avg_surprise},
                    "caveat": (
                        "Earnings dates concentrate risk: single-day moves around "
                        "reports are large and not predictable from this flag."
                    ),
                }
            )

    # 5) Margin trend (net income / revenue over reported quarters) ------
    margins = []
    for r in earnings_rows:
        rev, ni = r.get("revenue"), r.get("net_income")
        if rev and ni:
            margins.append((r.get("fiscal_period", ""), ni / rev * 100))
    if len(margins) >= 2:
        newest, oldest = margins[0][1], margins[-1][1]
        direction = "widening" if newest > oldest else "narrowing" if newest < oldest else "flat"
        signals.append(
            {
                "key": "margin_trend",
                "label": "Net-margin trend",
                "level": "info",
                "detail": (
                    f"Net margin is {direction}: {oldest:.1f}% ({margins[-1][0]}) → "
                    f"{newest:.1f}% ({margins[0][0]})."
                ),
                "inputs": {"oldest_pct": round(oldest, 1), "newest_pct": round(newest, 1),
                           "quarters": len(margins)},
                "caveat": (
                    "A few quarters is a short window; margins move with one-off "
                    "items, seasonality, and accounting choices."
                ),
            }
        )

    return {
        "ticker": ticker,
        "as_of": as_of,
        "signals": signals,
        "disclaimer": DISCLAIMER,
    }
