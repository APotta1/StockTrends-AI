"""Instrumented Anthropic client.

Every call records tokens, latency, and estimated cost. In an AI-engineering
project the instrumentation IS the point: you cannot route on cost, budget a
pipeline, or reason about escalation if you don't measure per-call spend.

Pricing is USD per 1M tokens. VERIFY these against current Anthropic pricing
before quoting cost-per-filing anywhere public — they change.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..config import get_settings

# USD per 1M tokens (input, output). Verify before relying on the numbers.
_PRICING = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-4-8": (15.00, 75.00),
}


@dataclass
class CallRecord:
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float


@dataclass
class Ledger:
    """Accumulates every call so a pipeline can report total spend/latency."""
    calls: list[CallRecord] = field(default_factory=list)

    def add(self, rec: CallRecord) -> None:
        self.calls.append(rec)

    @property
    def total_cost(self) -> float:
        return round(sum(c.cost_usd for c in self.calls), 6)

    @property
    def total_latency_ms(self) -> float:
        return round(sum(c.latency_ms for c in self.calls), 1)

    def summary(self) -> dict:
        return {
            "num_calls": len(self.calls),
            "total_cost_usd": self.total_cost,
            "total_latency_ms": self.total_latency_ms,
            "by_model": {
                m: sum(1 for c in self.calls if c.model == m)
                for m in {c.model for c in self.calls}
            },
        }


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = _PRICING.get(model, (0.0, 0.0))
    return round((input_tokens * in_rate + output_tokens * out_rate) / 1_000_000, 6)


class InstrumentedClient:
    """Thin wrapper over the Anthropic SDK that appends a CallRecord per call.

    Lazily imports/initializes the SDK so the rest of the app (and the whole
    demo mode) never needs the anthropic package or a key present.
    """

    def __init__(self, ledger: Ledger | None = None) -> None:
        self.ledger = ledger or Ledger()
        self._client = None

    def _sdk(self):
        if self._client is None:
            import anthropic  # imported lazily on purpose

            self._client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
        return self._client

    def complete(self, model: str, system: str, user: str, max_tokens: int = 1024) -> str:
        start = time.perf_counter()
        resp = self._sdk().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        latency_ms = (time.perf_counter() - start) * 1000
        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        self.ledger.add(
            CallRecord(
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                latency_ms=round(latency_ms, 1),
                cost_usd=estimate_cost(model, in_tok, out_tok),
            )
        )
        # Concatenate text blocks.
        return "".join(b.text for b in resp.content if b.type == "text")
