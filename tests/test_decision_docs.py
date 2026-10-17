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


def test_phase_docs_describe_the_current_resume_slice() -> None:
    documents = (
        README,
        DOCS_README,
        NEXT_STEPS,
        DEVELOPMENT_FLOW,
        TECHNICAL_REVIEW,
    )
    for path in documents:
        text = _read(path)
        assert "简历纵向切片验收通过" in text, path
        assert "真实 provider FAST eval 已通过" in text, path
        assert "完整 G4A 模型矩阵仍未关闭" in text, path
        assert "准备进入检索问答切片" in text, path
        assert "7 files / 21 tests" in text, path
        assert "107 passed" in text, path
        assert "4 passed" in text, path
        assert "78 files" in text, path
        assert "8f3d2a1c7b90" in text, path

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
