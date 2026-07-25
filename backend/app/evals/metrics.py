"""Grading with a failure taxonomy.

A single accuracy number hides the bugs that matter. Extracting revenue off by
1000x (a scale error), reading the column next door (adjacent-column), and
inventing a number that isn't in the filing (hallucination) are THREE different
failures with three different fixes. This grader classifies each field's outcome
so a sweep can tell you *how* a prompt fails, not just how often.

Scoring rationale:
  * CORRECT           = +1.0
  * SCALE_ERROR       = -0.25  (right digits, wrong magnitude — partially useful)
  * ADJACENT_COLUMN   = -0.25  (plausible mis-read of a neighboring cell)
  * WRONG             = -0.5
  * HALLUCINATION     = -0.5   (fabricated a value where truth is null)
  * ABSTAIN           =  0.0   (returned null — recoverable, not harmful)
A blank field is recoverable; a fabricated revenue number is not. So abstention
is scored strictly better than hallucination.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Outcome(str, Enum):
    CORRECT = "correct"
    SCALE_ERROR = "scale_error"
    ADJACENT_COLUMN = "adjacent_column"
    WRONG = "wrong"
    HALLUCINATION = "hallucination"
    ABSTAIN = "abstain"


_SCORE = {
    Outcome.CORRECT: 1.0,
    Outcome.SCALE_ERROR: -0.25,
    Outcome.ADJACENT_COLUMN: -0.25,
    Outcome.WRONG: -0.5,
    Outcome.HALLUCINATION: -0.5,
    Outcome.ABSTAIN: 0.0,
}

# Relative tolerance for "correct" — filings round, XBRL is exact.
_REL_TOL = 0.01


def _rel_close(a: float, b: float, tol: float = _REL_TOL) -> bool:
    if b == 0:
        return abs(a) < 1e-9
    return abs(a - b) / abs(b) <= tol


def classify_field(predicted, truth, neighbors: list | None = None) -> Outcome:
    """Classify one field's prediction against ground truth.

    `neighbors` = other true values from the same row (e.g. the adjacent
    column's number), used to detect adjacent-column mis-reads.
    """
    # Truth is null: only abstaining is acceptable.
    if truth is None:
        return Outcome.ABSTAIN if predicted is None else Outcome.HALLUCINATION

    # Model abstained where a value existed.
    if predicted is None:
        return Outcome.ABSTAIN

    try:
        p, t = float(predicted), float(truth)
    except (TypeError, ValueError):
        return Outcome.WRONG

    if _rel_close(p, t):
        return Outcome.CORRECT

    # Scale error: off by a clean power of 1000 (thousands/millions/billions).
    if t != 0:
        for factor in (1e3, 1e6, 1e9, 1e-3, 1e-6, 1e-9):
            if _rel_close(p, t * factor):
                return Outcome.SCALE_ERROR

    # Adjacent-column: matches a different true value from the same row.
    for n in neighbors or []:
        if n is not None and n != truth:
            try:
                if _rel_close(p, float(n)):
                    return Outcome.ADJACENT_COLUMN
            except (TypeError, ValueError):
                continue

    return Outcome.WRONG


@dataclass
class GradeResult:
    per_field: dict            # field -> Outcome
    score: float               # mean field score
    accuracy: float            # fraction CORRECT
    taxonomy: dict             # Outcome -> count


def grade_example(predicted: dict, truth: dict, fields: tuple[str, ...]) -> GradeResult:
    """Grade all fields of one example.

    Each field is checked against its own truth, with the other fields' truths
    passed as neighbors for adjacent-column detection.
    """
    per_field: dict = {}
    taxonomy: dict = {o: 0 for o in Outcome}
    for f in fields:
        neighbors = [truth.get(g) for g in fields if g != f]
        outcome = classify_field(predicted.get(f), truth.get(f), neighbors)
        per_field[f] = outcome
        taxonomy[outcome] += 1

    n = len(fields)
    score = sum(_SCORE[o] for o in per_field.values()) / n if n else 0.0
    accuracy = taxonomy[Outcome.CORRECT] / n if n else 0.0
    return GradeResult(
        per_field=per_field,
        score=round(score, 4),
        accuracy=round(accuracy, 4),
        taxonomy={o.value: c for o, c in taxonomy.items() if c},
    )


def aggregate(results: list[GradeResult]) -> dict:
    """Roll up a list of graded examples into a sweep summary."""
    if not results:
        return {"n": 0}
    total_taxonomy: dict = {}
    for r in results:
        for k, c in r.taxonomy.items():
            total_taxonomy[k] = total_taxonomy.get(k, 0) + c
    return {
        "n": len(results),
        "mean_score": round(sum(r.score for r in results) / len(results), 4),
        "accuracy": round(sum(r.accuracy for r in results) / len(results), 4),
        "taxonomy": total_taxonomy,
    }
