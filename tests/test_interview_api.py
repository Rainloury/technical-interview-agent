"""Interview lifecycle, scoring Worker, report, and review integration tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.config import Settings
from app.db.models import (
    FollowUpChain,
    Interview,
    InterviewReport,
    InterviewTurn,
    ScoringAttempt,
    User,
    WeakPoint,
    WrongQuestion,
)
from app.interview_contracts import (
    InterviewFollowUpOutput,
    InterviewQuestionsOutput,
    InterviewScoringOutput,
)
from app.llm.client import LlmClientError, PromptMetadata, TraceContext
from app.llm.models import ModelTier
from app.prompts.loader import PromptLoader
from app.storage import LocalPrivateStorage
from app.worker import ResumeWorker
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import AppHarness
from tests.test_account_api import _login, _write_headers

pytestmark = pytest.mark.integration


def _headers(client: TestClient, key: str | None = None) -> dict[str, str]:
    return {
        **_write_headers(client),
        "Idempotency-Key": key or str(uuid.uuid4()),
    }


async def _owner(app_client: AppHarness, create_user: Any, email: str) -> User:
    user: User = create_user(email)
    async with app_client.session_factory() as session:
        session.add(user)
        await session.commit()
    return user


def _create(client: TestClient, *, key: str | None = None) -> Any:
    return client.post(
        "/api/v1/interviews",
        json={
            "direction": "backend",
            "difficulty": "balanced",
            "topic_keys": ["db_transactions", "api_idempotency"],
        },
        headers=_headers(client, key),
    )


def _score(
    total: float,
    *,
    critical: bool = False,
) -> InterviewScoringOutput:
    dimension = {
        "score": total,
        "deduction_reason": "" if total >= 70 else "关键机制说明不足",
    }
    return InterviewScoringOutput(
        correctness=dimension,
        technical_depth=dimension,
        engineering_judgment=dimension,
        completeness=dimension,
        clarity=dimension,
        critical_error=critical,
        critical_error_reason="关键事实错误" if critical else "",
        loss_reasons=["关键机制说明不足"] if total < 70 else [],
        feedback="结构化反馈",
    )


class InterviewStaticLlm:
    """Deterministic output for all three interview prompts."""

    def __init__(
        self,
        *,
        scores: list[InterviewScoringOutput] | None = None,
        scoring_error: Exception | None = None,
    ) -> None:
        self.scores = list(scores or [_score(90)])
        self.scoring_error = scoring_error
        self.prompts: list[str] = []

    async def generate(
        self,
        *,
        tier: ModelTier | str,
        prompt: PromptMetadata,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[Any],
        context: TraceContext,
    ) -> Any:
        del system_prompt, context
        assert ModelTier(tier) == ModelTier.REASONING
        self.prompts.append(prompt.name)
        if output_schema is InterviewQuestionsOutput:
            return _result(
                InterviewQuestionsOutput.model_validate(
                    {
                        "questions": [
                            {
                                "question_text": f"主问题 {index}: 如何设计可靠系统？",
                                "reference_answer": "受保护参考答案",
                                "scoring_rubric": ["正确性", "权衡"],
                            }
                            for index in range(1, 6)
                        ]
                    }
                ),
                prompt,
                user_prompt,
            )
        if output_schema is InterviewScoringOutput:
            if self.scoring_error is not None:
                raise self.scoring_error
            value = self.scores.pop(0) if len(self.scores) > 1 else self.scores[0]
            return _result(value, prompt, user_prompt)
        if output_schema is InterviewFollowUpOutput:
            return _result(
                InterviewFollowUpOutput(
                    question_text="追问：并发重放时唯一约束如何避免副作用？",
                    reference_answer="受保护追问参考答案",
                    scoring_rubric=["幂等", "并发"],
                ),
                prompt,
                user_prompt,
            )
        raise AssertionError(f"unexpected schema: {output_schema}")


def _result(output: Any, prompt: PromptMetadata, user_prompt: str) -> Any:
    from app.llm.client import LlmResult
    from app.trace import LlmTrace

    return LlmResult(
        output=output,
        trace=LlmTrace(
            request_id="interview-test",
            trace_id="interview-test",
            model_name="static",
            model_tier="REASONING",
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            input_tokens=len(user_prompt),
            output_tokens=1,
            latency_ms=0,
            retry_count=0,
        ),
        cost_usd=0.0,
    )


def _worker(app_client: AppHarness, settings: Settings, llm: Any) -> ResumeWorker:
    return ResumeWorker(
        settings=settings.model_copy(
            update={
                "worker_lease_seconds": 30,
                "worker_retry_base_seconds": 1,
                "worker_retry_max_seconds": 1,
            }
        ),
        session_factory=app_client.session_factory,
        storage=LocalPrivateStorage(settings.resume_storage_dir),
        llm=llm,
        prompt_loader=PromptLoader("app/prompts"),
        worker_id=f"interview-worker-{uuid.uuid4().hex[:6]}",
    )


async def test_create_and_start_are_idempotent_owner_scoped_and_deadline_bound(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "interview-owner@example.com")
    await _owner(app_client, create_user, "interview-stranger@example.com")
    client = app_client.client
    _login(client, "interview-owner@example.com")

    key = str(uuid.uuid4())
    created = _create(client, key=key)
    assert created.status_code == 201, created.text
    payload = created.json()
    interview_id = payload["interview_id"]
    assert payload["state"] == "created"
    assert payload["main_question_count"] == 5
    assert payload["deadline_at"] is None
    assert "reference" not in created.text
    assert _create(client, key=key).json()["interview_id"] == interview_id
    conflict = client.post(
        "/api/v1/interviews",
        json={
            "direction": "frontend",
            "difficulty": "balanced",
            "topic_keys": [],
        },
        headers=_headers(client, key),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"

    start_key = str(uuid.uuid4())
    started = client.post(
        f"/api/v1/interviews/{interview_id}/start",
        headers=_headers(client, start_key),
    )
    assert started.status_code == 200, started.text
    start_payload = started.json()
    assert start_payload["state"] == "in_progress"
    assert start_payload["current_turn"] is None
    assert start_payload["progress"]["main_questions_total"] == 5
    deadline = datetime.fromisoformat(start_payload["deadline_at"].replace("Z", "+00:00"))
    server_now = datetime.fromisoformat(start_payload["server_time"].replace("Z", "+00:00"))
    assert timedelta(0) < deadline - server_now <= timedelta(minutes=40)
    async with app_client.session_factory() as session:
        row = await session.get(Interview, uuid.UUID(interview_id))
        assert row is not None and row.started_at is not None
        assert row.deadline_at - row.started_at == timedelta(minutes=40)
    replay = client.post(
        f"/api/v1/interviews/{interview_id}/start",
        headers=_headers(client, start_key),
    )
    assert replay.status_code == 200
    assert replay.json()["deadline_at"] == start_payload["deadline_at"]
    replay_other_key = client.post(
        f"/api/v1/interviews/{interview_id}/start",
        headers=_headers(client),
    )
    assert replay_other_key.status_code == 200
    assert replay_other_key.json()["deadline_at"] == start_payload["deadline_at"]

    client.cookies.clear()
    _login(client, "interview-stranger@example.com")
    assert client.get(f"/api/v1/interviews/{interview_id}").status_code == 404


async def test_worker_generates_questions_and_submission_is_private_and_idempotent(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "interview-turn@example.com")
    client = app_client.client
    _login(client, "interview-turn@example.com")
    interview_id = _create(client).json()["interview_id"]
    started = client.post(
        f"/api/v1/interviews/{interview_id}/start",
        headers=_headers(client),
    )
    assert started.status_code == 200
    llm = InterviewStaticLlm()
    result = await _worker(app_client, settings, llm).run_once()
    assert result.outcome == "succeeded"
    assert "interview_questions" in llm.prompts
    detail = client.get(f"/api/v1/interviews/{interview_id}")
    assert detail.status_code == 200
    turn = detail.json()["current_turn"]
    assert turn["state"] == "awaiting_answer"
    assert len(detail.json()["submitted_turns"]) == 0
    assert "reference_answer" not in detail.text
    assert "score_total" not in detail.text

    answer_key = str(uuid.uuid4())
    submitted = client.post(
        f"/api/v1/interviews/{interview_id}/turns/{turn['id']}/answer",
        json={
            "answer": "用幂等键和唯一约束保证一次副作用。",
            "client_submitted_at": "1999-01-01T00:00:00Z",
        },
        headers=_headers(client, answer_key),
    )
    assert submitted.status_code == 202, submitted.text
    body = submitted.json()
    assert body["state"] == "scoring"
    assert body["next_action"] == "wait"
    assert "score" not in submitted.text
    assert "reference" not in submitted.text
    replay = client.post(
        f"/api/v1/interviews/{interview_id}/turns/{turn['id']}/answer",
        json={
            "answer": "用幂等键和唯一约束保证一次副作用。",
            "client_submitted_at": "2030-01-01T00:00:00Z",
        },
        headers=_headers(client, answer_key),
    )
    assert replay.status_code == 202
    assert replay.json()["accepted_at"] == body["accepted_at"]
    different = client.post(
        f"/api/v1/interviews/{interview_id}/turns/{turn['id']}/answer",
        json={"answer": "另一个回答"},
        headers=_headers(client),
    )
    assert different.status_code == 409
    assert different.json()["error"]["code"] == "turn_already_submitted"
    report = client.get(f"/api/v1/interviews/{interview_id}/report")
    assert report.status_code == 409
    assert report.json()["error"]["code"] == "report_not_ready"

    scored = await _worker(app_client, settings, llm).run_once()
    assert scored.outcome == "succeeded"
    after = client.get(f"/api/v1/interviews/{interview_id}").json()
    assert after["current_turn"]["type"] == "follow_up"
    assert after["current_turn"]["depth"] == 1
    assert "reference_answer" not in str(after)


async def test_low_score_writes_wrong_question_and_skip_reasons_are_distinct(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "interview-low@example.com")
    client = app_client.client
    _login(client, "interview-low@example.com")
    interview_id = _create(client).json()["interview_id"]
    client.post(f"/api/v1/interviews/{interview_id}/start", headers=_headers(client))
    llm = InterviewStaticLlm(scores=[_score(60)])
    await _worker(app_client, settings, llm).run_once()
    turn = client.get(f"/api/v1/interviews/{interview_id}").json()["current_turn"]
    submitted = client.post(
        f"/api/v1/interviews/{interview_id}/turns/{turn['id']}/answer",
        json={"answer": "回答缺少关键机制。"},
        headers=_headers(client),
    )
    assert submitted.status_code == 202
    await _worker(app_client, settings, llm).run_once()
    async with app_client.session_factory() as session:
        wrong = (
            await session.execute(
                select(WrongQuestion).where(WrongQuestion.turn_id == uuid.UUID(turn["id"]))
            )
        ).scalar_one()
        assert wrong.loss_reasons["items"] == ["关键机制说明不足"]
        weak = (
            await session.execute(select(WeakPoint).where(WeakPoint.topic_key == turn["topic_key"]))
        ).scalar_one()
        assert weak.failure_count == 1
    next_detail = client.get(f"/api/v1/interviews/{interview_id}").json()
    assert next_detail["current_turn"]["type"] == "main"

    follow_payload = await _seed_follow_up(
        app_client,
        interview_id,
        next_detail["current_turn"]["id"],
    )
    follow_id = follow_payload["turn_id"]
    skipped = client.post(
        f"/api/v1/interviews/{interview_id}/turns/{follow_id}/skip",
        headers=_headers(client),
    )
    assert skipped.status_code == 200, skipped.text
    advance = await _worker(app_client, settings, llm).run_once()
    assert advance.outcome == "succeeded"
    async with app_client.session_factory() as session:
        skipped_turn = await session.get(InterviewTurn, uuid.UUID(follow_id))
        assert skipped_turn is not None
        assert skipped_turn.end_reason == "user_skipped"
        assert skipped_turn.state == "skipped"
        interview = await session.get(Interview, uuid.UUID(interview_id))
        assert interview is not None
        assert interview.ended_at is None
        skipped_wrong_questions = list(
            (
                await session.execute(
                    select(WrongQuestion).where(WrongQuestion.turn_id == skipped_turn.id)
                )
            ).scalars()
        )
        assert skipped_wrong_questions == []
    after_skip = client.get(f"/api/v1/interviews/{interview_id}").json()
    assert after_skip["current_turn"]["type"] == "main"


async def _seed_follow_up(
    app_client: AppHarness,
    interview_id: str,
    root_id: str,
) -> dict[str, str]:
    async with app_client.session_factory() as session:
        root = await session.get(InterviewTurn, uuid.UUID(root_id))
        assert root is not None
        chain = (
            await session.execute(
                select(FollowUpChain).where(
                    FollowUpChain.interview_id == uuid.UUID(interview_id),
                    FollowUpChain.root_turn_id == root.id,
                )
            )
        ).scalar_one()
        child = InterviewTurn(
            interview_id=root.interview_id,
            owner_user_id=root.owner_user_id,
            parent_turn_id=root.id,
            root_turn_id=root.id,
            turn_type="follow_up",
            depth=1,
            state="awaiting_answer",
            sequence=100,
            question_text="追问：如何避免重放副作用？",
            reference_answer="受保护追问答案",
            scoring_rubric={"items": ["幂等"]},
            topic_key=root.topic_key,
            difficulty=root.difficulty,
            question_snapshot={},
        )
        session.add(child)
        await session.flush()
        chain.current_turn_id = child.id
        chain.depth_used = 1
        chain.answer_count = 1
        chain.state = "awaiting_answer"
        await session.commit()
        return {"turn_id": str(child.id)}


async def test_expired_submission_is_rejected_without_wrong_question(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "interview-expired@example.com")
    client = app_client.client
    _login(client, "interview-expired@example.com")
    interview_id = _create(client).json()["interview_id"]
    async with app_client.session_factory() as session:
        interview = await session.get(Interview, uuid.UUID(interview_id))
        assert interview is not None
        interview.state = "in_progress"
        interview.started_at = datetime.now(UTC) - timedelta(minutes=41)
        interview.deadline_at = datetime.now(UTC) - timedelta(minutes=1)
        root_id = uuid.uuid4()
        root = InterviewTurn(
            id=root_id,
            interview_id=interview.id,
            owner_user_id=interview.owner_user_id,
            root_turn_id=root_id,
            turn_type="main",
            depth=0,
            state="awaiting_answer",
            sequence=1,
            question_text="主问题",
            reference_answer="受保护",
            scoring_rubric={"items": ["正确性"]},
            topic_key="db_transactions",
            difficulty="medium",
            question_snapshot={},
        )
        session.add(root)
        await session.commit()
    response = client.post(
        f"/api/v1/interviews/{interview_id}/turns/{root_id}/answer",
        json={"answer": "迟到的回答"},
        headers=_headers(client),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "interview_time_expired"
    async with app_client.session_factory() as session:
        interview = await session.get(Interview, uuid.UUID(interview_id))
        root = await session.get(InterviewTurn, root_id)
        assert interview is not None and root is not None
        assert interview.state == "timed_out"
        assert root.state == "unanswered"
        wrong = list(
            (
                await session.execute(
                    select(WrongQuestion).where(WrongQuestion.interview_id == interview.id)
                )
            ).scalars()
        )
        assert wrong == []


async def test_terminal_scoring_failure_unlocks_incomplete_report(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "interview-failed@example.com")
    client = app_client.client
    _login(client, "interview-failed@example.com")
    interview_id = _create(client).json()["interview_id"]
    client.post(f"/api/v1/interviews/{interview_id}/start", headers=_headers(client))
    await _worker(app_client, settings, InterviewStaticLlm()).run_once()
    turn = client.get(f"/api/v1/interviews/{interview_id}").json()["current_turn"]
    client.post(
        f"/api/v1/interviews/{interview_id}/turns/{turn['id']}/answer",
        json={"answer": "回答"},
        headers=_headers(client),
    )
    failure = InterviewStaticLlm(
        scoring_error=LlmClientError("invalid_request", "bad request", retryable=False)
    )
    result = await _worker(app_client, settings, failure).run_once()
    assert result.outcome == "dead_letter"
    async with app_client.session_factory() as session:
        turn_row = await session.get(InterviewTurn, uuid.UUID(turn["id"]))
        assert turn_row is not None
        assert turn_row.state == "scoring_failed"
    report = client.get(f"/api/v1/interviews/{interview_id}/report")
    assert report.status_code == 409
    assert report.json()["error"]["code"] == "report_not_ready"


async def test_retryable_scoring_failure_records_failed_attempt_and_retries(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "interview-retry@example.com")
    client = app_client.client
    _login(client, "interview-retry@example.com")
    interview_id = _create(client).json()["interview_id"]
    client.post(f"/api/v1/interviews/{interview_id}/start", headers=_headers(client))
    await _worker(app_client, settings, InterviewStaticLlm()).run_once()
    turn = client.get(f"/api/v1/interviews/{interview_id}").json()["current_turn"]
    client.post(
        f"/api/v1/interviews/{interview_id}/turns/{turn['id']}/answer",
        json={"answer": "回答"},
        headers=_headers(client),
    )
    retry_llm = InterviewStaticLlm(
        scoring_error=LlmClientError("timeout", "provider timeout", retryable=True)
    )
    outcome = await _worker(app_client, settings, retry_llm).run_once()
    assert outcome.outcome == "retry_scheduled"
    async with app_client.session_factory() as session:
        attempt = (
            await session.execute(
                select(ScoringAttempt).where(ScoringAttempt.turn_id == uuid.UUID(turn["id"]))
            )
        ).scalar_one()
        assert attempt.state == "timed_out"
        turn_row = await session.get(InterviewTurn, uuid.UUID(turn["id"]))
        assert turn_row is not None
        assert turn_row.state == "scoring"


async def test_wrong_question_feedback_is_locked_until_terminal(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "interview-locked@example.com")
    client = app_client.client
    _login(client, "interview-locked@example.com")
    interview_id = _create(client).json()["interview_id"]
    client.post(f"/api/v1/interviews/{interview_id}/start", headers=_headers(client))
    await _worker(app_client, settings, InterviewStaticLlm()).run_once()
    detail = client.get(f"/api/v1/interviews/{interview_id}").json()
    turn = detail["current_turn"]
    client.post(
        f"/api/v1/interviews/{interview_id}/turns/{turn['id']}/answer",
        json={"answer": "回答"},
        headers=_headers(client),
    )
    async with app_client.session_factory() as session:
        turn_row = await session.get(InterviewTurn, uuid.UUID(turn["id"]))
        assert turn_row is not None
        interview = await session.get(Interview, uuid.UUID(interview_id))
        assert interview is not None
        question = WrongQuestion(
            owner_user_id=interview.owner_user_id,
            interview_id=interview.id,
            turn_id=turn_row.id,
            parent_turn_id=turn_row.parent_turn_id,
            question_text=turn_row.question_text,
            answer_text=turn_row.answer_text or "",
            reference_answer=turn_row.reference_answer,
            score_breakdown={},
            loss_reasons={"items": ["示例"]},
            topic_key=turn_row.topic_key,
            difficulty=turn_row.difficulty,
            expires_at=datetime.now(UTC) + timedelta(days=90),
        )
        session.add(question)
        await session.commit()
        question_id = question.id
    locked = client.get(f"/api/v1/wrong-questions/{question_id}")
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "feedback_locked"


async def test_complete_interview_unlocks_report_and_review_views(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "interview-complete@example.com")
    client = app_client.client
    _login(client, "interview-complete@example.com")
    interview_id = _create(client).json()["interview_id"]
    client.post(f"/api/v1/interviews/{interview_id}/start", headers=_headers(client))
    llm = InterviewStaticLlm(scores=[_score(72)])
    await _worker(app_client, settings, llm).run_once()
    for _ in range(5):
        detail = client.get(f"/api/v1/interviews/{interview_id}").json()
        turn = detail["current_turn"]
        assert turn is not None
        submitted = client.post(
            f"/api/v1/interviews/{interview_id}/turns/{turn['id']}/answer",
            json={"answer": "实现方案、边界和恢复路径。"},
            headers=_headers(client),
        )
        assert submitted.status_code == 202, submitted.text
        result = await _worker(app_client, settings, llm).run_once()
        assert result.outcome == "succeeded"

    final = client.get(f"/api/v1/interviews/{interview_id}")
    assert final.status_code == 200
    assert final.json()["state"] == "completed"
    assert final.json()["current_turn"] is None
    assert "score_total" not in final.text
    report = client.get(f"/api/v1/interviews/{interview_id}/report")
    assert report.status_code == 200, report.text
    report_payload = report.json()
    assert report_payload["scoring_status"] == "complete"
    assert len(report_payload["turns"]) == 5
    assert report_payload["summary"]["passed_count"] == 5
    assert report_payload["wrong_questions"] == []
    assert "reference_answer" in report.text

    async with app_client.session_factory() as session:
        report_row = (
            await session.execute(
                select(InterviewReport).where(
                    InterviewReport.interview_id == uuid.UUID(interview_id)
                )
            )
        ).scalar_one()
        assert report_row.passed_count == 5

    wrong_page = client.get("/api/v1/wrong-questions")
    assert wrong_page.status_code == 200
    assert wrong_page.json() == {"items": [], "next_cursor": None}
    weak_page = client.get("/api/v1/weak-points")
    assert weak_page.status_code == 200
    assert weak_page.json() == {"items": [], "next_cursor": None}


async def test_follow_up_chain_stops_at_two_layers_and_three_answers(
    app_client: AppHarness,
    settings: Settings,
    create_user: Any,
) -> None:
    await _owner(app_client, create_user, "interview-depth@example.com")
    client = app_client.client
    _login(client, "interview-depth@example.com")
    interview_id = _create(client).json()["interview_id"]
    client.post(f"/api/v1/interviews/{interview_id}/start", headers=_headers(client))
    llm = InterviewStaticLlm(scores=[_score(90)])
    await _worker(app_client, settings, llm).run_once()

    depths: list[int] = []
    for _ in range(3):
        detail = client.get(f"/api/v1/interviews/{interview_id}").json()
        turn = detail["current_turn"]
        assert turn is not None
        depths.append(turn["depth"])
        submitted = client.post(
            f"/api/v1/interviews/{interview_id}/turns/{turn['id']}/answer",
            json={"answer": "高分回答。"},
            headers=_headers(client),
        )
        assert submitted.status_code == 202
        await _worker(app_client, settings, llm).run_once()
    assert depths == [0, 1, 2]
    detail = client.get(f"/api/v1/interviews/{interview_id}").json()
    assert detail["current_turn"]["type"] == "main"
    assert detail["current_turn"]["depth"] == 0
    async with app_client.session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(InterviewTurn)
                    .where(InterviewTurn.interview_id == uuid.UUID(interview_id))
                    .order_by(InterviewTurn.sequence)
                )
            ).scalars()
        )
        follow_ups = [row for row in rows if row.turn_type == "follow_up"]
        assert len(follow_ups) == 2
        assert max(row.depth for row in follow_ups) == 2
