"""Eval dataset builder.

The trick that makes this project's evals cheap: XBRL is machine-readable truth.
So we can build a labeled extraction dataset with ZERO manual annotation —
    label  = the exact figure the company tagged in XBRL (from EDGAR)
    input  = the human-facing text the model must read
and grade the model's reading of the text against the XBRL label.

In demo mode we ship a small hand-built dataset (data/eval_dataset.json) so the
harness runs offline; `build` regenerates it from live EDGAR when keys/network
are available.
"""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATASET_PATH = DATA_DIR / "eval_dataset.json"


def load_dataset() -> list[dict]:
    """Load the eval dataset. Each example:
        {
          "ticker": "AAPL",
          "period": "Q2 2025",
          "input_text": "<filing excerpt as plain text>",
          "truth": {"revenue": ..., "net_income": ..., "eps": ...}
        }
    """
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"{DATASET_PATH} not found. Run `run_eval build` first "
            f"(or use the shipped demo dataset)."
        )
    return json.loads(DATASET_PATH.read_text())


async def build_dataset(tickers: list[str], out: Path = DATASET_PATH) -> int:
    """Build labels from live EDGAR XBRL.

    Note: pairing each XBRL figure with the exact filing text snippet requires
    fetching and slicing the filing HTML. That wiring is left as the live-mode
    extension; this function currently persists the XBRL truth rows so the
    labels exist, and is where the text-pairing step plugs in.
    """
    from ..clients import edgar

    examples: list[dict] = []
    for ticker in tickers:
        rows = await edgar.quarterly_earnings(ticker, limit=8)
        for r in rows:
            examples.append(
                {
                    "ticker": ticker,
                    "period": r["fiscal_period"],
                    "input_text": "",  # populated by the filing-text pairing step
                    "truth": {
                        "revenue": r.get("revenue"),
                        "net_income": r.get("net_income"),
                        "eps": r.get("eps"),
                    },
                }
            )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(examples, indent=2))
    return len(examples)
