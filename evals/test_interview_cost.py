"""Deterministic tests for complete-interview cost evidence."""

from decimal import Decimal

import pytest

from evals.interview_cost import InterviewCostReport, InterviewCostRun
from evals.run import percentile_nearest_rank

pytestmark = pytest.mark.eval


def _run(sequence: int, cost_cny: float) -> InterviewCostRun:
    return InterviewCostRun(
        sequence=sequence,
        direction="backend",
        model_calls=6,
        input_tokens=1000,
        output_tokens=2000,
        follow_up_calls=1,
        cost_usd=round(cost_cny / 7.2, 6),
        cost_cny=cost_cny,
        latency_ms=1000,
    )


def test_interview_cost_uses_p95_and_threshold() -> None:
    report = InterviewCostReport(
        provider="deepseek",
        model="deepseek-v4-pro",
        tier="REASONING",
        prompt_versions={},
        generated_at="2026-10-18T00:00:00+00:00",
        runs=(_run(1, 0.5), _run(2, 1.0), _run(3, 3.5)),
    )

    assert report.cost_p95_cny == 3.5
    assert report.release_ready is False
    payload = report.as_dict()
    assert payload["threshold_cny"] == 3.0
    assert payload["total_runs"] == 3
    assert payload["release_ready"] is False
    assert payload["follow_up_coverage_complete"] is True


def test_interview_cost_requires_measurements_and_reports_ready_below_threshold() -> None:
    empty = InterviewCostReport(
        provider="deepseek",
        model="deepseek-v4-pro",
        tier="REASONING",
        prompt_versions={},
        generated_at="2026-10-18T00:00:00+00:00",
        runs=(),
    )
    measured = InterviewCostReport(
        provider="deepseek",
        model="deepseek-v4-pro",
        tier="REASONING",
        prompt_versions={},
        generated_at="2026-10-18T00:00:00+00:00",
        runs=(_run(1, 2.99),),
        threshold_cny=Decimal("3.00"),
    )

    assert empty.release_ready is False
    assert measured.release_ready is True


def test_nearest_rank_p95_is_conservative_for_small_samples() -> None:
    assert percentile_nearest_rank([0.5, 1.0, 3.5]) == 3.5
    assert percentile_nearest_rank([1.0, 2.0]) == 2.0
    assert percentile_nearest_rank([]) == 0.0


def test_interview_cost_without_follow_up_coverage_is_not_release_ready() -> None:
    no_follow_up = InterviewCostRun(
        sequence=1,
        direction="backend",
        model_calls=6,
        input_tokens=1000,
        output_tokens=2000,
        follow_up_calls=0,
        cost_usd=0.1,
        cost_cny=0.72,
        latency_ms=1000,
    )
    report = InterviewCostReport(
        provider="deepseek",
        model="deepseek-v4-pro",
        tier="REASONING",
        prompt_versions={},
        generated_at="2026-10-18T00:00:00+00:00",
        runs=(no_follow_up,),
    )

    assert report.follow_up_coverage_complete is False
    assert report.release_ready is False


def test_cost_benchmark_answer_covers_concrete_recovery_mechanisms() -> None:
    from evals.interview_cost import ANSWER_TEXT, FOLLOW_UP_ANSWER_TEXT

    assert "幂等键" in ANSWER_TEXT
    assert "fencing token" in ANSWER_TEXT
    assert "指数退避" in ANSWER_TEXT
    assert "trace" in ANSWER_TEXT
    assert "fencing token" in FOLLOW_UP_ANSWER_TEXT
    assert len(FOLLOW_UP_ANSWER_TEXT) >= 180
