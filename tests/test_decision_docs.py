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
RELEASE_RUNBOOK = ROOT / "docs" / "release-runbook.md"
RESTORE_DRILL = ROOT / "docs" / "database-restore-drill-2026-10-18.md"
ROLLBACK_DRILL = ROOT / "docs" / "application-rollback-drill-2026-10-18.md"
ALERT_DRILL = ROOT / "docs" / "alert-delivery-drill-2026-10-19.md"
README = ROOT / "README.md"
DOCS_README = ROOT / "docs" / "README.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _dr07_section() -> str:
    register = _read(DECISION_REGISTER)
    marker = "### DR-07 首个用户可见切片与前端工程"
    _, separator, remainder = register.partition(marker)
    assert separator, "DR-07 section is missing"
    next_heading = re.search(r"\n## ", remainder)
    return remainder[: next_heading.start()] if next_heading else remainder


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


def test_phase_docs_describe_the_release_candidate_stage() -> None:
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
        assert "发布候选" in text, path
        assert (
            "待发布批准" in text
            or "发布批准与上线执行" in text
            or "发布批准待完成" in text
            or "发布批准与上线执行待完成" in text
        ), path
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
        assert "198 passed" in text or "206 passed" in text, path
        assert "166 passed, 51 skipped" in text, path
        assert "14 passed" in text, path
        assert "109 files" in text or "112 files" in text, path
        assert "7e2b4c6d8f10" in text, path
        assert "7/7" in text, path
        assert "WebKit" in text and "14 passed" in text, path

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


def test_release_candidate_docs_do_not_reopen_closed_launch_gates() -> None:
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
        assert "WebKit 待 CI 实跑" not in text, path
        assert "模拟面试（待开发）" not in text, path
        current_text = text.rsplit("版本记录", 1)[0]
        assert "发布评审待确认" not in current_text, path


def test_release_runbook_keeps_launch_blockers_and_recovery_evidence_explicit() -> None:
    assert RELEASE_RUNBOOK.is_file()
    runbook = _read(RELEASE_RUNBOOK)

    for fragment in (
        "生产 SHA 冻结",
        "生产配置与密钥复核",
        "生产灾备与回滚复核",
        "DirectMail DNS 验证和真实投递人工确认",
        "OSS 私有、加密、权限与生命周期复核",
        "密码重置投递由持久 Worker 任务完成",
        "生产通知渠道复核",
        "发布审批",
        "生产 Worker 入口",
        "部署资产",
        "密码重置投递",
        "备份恢复",
        "回滚演练",
        "监控告警",
        "Go/No-Go",
        "/health/ready",
        "dead_letter",
        "scoring_failed",
        "pg_dump",
        "pg_restore",
        "7e2b4c6d8f10",
        "7b9ed7a",
    ):
        assert fragment in runbook, f"{fragment} missing from {RELEASE_RUNBOOK}"

    next_steps = _read(NEXT_STEPS)
    assert "release-runbook.md" in next_steps


def test_release_baseline_is_bound_to_the_recorded_ci_sha() -> None:
    runbook = _read(RELEASE_RUNBOOK)
    match = re.search(
        r"^\| (?:已验证基线|候选发布基线) \| `([0-9a-f]{7,40})` \|$",
        runbook,
        re.MULTILINE,
    )
    assert match, "release baseline SHA is missing"
    baseline = match.group(1)
    current_facts = runbook.partition("## 2. 上线阻断项")[0]
    assert "39136496514" not in current_facts
    assert "19cd750" in runbook
    assert f"`{baseline}`" in runbook


def test_frozen_release_candidate_is_recorded_in_the_go_no_go_checklist() -> None:
    runbook = _read(RELEASE_RUNBOOK)
    assert (
        "- [x] 发布 SHA `19cd750` 已创建 `v0.1.0-rc.1` annotated tag；"
        "质量、容器与 WebKit CI 对同一 SHA 全绿。"
    ) in runbook


def test_release_runbook_documents_redacted_production_config_evidence() -> None:
    runbook = _read(RELEASE_RUNBOOK)

    for fragment in (
        "scripts.check_production_config",
        "production-config-check.json",
        "不得包含密码、Token、Access Key、完整数据库 URL 或密钥值",
        "生产 env 文件 SHA-256",
        "OPS_METRICS_TOKEN` 至少 32 字符",
        "不存在 localhost 或 `http://`",
        "镜像、迁移、API 与 Worker 使用同一个 `v0.1.0-rc.1` 标签",
        "Worker 心跳在 30 秒内",
    ):
        assert fragment in runbook, f"{fragment} missing from {RELEASE_RUNBOOK}"


