"""Run a bounded local resume Worker with deterministic, offline LLM outputs."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass

from app.config import Settings
from app.db.session import create_engine, create_session_factory
from app.llm.client import PromptMetadata, TraceContext
from app.llm.models import ModelTier
from app.prompts.loader import PromptLoader
from app.resume_contracts import (
    GeneratedQuestionOutput,
    ResumeAnalysisOutput,
    ResumeQuestionsOutput,
)
from app.storage import LocalPrivateStorage
from app.trace import LlmTrace
from app.worker import run_worker
from pydantic import BaseModel

DIFFICULTIES = ("easy",) * 3 + ("medium",) * 5 + ("hard",) * 2


class DeterministicResumeLlm:
    """Return valid fixed outputs without any provider or network call."""

    async def generate(
        self,
        *,
        tier: ModelTier | str,
        prompt: PromptMetadata,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[ResumeAnalysisOutput] | type[ResumeQuestionsOutput],
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
            ),
            cost_usd=0.0,
        )


@dataclass(frozen=True, slots=True)
class DeterministicLlmResult:
    """Minimal result shape consumed by the resume Worker."""

    output: BaseModel
    trace: LlmTrace
    cost_usd: float


async def _serve() -> None:
    settings = Settings()
    engine = create_engine(settings)
    try:
        print("ready", flush=True)
        await run_worker(
            settings=settings,
            session_factory=create_session_factory(engine),
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
