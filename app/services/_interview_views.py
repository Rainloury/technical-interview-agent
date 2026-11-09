"""面试复习视图的共享构造器,避免同字段出现两种表示。"""

from __future__ import annotations

from typing import Any, cast

from app.db.models import WeakPoint, WeakPointEvidence, WrongQuestion
from app.schemas.interview import (
    WeakPointEvidenceView,
    WeakPointSummary,
    WrongQuestionDetail,
)


def wrong_question_view(item: WrongQuestion) -> WrongQuestionDetail:
    return WrongQuestionDetail(
        id=item.id,
        interview_id=item.interview_id,
        turn_id=item.turn_id,
        parent_turn_id=item.parent_turn_id,
        question_text=item.question_text,
        topic_key=item.topic_key,
        difficulty=cast(Any, item.difficulty),
        score_breakdown=item.score_breakdown,
        loss_reasons=[
            str(value) for value in item.loss_reasons.get("items", []) if isinstance(value, str)
        ],
        created_at=item.created_at,
        answer_text=item.answer_text,
        reference_answer=item.reference_answer,
        state=item.state,
        expires_at=item.expires_at,
    )


def weak_point_evidence_view(row: WeakPointEvidence) -> WeakPointEvidenceView:
    return WeakPointEvidenceView(
        wrong_question_id=row.wrong_question_id,
        turn_id=row.turn_id,
        loss_reason_hash=row.loss_reason_hash,
    )


def weak_point_view(item: WeakPoint, evidence: list[WeakPointEvidence]) -> WeakPointSummary:
    return WeakPointSummary(
        id=item.id,
        topic_key=item.topic_key,
        title=item.title,
        severity=float(item.severity),
        failure_count=item.failure_count,
        last_failure_at=item.last_failure_at,
        review_advice=item.review_advice,
        state=item.state,
        evidence=[weak_point_evidence_view(row) for row in evidence],
    )