def test_private_rag_decision_and_public_contract_are_documented() -> None:
    adr = _read(ROOT / "docs" / "adr" / "0009-hybrid-rag-for-private-documents.md")
    adr_index = _read(ROOT / "docs" / "adr" / "README.md")
    api_contract = _read(API_CONTRACT)
    data_model = _read(DATA_MODEL)
    technical_design = _read(TECHNICAL_DESIGN)
    threat_model = _read(THREAT_MODEL)
    decision_register = _read(DECISION_REGISTER)
    readme = _read(README)

    assert "| 状态 | `accepted` |" in adr
    assert "| 审批日期 | 2026-10-21 |" in adr
    assert "ADR-0009" in adr_index and "已接受" in adr_index
    for fragment in (
        "POST /api/v1/documents",
        "GET /api/v1/documents",
        "GET /api/v1/documents/{document_id}",
        "DELETE /api/v1/documents/{document_id}",
        "不提供资料选择器",
    ):
        assert fragment in api_contract, fragment
    for fragment in ("user_documents", "user_document_chunks", "vector(1024)", "search_vector"):
        assert fragment in data_model, fragment
    for fragment in ("mxbai-embed-large:latest", "pgvector", "RRF", "降级", "BM25"):
        assert fragment in technical_design, fragment
    for fragment in ("个人资料", "owner", "Prompt", "<untrusted>"):
        assert fragment in threat_model, fragment
    assert "DR-08" in decision_register
    assert "内部资料" in readme and "mxbai-embed-large:latest" in readme


def test_production_config_signoff_requires_platform_evidence() -> None:
    runbook = _read(RELEASE_RUNBOOK)
    assert "- [ ] 生产配置核验通过，密钥未进入仓库或构建产物。" in runbook
    assert "生产 env 文件 SHA-256、生成人、复核人和 UTC 时间" in runbook
    assert "生产 env 文件由部署平台或密钥管理生成" in runbook


def test_phase_docs_do_not_claim_only_release_approval_remains() -> None:
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
        current_text = text.rsplit("版本记录", 1)[0]
        assert "只剩发布批准" not in current_text, path
        assert "恢复和告警待关闭" not in current_text, path


def test_docs_readme_references_current_document_versions() -> None:
    docs_index = _read(DOCS_README)

    def version(text: str) -> str:
        match = re.search(r"^\| 文档版本 \| ([^|]+?) \|$", text, re.MULTILINE)
        assert match, "document version is missing"
        return match.group(1).strip()

    assert f"| {version(_read(DEVELOPMENT_FLOW))} 当前流程基线 |" in docs_index
    assert f"| {version(_read(TECHNICAL_DESIGN))} 当前基线 |" in docs_index
    assert f"| {version(_read(RELEASE_RUNBOOK))} 发布候选；存在上线阻断项 |" in docs_index
    assert f"| {version(_read(NEXT_STEPS))} " in docs_index
    assert version(_read(DEVELOPMENT_FLOW)) in _read(NEXT_STEPS)
    assert version(_read(TECHNICAL_DESIGN)) in _read(NEXT_STEPS)
    assert version(_read(TECHNICAL_DESIGN)) in _read(TECHNICAL_REVIEW)
    assert "模拟面试（下一项）" not in _read(DEVELOPMENT_FLOW)
    assert "### 10. 模拟面试（已完成）" in _read(DEVELOPMENT_FLOW)
    assert "### 11. 报告与复习（已完成）" in _read(DEVELOPMENT_FLOW)
    assert "### 13. 全量验收与发布评审（已完成）" in _read(DEVELOPMENT_FLOW)


def test_database_restore_drill_keeps_auditable_evidence() -> None:
    assert RESTORE_DRILL.is_file()
    drill = _read(RESTORE_DRILL)

    for fragment in (
        "`passed`",
        "PostgreSQL 16.15",
        "technical-interview-agent-restore-20261018T145010Z",
        "9f75d1d84204386a19f8ba887a6917976823dcf2b7c9e1dd0a0a4946a306d39e",
        "3b7e1c9d4a20",
        "`public`：27 张表",
        "`pg_restore` 退出码为 `0`",
        "孤立记录数",
        "生产灾备验收",
    ):
        assert fragment in drill, f"{fragment} missing from {RESTORE_DRILL}"


def test_application_rollback_drill_keeps_auditable_evidence() -> None:
    assert ROLLBACK_DRILL.is_file()
    drill = _read(ROLLBACK_DRILL)

    for fragment in (
        "`passed`",
        "7b9ed7a90c9897ecada6f63affd8869bb10dcb37",
        "55a1053da091fc77b6d3396beb210b9104dafbbb",
        "3b7e1c9d4a20",
        "`fencing_token`",
        "succeeded",
        "没有执行 `alembic downgrade`",
        "生产网络",
    ):
        assert fragment in drill, f"{fragment} missing from {ROLLBACK_DRILL}"


def test_alert_delivery_drill_keeps_auditable_evidence() -> None:
    assert ALERT_DRILL.is_file()
    drill = _read(ALERT_DRILL)

    for fragment in (
        "`passed`",
        "7e2b4c6d8f10",
        "technical-interview-agent alerts",
        "ready_failed",
        "dead_letter",
        "scoring_failed",
        "deletion_failed",
        "worker_heartbeat_stale",
        "status=delivered: 5",
        "total: 5",
        "生产 Slack、飞书、钉钉或企业告警网关",
    ):
        assert fragment in drill, f"{fragment} missing from {ALERT_DRILL}"


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
