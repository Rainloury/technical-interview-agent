"""Contract tests for the eval runner itself."""

from pathlib import Path

import pytest

from evals.run import EvalReport, EvalResult, compare_with_baseline, run_suite

pytestmark = pytest.mark.eval


def test_seed_eval_suite_passes() -> None:
    report = run_suite()

    assert report.total == 3
    assert report.passed == report.total
    assert report.pass_rate == 1.0
    agent_case = next(
        result for result in report.results if result.case_id == "agent-tool-selection"
    )
    assert agent_case.passed is True
    qa_case = next(result for result in report.results if result.case_id == "qa-evidence-boundary")
    assert qa_case.passed is True


def test_pass_rate_regression_over_fifteen_percent_is_rejected(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        '{"pass_rate": 1.0, "total_cost_cny": 0.0}\n',
        encoding="utf-8",
    )
    report = EvalReport(
        results=(
            EvalResult(case_id="a", passed=True, cost_cny=0.0),
            EvalResult(case_id="b", passed=True, cost_cny=0.0),
            EvalResult(case_id="c", passed=False, cost_cny=0.0),
        ),
        generated_at="2026-10-17T00:00:00+00:00",
    )

    regressions = compare_with_baseline(report, baseline)

    assert any("pass_rate regressed" in reason for reason in regressions)


def test_cost_regression_over_fifteen_percent_is_rejected(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        '{"pass_rate": 1.0, "total_cost_cny": 1.0}\n',
        encoding="utf-8",
    )
    report = EvalReport(
        results=(EvalResult(case_id="a", passed=True, cost_cny=1.16),),
        generated_at="2026-10-17T00:00:00+00:00",
    )

    regressions = compare_with_baseline(report, baseline)

    assert any("total_cost_cny regressed" in reason for reason in regressions)
