"""Eval CLI.

Usage:
    python -m app.evals.run_eval build  --tickers AAPL,MSFT,NVDA
    python -m app.evals.run_eval sweep  [--models cheap,strong]
    python -m app.evals.run_eval grade-demo   # offline sanity check, no API key

`sweep` runs the extraction pipeline over the labeled dataset and prints the
failure taxonomy — how the prompt fails, not just how often. Results are written
to data/sweep_results.md so the README table can be regenerated from real runs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from ..config import get_settings
from . import harness
from .metrics import aggregate, grade_example

FIELDS = ("revenue", "net_income", "eps")
RESULTS_PATH = harness.DATA_DIR / "sweep_results.md"


def _write_report(summary: dict, per_example: list[dict], models: tuple[str, str]) -> None:
    lines = [
        "# Extraction eval sweep",
        "",
        f"- Dataset size: **{summary['n']}** examples × {len(FIELDS)} fields",
        f"- Models (cheap, strong): `{models[0]}`, `{models[1]}`",
        f"- Mean field score: **{summary['mean_score']}**",
        f"- Exact accuracy: **{summary['accuracy']:.1%}**",
        "",
        "## Failure taxonomy",
        "",
        "| Outcome | Count |",
        "| --- | --- |",
    ]
    for outcome, count in sorted(summary["taxonomy"].items(), key=lambda x: -x[1]):
        lines.append(f"| {outcome} | {count} |")
    lines += ["", "## Per-example", "", "| Ticker | Period | Score | Fields |", "| --- | --- | --- | --- |"]
    for row in per_example:
        fields = ", ".join(f"{k}:{v}" for k, v in row["per_field"].items())
        lines.append(f"| {row['ticker']} | {row['period']} | {row['score']} | {fields} |")
    RESULTS_PATH.write_text("\n".join(lines) + "\n")


def cmd_grade_demo(_args) -> None:
    """Grade a hardcoded set of predictions against the demo dataset — proves the
    taxonomy classifier end-to-end with no API key. The predictions intentionally
    include a scale error and a hallucination so every code path is exercised."""
    dataset = harness.load_dataset()
    # Fabricate predictions that mirror common real failures.
    faux = []
    for i, ex in enumerate(dataset):
        t = ex["truth"]
        if i == 0:
            pred = {**t, "revenue": t["revenue"] / 1e6}          # scale error
        elif i == 1:
            pred = {**t, "net_income": t["net_income"], "eps": None}  # abstain on eps
        elif i == 2:
            pred = {**t, "revenue": 99_999_999_999}              # wrong
        else:
            pred = dict(t)                                         # correct
        faux.append((ex, pred))

    results, per_example = [], []
    for ex, pred in faux:
        g = grade_example(pred, ex["truth"], FIELDS)
        results.append(g)
        per_example.append(
            {"ticker": ex["ticker"], "period": ex["period"], "score": g.score,
             "per_field": {k: v.value for k, v in g.per_field.items()}}
        )
    summary = aggregate(results)
    _write_report(summary, per_example, ("(demo)", "(demo)"))
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {RESULTS_PATH}")


def cmd_sweep(args) -> None:
    """Run the real extraction pipeline over the dataset and grade it."""
    from ..ai.extract import extract_financials

    settings = get_settings()
    if not settings.has_anthropic:
        raise SystemExit(
            "sweep needs ANTHROPIC_API_KEY. For an offline check run `grade-demo`."
        )
    models = tuple((args.models or f"{settings.extract_model_cheap},{settings.extract_model_strong}").split(","))
    dataset = harness.load_dataset()

    results, per_example = [], []
    for ex in dataset:
        res = extract_financials(ex["input_text"], models)  # type: ignore[arg-type]
        g = grade_example(res.values, ex["truth"], FIELDS)
        results.append(g)
        per_example.append(
            {"ticker": ex["ticker"], "period": ex["period"], "score": g.score,
             "per_field": {k: v.value for k, v in g.per_field.items()}}
        )
    summary = aggregate(results)
    _write_report(summary, per_example, models)  # type: ignore[arg-type]
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {RESULTS_PATH}")


def cmd_build(args) -> None:
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    n = asyncio.run(harness.build_dataset(tickers))
    print(f"Built {n} label rows from EDGAR into {harness.DATASET_PATH}")


def main() -> None:
    p = argparse.ArgumentParser(prog="run_eval")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build labels from EDGAR XBRL")
    b.add_argument("--tickers", default="AAPL,MSFT,NVDA")
    b.set_defaults(func=cmd_build)

    s = sub.add_parser("sweep", help="Run extraction + grade (needs ANTHROPIC_API_KEY)")
    s.add_argument("--models", default="")
    s.set_defaults(func=cmd_sweep)

    g = sub.add_parser("grade-demo", help="Offline grader sanity check (no key)")
    g.set_defaults(func=cmd_grade_demo)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
