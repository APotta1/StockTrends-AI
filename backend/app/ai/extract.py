"""Extraction pipeline.

Two jobs:
  1. extract_financials(): read a human-facing filing (HTML) and pull structured
     numbers, with a confidence-driven router that escalates only hard fields to
     the stronger model.
  2. score_sentiment(): label news headlines.

The interesting engineering is in html_to_text(): financial filings put a units
header like "(in millions)" ABOVE the table it governs. If you flatten the HTML
by grouping all tables and all paragraphs separately, that header gets divorced
from its figures and the model silently reads the wrong scale. So we traverse in
strict document order.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from .client import InstrumentedClient, Ledger

# --- Prompt versions ------------------------------------------------------
# Version the prompt string so eval runs are attributable to a prompt revision.
EXTRACT_PROMPT_VERSION = "v3"

_SYSTEM = """You extract structured financial figures from SEC filing text.
Return ONLY minified JSON with keys: revenue, net_income, eps, and for each a
sibling <key>_confidence in [0,1] and <key>_source_line (the verbatim line you
read it from). Respect the scale stated in the filing (e.g. "in millions").
If a value is genuinely absent, use null and confidence 0. Never guess."""

_USER_TMPL = """Filing excerpt:
---
{text}
---
Extract revenue, net_income (net income), and eps (diluted EPS if present).
Report each value in absolute dollars (convert "in millions"/"in thousands").
Return the JSON now."""


class _OrderedText(HTMLParser):
    """Flatten HTML to text in document order, so a units header stays adjacent
    to the table it introduces. Block-level tags and table rows force newlines;
    cells are separated by tabs."""

    _BLOCK = {"p", "div", "tr", "br", "li", "h1", "h2", "h3", "table", "thead", "tbody"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "td" or tag == "th":
            self.parts.append("\t")
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.parts.append(text)


def html_to_text(html: str) -> str:
    parser = _OrderedText()
    parser.feed(html)
    raw = "".join(parser.parts)
    # Collapse runs of blank lines / stray tabs but keep line structure.
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
    return "\n".join(ln for ln in lines if ln)


# --- Extraction + router --------------------------------------------------

_FIELDS = ("revenue", "net_income", "eps")
_CONFIDENCE_FLOOR = 0.75  # below this, escalate the field to the strong model


@dataclass
class ExtractionResult:
    values: dict            # field -> number|None
    confidence: dict        # field -> float
    source_line: dict       # field -> str
    escalated: list         # fields that were re-run on the strong model
    ledger_summary: dict


def _parse_json(raw: str) -> dict:
    # Models sometimes wrap JSON in prose or fences; grab the first object.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in model output: {raw[:200]}")
    return json.loads(match.group(0))


def extract_financials(html: str, models: tuple[str, str]) -> ExtractionResult:
    """Run cheap-first extraction, escalating only low-confidence fields.

    `models` is (cheap, strong). Requires a real Anthropic key; callers in demo
    mode should not reach here.
    """
    cheap, strong = models
    text = html_to_text(html)
    ledger = Ledger()
    client = InstrumentedClient(ledger)

    first = _parse_json(client.complete(cheap, _SYSTEM, _USER_TMPL.format(text=text)))

    values, confidence, source_line, escalated = {}, {}, {}, []
    for f in _FIELDS:
        values[f] = first.get(f)
        confidence[f] = float(first.get(f"{f}_confidence", 0.0) or 0.0)
        source_line[f] = first.get(f"{f}_source_line", "")

    # Escalate the whole excerpt once if any field is under the floor. (Re-running
    # the full excerpt is simpler and, for a short excerpt, barely costlier than
    # field-by-field prompts.)
    if any(confidence[f] < _CONFIDENCE_FLOOR for f in _FIELDS):
        second = _parse_json(client.complete(strong, _SYSTEM, _USER_TMPL.format(text=text)))
        for f in _FIELDS:
            if confidence[f] < _CONFIDENCE_FLOOR:
                values[f] = second.get(f, values[f])
                confidence[f] = float(second.get(f"{f}_confidence", confidence[f]) or confidence[f])
                source_line[f] = second.get(f"{f}_source_line", source_line[f])
                escalated.append(f)

    return ExtractionResult(
        values=values,
        confidence=confidence,
        source_line=source_line,
        escalated=escalated,
        ledger_summary=ledger.summary(),
    )


# --- News sentiment -------------------------------------------------------

_SENTIMENT_SYSTEM = """You score financial news sentiment for an investor.
Return ONLY minified JSON: {"score": <float -1..1>, "label": "positive|neutral|negative"}.
Positive = likely good for the stock; negative = likely bad. Be calibrated."""


def score_sentiment(headline: str, ledger: Ledger, model: str) -> dict:
    client = InstrumentedClient(ledger)
    raw = client.complete(model, _SENTIMENT_SYSTEM, f"Headline: {headline}")
    data = _parse_json(raw)
    score = max(-1.0, min(1.0, float(data.get("score", 0.0))))
    label = data.get("label", "neutral")
    return {"sentiment": label, "sentiment_score": round(score, 3)}
