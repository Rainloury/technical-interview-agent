"""Decision, phase, and delivered-slice contracts visible in project docs."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISION_REGISTER = ROOT / "docs" / "decision-register.md"
NEXT_STEPS = ROOT / "docs" / "next-steps.md"
DEVELOPMENT_FLOW = ROOT / "docs" / "development-flow.md"
TECHNICAL_REVIEW = ROOT / "docs" / "technical-review-checklist.md"
API_CONTRACT = ROOT / "docs" / "api-contract.md"
TECHNICAL_DESIGN = ROOT / "docs" / "technical-design.md"
THREAT_MODEL = ROOT / "docs" / "threat-model.md"
DATA_MODEL = ROOT / "docs" / "data-model.md"
README = ROOT / "README.md"
DOCS_README = ROOT / "docs" / "README.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _dr07_section() -> str:
    register = _read(DECISION_REGISTER)
    marker = "### DR-07 首个用户可见切片与前端工程"
    _, separator, remainder = register.partition(marker)
    assert separator, "DR-07 section is missing"
    section, _, _ = remainder.partition("\n## ")
    return section


def _dr07_status() -> str:
    section = _dr07_section()
    match = re.search(r"^\| 状态 \| `([^`]+)` \|$", section, re.MULTILINE)
    assert match, "DR-07 status is missing"
    return match.group(1)


def test_dr07_keeps_the_recommended_slice_boundary() -> None:
    section = _dr07_section()

    for fragment in (
        "React + TypeScript + Vite",
        "React Router",
        "TanStack Query",
        "登录、注册、找回密码、重置密码、工作台",
        "历史分页",
        "显式 CSRF 令牌",
        "Vitest + Testing Library + MSW",
        "Playwright",
    ):
        assert fragment in section


def test_dr07_is_approved_after_project_owner_decision() -> None:
    assert _dr07_status() == "approved"
    assert "DR-07 选择方案 A" in _dr07_section()


def test_first_slice_assets_are_present_after_approval() -> None:
    for relative_path in (
        "web/src/App.tsx",
        "web/src/pages/LoginPage.tsx",
        "web/src/pages/WorkspacePage.tsx",
        "web/src/pages/HistoryPage.tsx",
        "web/playwright.config.ts",
        "web/e2e/account-workspace.spec.ts",
        "scripts/prepare_e2e.py",
    ):
        assert (ROOT / relative_path).is_file(), f"{relative_path} is missing"


def test_phase_docs_describe_the_current_launch_quality_slice() -> None:
    documents = (
        README,
        DOCS_README,
        NEXT_STEPS,
        DEVELOPMENT_FLOW,
        TECHNICAL_REVIEW,
        TECHNICAL_DESIGN,
    )
    for path in documents:
        text = _read(path)
        assert "上线质量切片进行中" in text or "发布评审待确认" in text, path
        assert "隐私与可观测门禁" in text and "已通过" in text, path
        assert (
            "真实 provider 三档单轮 eval 已通过" in text or "真实 provider FAST eval 已通过" in text
        ), path
        assert (
            "G4A 行为矩阵已通过" in text
            or "G4A 行为矩阵仅剩整场成本证据" in text
            or "完整 G4A 仅剩整场成本证据" in text
            or "G4A 行为矩阵与整场成本门禁已通过" in text
        ), path
        assert "0.83908" in text, path
        assert "12 files / 37 tests" in text, path
        assert "158 passed" in text, path
        assert "14 passed" in text, path
        assert "76 files" in text, path
        assert "9f4c2a7d1e30" in text, path
        assert "7/7" in text, path

    implementation_docs = (
        README,
        DOCS_README,
        NEXT_STEPS,
        DEVELOPMENT_FLOW,
        TECHNICAL_REVIEW,
        API_CONTRACT,
        TECHNICAL_DESIGN,
        THREAT_MODEL,
        DATA_MODEL,
    )
    for path in implementation_docs:
        text = _read(path)
        for fragment in (
            "web/",
            "interview_session",
            "interview_csrf",
            "HttpOnly",
            "X-CSRF-Token",
            "{items, next_cursor}",
            "csrf_token_hash",
        ):
            assert fragment in text, f"{fragment} missing from {path}"


def test_retrieval_qa_assets_and_boundaries_are_present() -> None:
    for relative_path in (
        "app/api/v1/qa.py",
        "app/services/qa.py",
        "app/schemas/qa.py",
        "app/prompts/qa_answer.md",
        "migrations/versions/4b6e9d2c1a70_add_qa_retrieval_slice.py",
        "evals/cases/qa-evidence-boundary.yaml",
        "tests/test_qa_api.py",
        "web/src/pages/QaPage.tsx",
        "web/src/pages/QaDetailPage.tsx",
        "web/e2e/qa-slice.spec.ts",
    ):
        assert (ROOT / relative_path).is_file(), f"{relative_path} is missing"

    design = _read(TECHNICAL_DESIGN)
    for fragment in (
        "POST /api/v1/qa",
        "GET /api/v1/qa/{id}/stream",
        "Last-Event-ID",
        "citation_id",
        "source_state",
        "任意 URL",
    ):
        assert fragment in design, f"{fragment} missing from {TECHNICAL_DESIGN}"


def test_interview_report_assets_and_boundaries_are_present() -> None:
    for relative_path in (
        "app/api/v1/interviews.py",
        "app/services/interviews.py",
        "app/schemas/interview.py",
        "app/interview_contracts.py",
        "app/prompts/interview_questions.md",
        "app/prompts/interview_scoring.md",
        "app/prompts/interview_follow_up.md",
        "migrations/versions/2c9e7f4a1b60_add_interview_slice.py",
        "migrations/versions/7d1a3e5b9c42_add_interview_advance_job.py",
        "tests/test_interview_api.py",
        "web/src/pages/InterviewPage.tsx",
        "web/src/pages/InterviewDetailPage.tsx",
        "web/src/pages/ReviewPage.tsx",
        "web/e2e/interview-slice.spec.ts",
    ):
        assert (ROOT / relative_path).is_file(), f"{relative_path} is missing"

    design = _read(TECHNICAL_DESIGN)
    for fragment in (
        "POST /api/v1/interviews",
        "POST /api/v1/interviews/{id}/start",
        "POST /api/v1/interviews/{id}/turns/{turn_id}/answer",
        "GET /api/v1/interviews/{id}/report",
        "report_not_ready",
        "feedback_locked",
        "advance_interview",
    ):
        assert fragment in design, f"{fragment} missing from {TECHNICAL_DESIGN}"


def test_launch_privacy_metrics_and_retention_assets_are_present() -> None:
    for relative_path in (
        "app/api/v1/privacy.py",
        "app/services/privacy.py",
        "app/services/metrics.py",
        "app/schemas/privacy.py",
        "migrations/versions/9f4c2a7d1e30_add_privacy_lifecycle.py",
        "tests/test_privacy_api.py",
        "web/e2e/privacy-slice.spec.ts",
        "evals/cases/interview-threshold-gates.yaml",
        "evals/cases/interview-threshold-mid.yaml",
        "evals/cases/interview-threshold-fail.yaml",
        "evals/cases/interview-critical-error.yaml",
    ):
        assert (ROOT / relative_path).is_file(), f"{relative_path} is missing"

    contract = _read(API_CONTRACT)
    for fragment in (
        "DELETE /api/v1/me/data",
        "GET /api/v1/me/data-deletion",
        "data_deletion_requests",
        "retention_cleanup",
        "delete_account_data",
        "ops_metrics_token",
    ):
        assert fragment in contract, f"{fragment} missing from {API_CONTRACT}"
