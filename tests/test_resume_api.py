"""Owner-scoped resume upload, retry, deletion, and Worker behavior."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.config import Settings
from app.db.jobs import enqueue_job
from app.db.models import (
    AsyncJob,
    GeneratedQuestion,
    ResumeAnalysis,
    ResumeFile,
    ResumeTask,
    ResumeText,
)
from app.llm.client import LlmClientError, LlmResult, PromptMetadata, TraceContext
from app.llm.models import ModelTier
from app.prompts.loader import PromptLoader
from app.qa_contracts import QaAnswerOutput
from app.resume_contracts import ResumeAnalysisOutput, ResumeQuestionsOutput
from app.storage import LocalPrivateStorage
from app.worker import ResumeWorker, ResumeWorkerError, _safe_error_detail
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import select

from tests.conftest import AppHarness
from tests.test_account_api import _login, _write_headers
from tests.test_resume_processing import analysis_payload, make_pdf, questions_payload

pytestmark = pytest.mark.integration


def _upload(
    client: TestClient,
    content: bytes,
    *,
    filename: str = "resume.pdf",
    mime: str = "application/pdf",
    key: str | None = None,
) -> Any:
    return client.post(
        "/api/v1/resumes",
        files={"file": (filename, content, mime)},
        headers={**_write_headers(client), "Idempotency-Key": key or str(uuid.uuid4())},
    )


async def _failed_task(
    harness: AppHarness,
    *,
    owner_id: uuid.UUID,
    storage: LocalPrivateStorage,
) -> tuple[ResumeTask, ResumeFile, ResumeText, AsyncJob]:
    object_key = f"{owner_id.hex}/{uuid.uuid4().hex}"
    content = make_pdf("Python backend engineer")
    await storage.put(object_key, content)
    now = datetime.now(UTC)
    async with harness.session_factory() as session:
        task = ResumeTask(
            owner_user_id=owner_id,
            state="failed",
            failure_stage="analyze",
            error_code="provider_timeout",
            error_message="简历处理未完成，请稍后重试",
            started_at=now,
            expires_at=now + timedelta(days=90),
        )
        session.add(task)
        await session.flush()
        source = ResumeFile(
            resume_task_id=task.id,
            owner_user_id=owner_id,
            original_filename="resume.pdf",
            declared_mime="application/pdf",
            detected_mime="application/pdf",
            size_bytes=len(content),
            page_count=1,
            sha256="a" * 64,
            object_key=object_key,
            storage_state="stored",
            retention_expires_at=now + timedelta(days=30),
        )
        text = ResumeText(
            resume_task_id=task.id,
            owner_user_id=owner_id,
            extracted_text="Python backend engineer",
            text_hash="b" * 64,
            extractor_version="resume-processing-v1",
            page_map={"pages": [{"page": 1, "start": 0, "end": 23}]},
            expires_at=now + timedelta(days=30),
        )
        session.add_all([source, text])
        job = await enqueue_job(
            session,
            owner_user_id=owner_id,
            job_type="parse_resume",
            resource_type="resume_task",
            resource_id=task.id,
            idempotency_key=f"seed:{task.id}",
            max_attempts=3,
        )
        job.state = "dead_letter"
        await session.commit()
        await session.refresh(task)
        await session.refresh(source)
        await session.refresh(text)
        await session.refresh(job)
        return task, source, text, job


async def test_upload_is_owner_scoped_and_idempotent(
    app_client: AppHarness, create_user: Any
) -> None:
    owner = create_user("resume-owner@example.com")
    stranger = create_user("resume-stranger@example.com")
    async with app_client.session_factory() as session:
        session.add_all([owner, stranger])
        await session.commit()

    client = app_client.client
    _login(client, "resume-owner@example.com")
    content = make_pdf("Python backend engineer")
    key = str(uuid.uuid4())
    accepted = _upload(client, content, key=key)
    assert accepted.status_code == 202, accepted.text
    task_id = accepted.json()["resume_task_id"]

    replay = _upload(client, content, key=key)
    assert replay.status_code == 202
    assert replay.json()["resume_task_id"] == task_id

    conflict = _upload(client, make_pdf("Different resume"), key=key)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"

    detail = client.get(f"/api/v1/resumes/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["state"] == "uploaded"
    assert "reference_answer" not in detail.text
    assert "scoring_rubric" not in detail.text

    client.cookies.clear()
    assert client.get(f"/api/v1/resumes/{task_id}").status_code == 401
    _login(client, "resume-stranger@example.com")
    assert client.get(f"/api/v1/resumes/{task_id}").status_code == 404


@pytest.mark.parametrize(
    ("filename", "content", "mime", "status", "code"),
    [
        ("resume.exe", b"not a resume", "application/octet-stream", 422, "unsupported_source"),
        ("resume.pdf", b"not a pdf", "application/pdf", 422, "unsupported_source"),
        ("resume.pdf", make_pdf(""), "application/pdf", 422, "text_extraction_unsupported"),
        ("resume.pdf", make_pdf(*["page"] * 11), "application/pdf", 422, "page_limit_exceeded"),
    ],
)
async def test_upload_rejects_invalid_documents_before_enqueue(
    app_client: AppHarness,
    create_user: Any,
    filename: str,
    content: bytes,
    mime: str,
    status: int,
    code: str,
) -> None:
    async with app_client.session_factory() as session:
        session.add(create_user("invalid-resume@example.com"))
        await session.commit()
    client = app_client.client
    _login(client, "invalid-resume@example.com")
    response = _upload(client, content, filename=filename, mime=mime)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    async with app_client.session_factory() as session:
        assert (await session.execute(select(AsyncJob))).scalars().all() == []


async def test_upload_rejects_oversized_body_without_creating_a_job(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    async with app_client.session_factory() as session:
        session.add(create_user("large-resume@example.com"))
        await session.commit()
    client = app_client.client
    _login(client, "large-resume@example.com")
    response = _upload(client, b"x" * (10 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"
    async with app_client.session_factory() as session:
        assert (await session.execute(select(AsyncJob))).scalars().all() == []


async def test_docx_upload_and_retry_copy_source_to_new_object(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    owner = create_user("retry-owner@example.com")
    async with app_client.session_factory() as session:
        session.add(owner)
        await session.commit()
        owner_id = owner.id
    storage = LocalPrivateStorage(app_client.app.state.settings.resume_storage_dir)
    failed, source, _, _ = await _failed_task(
        app_client,
        owner_id=owner_id,
        storage=storage,
    )

    client = app_client.client
    _login(client, "retry-owner@example.com")
    key = str(uuid.uuid4())
    response = client.post(
        f"/api/v1/resumes/{failed.id}/retry",
        headers={**_write_headers(client), "Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    new_task_id = response.json()["resume_task_id"]
    assert new_task_id != str(failed.id)
    replay = client.post(
        f"/api/v1/resumes/{failed.id}/retry",
        headers={**_write_headers(client), "Idempotency-Key": key},
    )
    assert replay.json()["resume_task_id"] == new_task_id

    async with app_client.session_factory() as session:
        copied = (
            await session.execute(
                select(ResumeFile).where(ResumeFile.resume_task_id == uuid.UUID(new_task_id))
            )
        ).scalar_one()
        assert copied.object_key != source.object_key
        assert await storage.get(copied.object_key) == await storage.get(source.object_key)

    client.cookies.clear()
    _login(client, "retry-owner@example.com")
    missing_key = client.post(
        f"/api/v1/resumes/{failed.id}/retry",
        headers=_write_headers(client),
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["error"]["code"] == "idempotency_key_required"


async def test_delete_source_removes_private_material_and_protected_answers(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    owner = create_user("delete-owner@example.com")
    async with app_client.session_factory() as session:
        session.add(owner)
        await session.commit()
        owner_id = owner.id
    storage = LocalPrivateStorage(app_client.app.state.settings.resume_storage_dir)
    task, source, text, _ = await _failed_task(
        app_client,
        owner_id=owner_id,
        storage=storage,
    )
    async with app_client.session_factory() as session:
        analysis = ResumeAnalysis(
            resume_task_id=task.id,
            owner_user_id=owner_id,
            schema_version="1.0",
            analysis_version="1.0.0",
            skills={"items": [{"name": "Python", "evidence_ids": ["evidence-1"]}]},
            projects={"items": []},
            evidence={
                "items": [
                    {
                        "id": "evidence-1",
                        "summary": "Python 后端经历" * 40,
                        "capability_tags": ["backend"],
                        "page": 1,
                    }
                ],
                "source_state": "available",
            },
            unverified_items={"items": ["未验证项目"]},
            gaps={"items": []},
            model_name="DEFAULT",
            prompt_version="1.0.0",
            expires_at=datetime.now(UTC) + timedelta(days=90),
        )
        session.add(analysis)
        await session.flush()
        question = GeneratedQuestion(
            owner_user_id=owner_id,
            resume_analysis_id=analysis.id,
            sequence=1,
            question_text="问题",
            category="backend",
            difficulty="easy",
            topic_key="topic-1",
            assessment_points={"items": ["考察点"], "page": 1},
            reference_answer="敏感参考答案",
            scoring_rubric={"items": ["评分点"]},
            evidence_refs={"ids": ["evidence-1"], "filename": "resume.pdf"},
        )
        session.add(question)
        await session.commit()
        analysis_id = analysis.id

    client = app_client.client
    _login(client, "delete-owner@example.com")
    key = str(uuid.uuid4())
    response = client.delete(
        f"/api/v1/resumes/{task.id}/source",
        headers={**_write_headers(client), "Idempotency-Key": key},
    )
    assert response.status_code == 204, response.text
    replay = client.delete(
        f"/api/v1/resumes/{task.id}/source",
        headers={**_write_headers(client), "Idempotency-Key": key},
    )
    assert replay.status_code == 204
    assert not (storage._root / source.object_key).exists()

    async with app_client.session_factory() as session:
        persisted_task = await session.get(ResumeTask, task.id)
        persisted_source = await session.get(ResumeFile, source.id)
        persisted_text = await session.get(ResumeText, text.id)
        persisted_analysis = await session.get(ResumeAnalysis, analysis_id)
        persisted_question = (
            await session.execute(
                select(GeneratedQuestion).where(GeneratedQuestion.resume_analysis_id == analysis_id)
            )
        ).scalar_one()
        assert persisted_task is not None and persisted_task.state == "source_deleted"
        assert persisted_source is not None
        assert persisted_source.storage_state == "deleted"
        assert persisted_source.original_filename == "已删除简历"
        assert persisted_source.deleted_at is not None
        assert persisted_text is not None
        assert persisted_text.extracted_text == ""
        assert persisted_text.page_map == {"source_state": "source_deleted"}
        assert persisted_text.deleted_at is not None
        assert persisted_analysis is not None
        summary = persisted_analysis.evidence["items"][0]["summary"]
        assert len(summary) <= 200
        assert "page" not in persisted_analysis.evidence["items"][0]
        assert persisted_analysis.evidence["source_state"] == "source_deleted"
        assert persisted_question.reference_answer == ""
        assert persisted_question.scoring_rubric == {"source_state": "source_deleted"}
        assert "filename" not in persisted_question.evidence_refs

    detail = client.get(f"/api/v1/resumes/{task.id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["state"] == "source_deleted"
    assert "reference_answer" not in detail.text
    assert "scoring_rubric" not in detail.text
    assert "resume.pdf" not in detail.text


class StaticLlm:
    """Return deterministic analysis and questions for the Worker test."""

    def __init__(self) -> None:
        self.calls: list[ModelTier] = []

    async def generate(
        self,
        *,
        tier: ModelTier | str,
        prompt: PromptMetadata,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[ResumeAnalysisOutput]
        | type[ResumeQuestionsOutput]
        | type[QaAnswerOutput],
        context: TraceContext,
    ) -> Any:
        del prompt, system_prompt, user_prompt, context
        self.calls.append(ModelTier(tier))
        if output_schema is ResumeAnalysisOutput:
            output: BaseModel = ResumeAnalysisOutput.model_validate(
                analysis_payload(evidence_ids=["evidence-1"])
            )
        elif output_schema is ResumeQuestionsOutput:
            output = ResumeQuestionsOutput.model_validate(
                questions_payload(evidence_id="evidence-1")
            )
        elif output_schema is QaAnswerOutput:
            output = QaAnswerOutput(
                direct_answer="Use a bounded queue.",
                explanation="A queue isolates retrieval from answer generation.",
                evidence_ids=["evidence-1"],
                extended_questions=["How are retries bounded?"],
                evidence_status="supported",
            )
        else:
            raise AssertionError(f"unexpected output schema: {output_schema}")
        return LlmResult(
            output=output,
            trace=_trace(),
            cost_usd=0.0,
        )


def _trace() -> Any:
    from app.trace import LlmTrace

    return LlmTrace(
        request_id="test",
        trace_id="test",
        model_name="test",
        model_tier="DEFAULT",
        prompt_name="test",
        prompt_version="1.0.0",
        input_tokens=1,
        output_tokens=1,
        latency_ms=0,
        retry_count=0,
    )


async def test_worker_completes_full_resume_state_chain(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    owner = create_user("worker-owner@example.com")
    async with app_client.session_factory() as session:
        session.add(owner)
        await session.commit()

    client = app_client.client
    _login(client, "worker-owner@example.com")
    response = _upload(client, make_pdf("Python backend engineer"))
    task_id = uuid.UUID(response.json()["resume_task_id"])
    async with app_client.session_factory() as session:
        job = (
            await session.execute(select(AsyncJob).where(AsyncJob.resource_id == task_id))
        ).scalar_one()
        job_id = job.id

    storage = LocalPrivateStorage(settings.resume_storage_dir)
    worker = ResumeWorker(
        settings=settings.model_copy(update={"worker_lease_seconds": 60}),
        session_factory=app_client.session_factory,
        storage=storage,
        llm=StaticLlm(),
        prompt_loader=PromptLoader("app/prompts"),
        worker_id="worker-test",
    )
    result = await worker.run_once()
    assert result.job_id == job_id
    assert result.outcome == "succeeded"

    async with app_client.session_factory() as session:
        task = await session.get(ResumeTask, task_id)
        persisted_job = await session.get(AsyncJob, job_id)
        analysis = (
            await session.execute(
                select(ResumeAnalysis).where(ResumeAnalysis.resume_task_id == task_id)
            )
        ).scalar_one()
        questions = (
            (
                await session.execute(
                    select(GeneratedQuestion).where(
                        GeneratedQuestion.resume_analysis_id == analysis.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert task is not None and task.state == "completed"
        assert task.failure_stage is None
        assert task.completed_at is not None
        assert persisted_job is not None and persisted_job.state == "succeeded"
        assert len(questions) == 10


class BrokenQuestionsLlm(StaticLlm):
    async def generate(
        self,
        *,
        tier: ModelTier | str,
        prompt: PromptMetadata,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[ResumeAnalysisOutput]
        | type[ResumeQuestionsOutput]
        | type[QaAnswerOutput],
        context: TraceContext,
    ) -> Any:
        if output_schema is ResumeQuestionsOutput:
            raise LlmClientError("timeout", "provider timeout", retryable=True)
        return await super().generate(
            tier=tier,
            prompt=prompt,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=output_schema,
            context=context,
        )


async def test_worker_records_retry_and_real_failure_stage(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    owner = create_user("worker-failure@example.com")
    async with app_client.session_factory() as session:
        session.add(owner)
        await session.commit()
    client = app_client.client
    _login(client, "worker-failure@example.com")
    response = _upload(client, make_pdf("Python backend engineer"))
    task_id = uuid.UUID(response.json()["resume_task_id"])
    async with app_client.session_factory() as session:
        job = (
            await session.execute(select(AsyncJob).where(AsyncJob.resource_id == task_id))
        ).scalar_one()
        job.max_attempts = 1
        await session.commit()

    worker = ResumeWorker(
        settings=settings.model_copy(update={"worker_lease_seconds": 60}),
        session_factory=app_client.session_factory,
        storage=LocalPrivateStorage(settings.resume_storage_dir),
        llm=BrokenQuestionsLlm(),
        prompt_loader=PromptLoader("app/prompts"),
        worker_id="worker-failure-test",
    )
    result = await worker.run_once()
    assert result.outcome == "dead_letter"

    async with app_client.session_factory() as session:
        task = await session.get(ResumeTask, task_id)
        job = (
            await session.execute(select(AsyncJob).where(AsyncJob.resource_id == task_id))
        ).scalar_one()
        assert task is not None
        assert task.state == "failed"
        assert task.failure_stage == "generate"
        assert task.error_code == "timeout"
        assert job.state == "dead_letter"


async def test_stale_fencing_token_cannot_finish_job(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    owner = create_user("fencing-owner@example.com")
    async with app_client.session_factory() as session:
        session.add(owner)
        await session.commit()
        task = ResumeTask(
            owner_user_id=owner.id,
            state="failed",
            expires_at=datetime.now(UTC) + timedelta(days=90),
        )
        session.add(task)
        await session.flush()
        job = await enqueue_job(
            session,
            owner_user_id=owner.id,
            job_type="parse_resume",
            resource_type="resume_task",
            resource_id=task.id,
            idempotency_key=f"stale:{task.id}",
            max_attempts=1,
        )
        await session.commit()
        job_id = job.id

    from app.db.jobs import finish_job, lease_next_job

    async with app_client.session_factory() as session:
        leased = await lease_next_job(
            session,
            worker_id="worker-a",
            allowed_job_ids=(job_id,),
        )
        assert leased is not None
        token = leased.fencing_token
        await session.commit()
    async with app_client.session_factory() as session:
        finished = await finish_job(
            session,
            job_id=job_id,
            worker_id="worker-a",
            fencing_token=token - 1,
            state="succeeded",
        )
        await session.commit()
        assert finished is False


async def test_invalid_question_evidence_reference_is_rejected() -> None:
    analysis = ResumeAnalysisOutput.model_validate(analysis_payload(evidence_ids=["evidence-1"]))
    questions = ResumeQuestionsOutput.model_validate(questions_payload(evidence_id="missing"))
    with pytest.raises(ResumeWorkerError) as error:
        ResumeWorker._validate_question_evidence(questions, analysis)
    assert error.value.code == "invalid_evidence_reference"


def test_safe_error_detail_records_type_but_not_sensitive_message() -> None:
    error = ValueError("resume body alice@example.com")
    detail = _safe_error_detail(error)
    assert detail == "exception=ValueError"
    assert "alice@example.com" not in detail
