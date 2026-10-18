"""Run a bounded local Worker with deterministic, offline LLM outputs."""

from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.config import Settings
from app.db.models import (
    KnowledgeSource,
    KnowledgeSourceSection,
    KnowledgeSourceVersion,
)
from app.db.session import create_engine, create_session_factory
from app.interview_contracts import (
    InterviewFollowUpOutput,
    InterviewQuestionsOutput,
    InterviewScoringOutput,
)
from app.llm.client import PromptMetadata, TraceContext
from app.llm.models import ModelTier
from app.prompts.loader import PromptLoader
from app.qa_contracts import QaAnswerOutput
from app.resume_contracts import (
    GeneratedQuestionOutput,
    ResumeAnalysisOutput,
    ResumeQuestionsOutput,
)
from app.storage import LocalPrivateStorage
from app.trace import LlmTrace
from app.worker import run_worker
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

DIFFICULTIES = ("easy",) * 3 + ("medium",) * 5 + ("hard",) * 2
QA_SOURCE_ID = uuid.UUID("1f4b4e3e-2f59-4a15-9a71-2fa3d7b94001")
QA_VERSION_ID = uuid.UUID("1f4b4e3e-2f59-4a15-9a71-2fa3d7b94002")
QA_SECTION_ID = uuid.UUID("1f4b4e3e-2f59-4a15-9a71-2fa3d7b94003")
QA_CONTENT = "有界重试应限制次数，使用指数退避、抖动和幂等键来避免重复提交。"
QA_ANSWER = "有界重试应设置次数上限，使用指数退避与抖动，并通过幂等键避免重复提交。"


class DeterministicResumeLlm:
    """Return valid fixed outputs without any provider or network call."""

    async def generate(
        self,
        *,
        tier: ModelTier | str,
        prompt: PromptMetadata,
        system_prompt: str,
        user_prompt: str,
        output_schema: (
            type[ResumeAnalysisOutput]
            | type[ResumeQuestionsOutput]
            | type[QaAnswerOutput]
            | type[InterviewQuestionsOutput]
            | type[InterviewScoringOutput]
            | type[InterviewFollowUpOutput]
        ),
        context: TraceContext,
    ) -> DeterministicLlmResult:
        del system_prompt, user_prompt
        if output_schema is ResumeAnalysisOutput:
            output: BaseModel = ResumeAnalysisOutput.model_validate(
                {
                    "schema_version": "1.0",
                    "analysis_version": "e2e-1.0.0",
                    "skills": [
                        {
                            "name": "Python",
                            "level": "advanced",
                            "evidence_ids": ["evidence-1"],
                        },
                        {
                            "name": "PostgreSQL",
                            "level": "intermediate",
                            "evidence_ids": ["evidence-2"],
                        },
                    ],
                    "projects": [
                        {
                            "name": "有界任务平台",
                            "role": "后端工程师",
                            "summary": "负责任务租约、重试与可观测性。",
                            "evidence_ids": ["evidence-1"],
                        }
                    ],
                    "evidence": [
                        {
                            "id": "evidence-1",
                            "summary": "使用 Python 构建异步任务服务",
                            "capability_tags": ["backend", "python"],
                        },
                        {
                            "id": "evidence-2",
                            "summary": "使用 PostgreSQL 管理并发任务状态",
                            "capability_tags": ["database"],
                        },
                    ],
                    "unverified_items": ["线上流量规模尚未核实"],
                    "gaps": [],
                }
            )
        elif output_schema is ResumeQuestionsOutput:
            output = ResumeQuestionsOutput(
                questions=[
                    GeneratedQuestionOutput(
                        sequence=index + 1,
                        question_text=(
                            f"{'E2E' if index == 0 else '简历'}问题 {index + 1}："
                            f"如何设计有界任务的并发与重试？"
                        ),
                        category="后端工程",
                        difficulty=difficulty,
                        topic_key=f"e2e-topic-{index + 1}",
                        assessment_points=["边界条件", "故障恢复"],
                        reference_answer="仅用于服务端评分的参考答案，不应公开。",
                        scoring_rubric=["正确性", "权衡说明"],
                        evidence_ids=["evidence-1"],
                    )
                    for index, difficulty in enumerate(DIFFICULTIES)
                ]
            )
        elif output_schema is QaAnswerOutput:
            output = QaAnswerOutput(
                direct_answer=QA_ANSWER,
                explanation=(
                    "先用幂等键去重，再限制总尝试次数；退避加入抖动，避免并发客户端同时重试。"
                ),
                evidence_ids=["evidence-1"],
                extended_questions=["如何选择重试上限与退避窗口？"],
                evidence_status="supported",
            )
        elif output_schema is InterviewQuestionsOutput:
            output = InterviewQuestionsOutput.model_validate(
                {
                    "questions": [
                        {
                            "question_text": (
                                f"E2E 主问题 {index}: "
                                "如何设计有界重试并保证重复提交不会产生副作用？"
                            ),
                            "reference_answer": "受保护参考答案：幂等键、唯一约束与有界重试。",
                            "scoring_rubric": ["正确性", "工程取舍", "故障恢复"],
                        }
                        for index in range(1, 6)
                    ]
                }
            )
        elif output_schema is InterviewScoringOutput:
            output = InterviewScoringOutput.model_validate(
                {
                    "correctness": {"score": 90, "deduction_reason": ""},
                    "technical_depth": {"score": 88, "deduction_reason": ""},
                    "engineering_judgment": {"score": 86, "deduction_reason": ""},
                    "completeness": {"score": 84, "deduction_reason": "边界说明可以更具体"},
                    "clarity": {"score": 90, "deduction_reason": ""},
                    "critical_error": False,
                    "loss_reasons": [],
                    "feedback": "回答覆盖了核心机制和恢复路径。",
                }
            )
        elif output_schema is InterviewFollowUpOutput:
            output = InterviewFollowUpOutput(
                question_text="E2E 追问：并发重放时，唯一约束和响应回放如何配合？",
                reference_answer="受保护追问参考答案：唯一约束负责去重，响应回放保证结果一致。",
                scoring_rubric=["幂等", "并发", "响应一致性"],
            )
        else:
            raise RuntimeError("unexpected output schema")
        return DeterministicLlmResult(
            output=output,
            trace=LlmTrace(
                request_id="e2e",
                trace_id="e2e",
                model_tier=ModelTier(tier).value,
                model_name="deterministic-e2e",
                prompt_name=prompt.name,
                prompt_version=prompt.version,
                input_tokens=0,
                output_tokens=0,
                latency_ms=0,
                retry_count=0,
                resume_task_id=context.resume_task_id,
                qa_request_id=context.qa_request_id,
            ),
            cost_usd=0.0,
        )


