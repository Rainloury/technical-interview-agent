"""Contract tests for the eval runner itself."""

from pathlib import Path

import pytest
from app.interview_contracts import InterviewScoringOutput

from evals.provider_matrix import MatrixCase, _validate_result
from evals.run import (
    EvalCase,
    EvalReport,
    EvalResult,
    ReleaseGate,
    compare_with_baseline,
    load_cases,
    run_suite,
    validate_release_matrix,
)

pytestmark = pytest.mark.eval


def test_seed_eval_suite_passes() -> None:
    report = run_suite()

    assert report.total == 7
    assert report.passed == report.total
    assert report.pass_rate == 1.0
    agent_case = next(
        result for result in report.results if result.case_id == "agent-tool-selection"
    )
    assert agent_case.passed is True
    qa_case = next(result for result in report.results if result.case_id == "qa-evidence-boundary")
    assert qa_case.passed is True
    threshold_cases = [
        result for result in report.results if result.case_id.startswith("interview-")
    ]
    assert len(threshold_cases) == 4
    assert all(result.passed for result in threshold_cases)


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


def test_release_matrix_reports_missing_required_cases() -> None:
    gate = ReleaseGate(
        total_cases=2,
        cases_per_direction=1,
        shared_security_cases=1,
        overall_pass_rate=0.9,
        direction_pass_rate=0.85,
        category_pass_rate=0.8,
        critical_pass_rate=1.0,
    )
    cases = (
        EvalCase(
            case_id="backend-1",
            kind="interview_threshold",
            description="backend",
            input={"score": 90},
            expect={},
            forbidden={},
            cost_cny=0.5,
            category="interview",
            direction="backend",
            critical=True,
        ),
        EvalCase(
            case_id="shared-1",
            kind="http_contract",
            description="shared",
            input={},
            expect={},
            forbidden={},
            cost_cny=0.2,
            category="security",
        ),
    )
    results = (
        EvalResult(case_id="backend-1", passed=True, cost_cny=0.5),
        EvalResult(case_id="shared-1", passed=True, cost_cny=0.2),
    )

    failures = validate_release_matrix(cases, results, gate=gate)

    assert "frontend has 0 cases" in " ".join(failures)
    assert "fullstack has 0 cases" in " ".join(failures)


def test_checked_in_matrix_is_explicitly_not_release_ready() -> None:
    cases = load_cases()
    report = run_suite()

    failures = validate_release_matrix(cases, report.results)

    assert failures
    assert any("at least 110" in failure for failure in failures)


def test_release_matrix_does_not_treat_one_scoring_call_as_full_interview_cost() -> None:
    gate = ReleaseGate(
        total_cases=1,
        cases_per_direction=0,
        shared_security_cases=0,
        overall_pass_rate=1.0,
        direction_pass_rate=1.0,
        category_pass_rate=1.0,
        critical_pass_rate=1.0,
    )
    cases = (
        EvalCase(
            case_id="backend-1",
            kind="provider_matrix",
            description="backend",
            input={},
            expect={},
            forbidden={},
            cost_cny=2.99,
            category="core",
            direction="backend",
        ),
    )
    results = (EvalResult(case_id="backend-1", passed=True, cost_cny=2.99),)

    failures = validate_release_matrix(cases, results, gate=gate)

    assert not any("cost" in failure.casefold() for failure in failures)


def test_provider_matrix_preserves_reported_usd_cost() -> None:
    dimension = {
        "score": 16,
        "deduction_reason": "",
    }
    output = InterviewScoringOutput.model_validate(
        {
            "correctness": dimension,
            "technical_depth": dimension,
            "engineering_judgment": dimension,
            "completeness": dimension,
            "clarity": dimension,
            "critical_error": False,
            "critical_error_reason": "",
            "feedback": "ok",
            "loss_reasons": [],
        }
    )
    matrix_case = MatrixCase(
        case=EvalCase(
            case_id="backend-cost",
            kind="provider_matrix",
            description="cost",
            input={},
            expect={},
            forbidden={},
            cost_cny=0.0,
            category="core",
            direction="backend",
        ),
        question="q",
        reference_answer="r",
        answer="a",
        expected_pass=True,
        min_total=80.0,
    )

    result = _validate_result(matrix_case, output, cost_usd=0.01, latency_ms=1)

    assert result.cost_usd == 0.01
    assert result.cost_cny == 0.072
