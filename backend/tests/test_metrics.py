"""Tests for the failure-taxonomy grader.

These pin the behavior that makes the eval meaningful: that a scale error, an
adjacent-column read, a hallucination, and an abstention are each classified
distinctly and scored in the right order.
"""
from app.evals.metrics import Outcome, aggregate, classify_field, grade_example

FIELDS = ("revenue", "net_income", "eps")


def test_correct_within_tolerance():
    assert classify_field(90_830_000_000, 90_830_000_000) is Outcome.CORRECT
    # filings round; within 1% is still correct
    assert classify_field(90_800_000_000, 90_830_000_000) is Outcome.CORRECT


def test_scale_error_detected():
    # off by 1e6 (read "in millions" as raw)
    assert classify_field(90_830, 90_830_000_000) is Outcome.SCALE_ERROR
    # off by 1000 the other way
    assert classify_field(90_830_000_000_000, 90_830_000_000) is Outcome.SCALE_ERROR


def test_adjacent_column():
    # predicted revenue equals the row's net_income (neighbor)
    out = classify_field(23_636_000_000, 90_830_000_000, neighbors=[23_636_000_000, 1.53])
    assert out is Outcome.ADJACENT_COLUMN


def test_hallucination_vs_abstain():
    # truth is null: fabricating a value is a hallucination, null is an abstain
    assert classify_field(123, None) is Outcome.HALLUCINATION
    assert classify_field(None, None) is Outcome.ABSTAIN


def test_abstain_when_value_missing():
    assert classify_field(None, 90_830_000_000) is Outcome.ABSTAIN


def test_wrong_is_last_resort():
    assert classify_field(42, 90_830_000_000) is Outcome.WRONG


def test_scoring_order():
    """Abstention must score strictly better than hallucination."""
    truth = {"revenue": None, "net_income": 100, "eps": 1.0}
    abstain = grade_example({"revenue": None, "net_income": 100, "eps": 1.0}, truth, FIELDS)
    hallucinate = grade_example({"revenue": 5, "net_income": 100, "eps": 1.0}, truth, FIELDS)
    assert abstain.score > hallucinate.score


def test_aggregate_rolls_up():
    truth = {"revenue": 100, "net_income": 50, "eps": 1.0}
    perfect = grade_example(dict(truth), truth, FIELDS)
    summary = aggregate([perfect, perfect])
    assert summary["n"] == 2
    assert summary["accuracy"] == 1.0
    assert summary["taxonomy"]["correct"] == 6