@dataclass(frozen=True, slots=True)
class DeterministicLlmResult:
    """Minimal result shape consumed by the Worker."""

    output: BaseModel
    trace: LlmTrace
    cost_usd: float


async def _seed_qa_source(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Create one fixed, published QA source without duplicating prior runs."""

    async with session_factory() as session:
        source = await session.get(KnowledgeSource, QA_SOURCE_ID)
        if source is None:
            session.add(
                KnowledgeSource(
                    id=QA_SOURCE_ID,
                    source_type="official_doc",
                    title="有界重试设计指南",
                    source_uri="https://docs.example/bounded-retry",
                    direction="backend",
                    allowlisted=True,
                )
            )
            await session.flush()
        version = await session.get(KnowledgeSourceVersion, QA_VERSION_ID)
        if version is None:
            session.add(
                KnowledgeSourceVersion(
                    id=QA_VERSION_ID,
                    source_id=QA_SOURCE_ID,
                    version_label="e2e-1",
                    content_hash="e2e-bounded-retry-v1",
                    published_at=datetime(2026, 1, 1, tzinfo=UTC),
                    status="published",
                )
            )
            await session.flush()
        section = await session.get(KnowledgeSourceSection, QA_SECTION_ID)
        if section is None:
            session.add(
                KnowledgeSourceSection(
                    id=QA_SECTION_ID,
                    version_id=QA_VERSION_ID,
                    section_index=0,
                    section_path="重试策略 / 有界重试",
                    content=QA_CONTENT,
                    token_count=len(QA_CONTENT),
                )
            )
        else:
            section.content = QA_CONTENT
            section.token_count = len(QA_CONTENT)
        await session.commit()


async def _serve() -> None:
    settings = Settings(_env_file=None)
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        await _seed_qa_source(session_factory)
        print("ready", flush=True)
        await run_worker(
            settings=settings,
            session_factory=session_factory,
            storage=LocalPrivateStorage(settings.resume_storage_dir),
            llm=DeterministicResumeLlm(),
            prompt_loader=PromptLoader(settings.prompt_dir),
            max_iterations=3000,
            idle_seconds=0.2,
        )
    finally:
        await engine.dispose()


def main() -> int:
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"deterministic worker failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
