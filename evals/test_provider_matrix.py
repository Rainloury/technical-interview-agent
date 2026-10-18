"""Deterministic contract tests for the live-provider release matrix."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import httpx
import pytest
from app.config import Settings
from app.interview_contracts import DIRECTION_PLANS
from app.prompts.loader import PromptLoader

from evals.provider_matrix import (
    MatrixCase,
    MatrixReport,
    MatrixResult,
    _anchor_design,
    _preflight_model,
    build_matrix_cases,
    run_matrix,
)

pytestmark = pytest.mark.eval
MATRIX_PATH = Path(__file__).resolve().parent / "provider_matrix.json"


def test_matrix_has_exact_release_shape_and_unique_ids() -> None:
    cases = build_matrix_cases()
    direction_counts = Counter(case.case.direction for case in cases)

    assert len(cases) == 110
    assert direction_counts == {"backend": 30, "frontend": 30, "fullstack": 30, None: 20}
    assert len({case.case.case_id for case in cases}) == 110
    assert sum(case.case.critical for case in cases) == 29
    assert sum(case.case.category == "security" for case in cases) == 10
    assert sum(case.case.category == "contract" for case in cases) == 10


def test_every_matrix_anchor_has_concrete_technical_content() -> None:
    anchors = {
        anchor
        for plan in DIRECTION_PLANS.values()
        for topic in plan.topics
        for anchor in topic.anchors
    }

    assert all("通过明确约束" not in _anchor_design(anchor) for anchor in anchors)

    for case in build_matrix_cases()[:90]:
        assert "通过明确约束" not in case.answer
        assert "先写数据库事实再更新缓存" not in case.answer
        if case.case.case_id.endswith("-partial"):
            assert case.min_total == 55.0
            assert case.max_total == 84.0


def test_contradictory_case_expects_detection_without_unsafe_endorsement() -> None:
    cases = {
        case.case.case_id: case
        for case in build_matrix_cases()
        if case.case.case_id.endswith("-boundary-contradictory")
    }

    assert len(cases) == 3
    for case in cases.values():
        assert "错误假设" in case.answer
        assert "题干包含一个无法同时满足的要求" in case.question
        assert case.expected_pass is True
        assert case.expected_critical_error is False
        assert case.min_total is None
        assert case.max_total is None


def test_matrix_serialization_does_not_mislabel_scoring_cost_as_interview_cost() -> None:
    case = MatrixCase(
        case=build_matrix_cases()[0].case,
        question="q",
        reference_answer="r",
        answer="a",
        expected_pass=True,
    )
    report = MatrixReport(
        provider="deepseek",
        model="deepseek-v4-pro",
        tier="REASONING",
        prompt_version="1.0.0",
        generated_at="2026-10-18T00:00:00+00:00",
        cases=(case,),
        results=(
            MatrixResult(
                case_id=case.case.case_id,
                passed=True,
                score_total=90.0,
                score_band="85_plus",
                critical_error=False,
                cost_usd=0.01,
                cost_cny=0.072,
                latency_ms=1,
            ),
        ),
        release_violations=(),
    )

    payload = report.as_dict()

    assert payload["scoring_call_cost_p95_cny"] == 0.072
    assert payload["full_interview_cost_p95_cny"] is None
    assert "cost_p95_cny" not in payload


def test_checked_in_matrix_is_well_formed_and_release_ready() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 2
    assert payload["total"] == len(payload["results"]) == 110
    assert payload["matrix_complete"] is True
    assert payload["release_ready"] is True
    assert payload["release_violations"] == []
    assert payload["full_interview_cost_p95_cny"] is None
    assert "cost_p95_cny" not in payload


def test_combined_matrix_evidence_distinguishes_targeted_revalidation() -> None:
    if not MATRIX_PATH.exists():
        pytest.skip("provider matrix evidence has not been generated")
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    assert payload["evidence_mode"] in {"full_run", "full_run_plus_targeted_revalidation"}
    assert payload["total"] == 110
    if payload["evidence_mode"] == "full_run_plus_targeted_revalidation":
        assert payload["targeted_revalidation"]
        assert payload["full_interview_cost_p95_cny"] is None


def test_matrix_run_does_not_claim_full_interview_cost() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    assert payload["full_interview_cost_p95_cny"] is None


def test_scoring_prompt_has_release_calibration_contract() -> None:
    prompt = PromptLoader("app/prompts").load("interview_scoring")

    assert prompt.version == "1.1.0"
    assert "85-100" in prompt.body
    assert "55-69" in prompt.body
    assert "names the decisive mechanism" in prompt.body
    assert "critical_error" in prompt.body
    assert "severe production-safety issue" in prompt.body
    assert "Never quote it" in prompt.body


def test_shared_injection_case_checks_leak_without_requiring_critical_flag() -> None:
    cases = {case.case.case_id: case for case in build_matrix_cases()}

    security = cases["shared-security-06"]
    contract = cases["shared-contract-04"]

    assert security.expected_critical_error is None
    assert security.expected_pass is False
    assert contract.expected_pass is False
    assert "具体实现没有展开" in contract.answer


@pytest.mark.asyncio
async def test_case_selection_rejects_unknown_ids_before_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_preflight(_: Settings) -> None:
        return None

    monkeypatch.setattr("evals.provider_matrix._preflight_model", no_preflight)

    with pytest.raises(ValueError, match="unknown provider matrix case ids: missing-case"):
        await run_matrix(Settings(), case_ids=["missing-case"])


@pytest.mark.asyncio
async def test_preflight_rejects_unsupported_deepseek_model_before_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        llm_provider="deepseek",
        llm_api_key="test-key",
        llm_reasoning_model="deepseek-v4.1-flash",
    )

    class FakeAsyncClient:
        def __init__(self, **_: object) -> None:
            pass

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
            assert url == "https://api.deepseek.com/models"
            assert headers["Authorization"] == "Bearer test-key"
            request = httpx.Request("GET", url, headers=headers)
            return httpx.Response(
                request=request,
                status_code=200,
                json={
                    "data": [
                        {"id": "deepseek-flash"},
                        {"id": "deepseek-v4-pro"},
                    ]
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(ValueError, match=r"deepseek-v4\.1-flash"):
        await _preflight_model(settings)
