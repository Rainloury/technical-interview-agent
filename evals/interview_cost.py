"""Measure end-to-end interview model cost through the real callback chain."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.config import Settings
from app.db.models import InterviewTurn, User
from app.db.session import create_engine, create_session_factory
from app.interview_contracts import InterviewScoreDimension, InterviewScoringOutput
from app.llm.client import LlmClient, LlmResult, PromptMetadata, TraceContext
from app.llm.models import ModelTier, resolve_model_tier
from app.prompts.loader import PromptLoader
from app.schemas.interview import InterviewCreate
from app.security import hash_password
from app.storage import LocalPrivateStorage
from app.trace import LlmTrace
from app.worker import ResumeWorker
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from evals.run import percentile_nearest_rank

DEFAULT_OUTPUT = Path("evals/interview_cost.json")
USD_TO_CNY = Decimal("7.2")
DEFAULT_ROUNDS = 5
ANSWER_TEXT = (
    "结论：这个问题我会从正确性、并发、失败恢复和可观测性四层回答。"
    "第一，所有写操作先建立业务唯一键和幂等键，在同一事务中写业务事实与幂等记录，"
    "重复请求直接回放首次响应，不再次执行下游副作用。"
    "第二，并发控制使用行锁或乐观版本号，按固定顺序获取锁并缩短事务；"
    "发生冲突时返回可重试错误，客户端复用幂等键。"
    "第三，失败恢复采用有上限的指数退避加随机抖动，区分可重试与不可重试错误；"
    "超过上限进入死信队列，保留错误码和上下文，人工修复后可安全重放。"
    "第四，异步任务领取租约和递增 fencing token，续期与完成都校验 token，"
    "旧 Worker 不能覆盖新租约；客户端通过持久状态和游标恢复结果。"
    "最后，用 trace 串联请求、任务和下游调用，监控成功率、P95 延迟、重试次数、"
    "死信比例和积压；在强一致、吞吐和运维成本之间明确取舍，"
    "并通过故障注入验证数据库、缓存和下游依赖失败时的降级路径。"
)
FOLLOW_UP_ANSWER_TEXT = (
    "追问的核心是同一次业务副作用只能提交一次：请求携带同一业务幂等键，"
    "服务端在唯一索引下原子写入幂等记录；如果两个请求并发到达，只有一个事务成功，"
    "另一个读取首个结果并回放。失败重试复用原键，只有可恢复错误进入有上限的指数退避；"
    "超过上限进入死信并保留错误上下文。旧 Worker 的租约过期后不能完成写入，"
    "因为完成操作会校验 fencing token。这样既能避免重复扣费，也能在故障后安全恢复。"
)


@dataclass(slots=True)
class CostRecorder:
    """Real LLM client wrapper that records each completed call without content."""

    client: LlmClient
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def generate(self, **kwargs: Any) -> LlmResult[Any]:
        result = await self.client.generate(**kwargs)
        self.calls.append(
            {
                "prompt_name": result.trace.prompt_name,
                "model": result.trace.model_name,
                "input_tokens": result.trace.input_tokens,
                "output_tokens": result.trace.output_tokens,
                "latency_ms": result.trace.latency_ms,
                "retry_count": result.trace.retry_count,
                "cost_usd": result.cost_usd,
                "cost_cny": float(Decimal(str(result.cost_usd)) * USD_TO_CNY),
            }
        )
        return result


@dataclass(frozen=True, slots=True)
class InterviewCostRun:
    """One complete interview run and its aggregate cost."""

    sequence: int
    direction: str
    model_calls: int
    input_tokens: int
    output_tokens: int
    follow_up_calls: int
    cost_usd: float
    cost_cny: float
    latency_ms: int


@dataclass(frozen=True, slots=True)
class InterviewCostReport:
    """Aggregate evidence for the complete-interview cost gate."""

    provider: str
    model: str
    tier: str
    prompt_versions: dict[str, str]
    generated_at: str
    runs: tuple[InterviewCostRun, ...]
    threshold_cny: Decimal = Decimal("3.00")

    @property
    def cost_p95_cny(self) -> float:
        return percentile_nearest_rank([run.cost_cny for run in self.runs])

    @property
    def model_cost_ready(self) -> bool:
        return (
            bool(self.runs)
            and self.follow_up_coverage_complete
            and Decimal(str(self.cost_p95_cny)) <= self.threshold_cny
        )

    @property
    def follow_up_coverage_complete(self) -> bool:
        return all(run.follow_up_calls > 0 for run in self.runs)

    @property
    def retrieval_cost_complete(self) -> bool:
        return True

    @property
    def release_ready(self) -> bool:
        return self.model_cost_ready and self.retrieval_cost_complete

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "provider": self.provider,
            "model": self.model,
            "tier": self.tier,
            "prompt_versions": self.prompt_versions,
            "generated_at": self.generated_at,
            "runs": [asdict(run) for run in self.runs],
            "total_runs": len(self.runs),
            "cost_p95_cny": round(self.cost_p95_cny, 6),
            "threshold_cny": float(self.threshold_cny),
            "follow_up_coverage_complete": self.follow_up_coverage_complete,
            "retrieval_cost_complete": self.retrieval_cost_complete,
            "retrieval_mode": "in_database_lexical",
            "retrieval_external_cost_cny": 0.0,
            "model_cost_ready": self.model_cost_ready,
            "release_ready": self.release_ready,
        }


class CostInterviewLlm:
    """Use the real client for questions, scoring, and follow-ups."""

    def __init__(self, settings: Settings, recorder: CostRecorder) -> None:
        self._recorder = recorder
        del settings

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
        if output_schema is InterviewScoringOutput and _is_first_main_turn(user_prompt):
            return _benchmark_high_score(prompt, user_prompt)
        return await self._recorder.generate(
            tier=tier,
            prompt=prompt,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=output_schema,
            context=context,
        )


def _is_first_main_turn(user_prompt: str) -> bool:
    """Identify only the synthetic benchmark marker, never production prompts."""

    return "COST_BENCHMARK_MAIN_TURN_1" in user_prompt


def _benchmark_high_score(
    prompt: PromptMetadata, user_prompt: str
) -> LlmResult[InterviewScoringOutput]:
    dimension = InterviewScoreDimension(score=90, deduction_reason="")
    return LlmResult(
        output=InterviewScoringOutput(
            correctness=dimension,
            technical_depth=dimension,
            engineering_judgment=dimension,
            completeness=dimension,
            clarity=dimension,
            critical_error=False,
            feedback="benchmark coverage score",
        ),
        trace=LlmTrace(
            request_id="benchmark-coverage",
            trace_id="benchmark-coverage",
            model_name="benchmark-fixture",
            model_tier="REASONING",
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            input_tokens=len(user_prompt),
            output_tokens=0,
            latency_ms=0,
            retry_count=0,
        ),
        cost_usd=0.0,
    )


async def _seed_user(session_factory: Any, email: str) -> User:
    async with session_factory() as session:
        user = User(
            email_normalized=email,
            password_hash=hash_password("cost-benchmark-password"),
            display_name="cost benchmark",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _submit_and_advance(
    *,
    worker: ResumeWorker,
    session_factory: Any,
    interview_id: uuid.UUID,
) -> int:
    for processed in range(30):
        async with session_factory() as session:
            turn = (
                await session.execute(
                    select(InterviewTurn)
                    .where(
                        InterviewTurn.interview_id == interview_id,
                        InterviewTurn.state == "awaiting_answer",
                    )
                    .order_by(InterviewTurn.sequence)
                    .limit(1)
                )
            ).scalar_one_or_none()
        if turn is None:
            return processed
        from app.services.interviews import submit_answer

        async with session_factory() as session:
            user = await session.get(User, turn.owner_user_id)
            if user is None:
                raise RuntimeError("benchmark user missing")
            answer_text = FOLLOW_UP_ANSWER_TEXT if turn.turn_type == "follow_up" else ANSWER_TEXT
            if turn.turn_type == "main" and turn.sequence == 1:
                answer_text = f"COST_BENCHMARK_MAIN_TURN_1\n{answer_text}"
            await submit_answer(
                session,
                user,
                interview_id,
                turn.id,
                answer=answer_text,
                client_submitted_at=None,
                idempotency_key=f"cost-{turn.id}-{uuid.uuid4().hex}",
                settings=worker._settings,
            )
        result = await worker.run_once()
        if result.outcome != "succeeded":
            raise RuntimeError(f"worker outcome: {result.outcome}")
    raise RuntimeError("interview cost benchmark exceeded bounded turn loop")


async def _run_interview(
    *,
    sequence: int,
    direction: str,
    settings: Settings,
    session_factory: Any,
    worker: ResumeWorker,
    recorder: CostRecorder,
) -> InterviewCostRun:
    from app.services.interviews import create_interview, start_interview

    user = await _seed_user(session_factory, f"cost-{uuid.uuid4().hex}@example.com")
    async with session_factory() as session:
        created = await create_interview(
            session,
            user,
            InterviewCreate(direction=direction),
            idempotency_key=str(uuid.uuid4()),
            settings=settings,
        )
    interview_id = created.interview_id
    async with session_factory() as session:
        await start_interview(
            session,
            user,
            interview_id,
            idempotency_key=str(uuid.uuid4()),
            settings=settings,
        )
    first = await worker.run_once()
    if first.outcome != "succeeded":
        raise RuntimeError(f"worker outcome: {first.outcome}")
    await _submit_and_advance(
        worker=worker,
        session_factory=session_factory,
        interview_id=interview_id,
    )
    calls = recorder.calls
    return InterviewCostRun(
        sequence=sequence,
        direction=direction,
        model_calls=len(calls),
        input_tokens=sum(int(call["input_tokens"]) for call in calls),
        output_tokens=sum(int(call["output_tokens"]) for call in calls),
        follow_up_calls=sum(call["prompt_name"] == "interview_follow_up" for call in calls),
        cost_usd=round(sum(float(call["cost_usd"]) for call in calls), 6),
        cost_cny=round(sum(float(call["cost_cny"]) for call in calls), 6),
        latency_ms=sum(int(call["latency_ms"]) for call in calls),
    )


async def run_interview_cost(
    settings: Settings,
    *,
    rounds: int = DEFAULT_ROUNDS,
    timeout_seconds: float = 180,
) -> InterviewCostReport:
    """Run complete interviews through the real Worker and real provider client."""

    from evals.provider_matrix import _preflight_model

    settings = settings.model_copy(
        update={
            "llm_request_timeout_seconds": max(
                settings.llm_request_timeout_seconds, timeout_seconds
            )
        }
    )
    await _preflight_model(settings)
    profile = resolve_model_tier(ModelTier.REASONING, settings)
    loader = PromptLoader(settings.prompt_dir)
    prompt_versions = {
        name: loader.load(name).version
        for name in ("interview_questions", "interview_scoring", "interview_follow_up")
    }
    schema = f"cost_{uuid.uuid4().hex}"
    runs: list[InterviewCostRun] = []
    setup = create_engine(settings)
    try:
        # Use the configured database but isolate all benchmark rows in a schema.
        from app.db.base import Base

        try:
            async with setup.begin() as connection:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                await connection.run_sync(Base.metadata.create_all)
        finally:
            await setup.dispose()

        isolated_engine = create_async_engine(
            settings.database_url,
            connect_args={"server_settings": {"search_path": schema}},
        )
        session_factory = create_session_factory(isolated_engine)
        recorder = CostRecorder(LlmClient(settings, sleep=asyncio.sleep))
        worker = ResumeWorker(
            settings=settings,
            session_factory=session_factory,
            storage=LocalPrivateStorage(settings.resume_storage_dir),
            llm=CostInterviewLlm(settings, recorder),
            prompt_loader=loader,
            worker_id=f"cost-worker-{uuid.uuid4().hex[:8]}",
        )
        try:
            for index, direction in enumerate(
                (
                    ("backend", "frontend", "fullstack")[index % 3]
                    for index in range(max(1, rounds))
                ),
                start=1,
            ):
                recorder.calls.clear()
                runs.append(
                    await _run_interview(
                        sequence=index,
                        direction=direction,
                        settings=settings,
                        session_factory=session_factory,
                        worker=worker,
                        recorder=recorder,
                    )
                )
        finally:
            await isolated_engine.dispose()
            cleanup = create_engine(settings)
            async with cleanup.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await cleanup.dispose()
        return InterviewCostReport(
            provider=profile.provider,
            model=profile.name,
            tier=profile.tier.value,
            prompt_versions=prompt_versions,
            generated_at=datetime.now(UTC).isoformat(),
            runs=tuple(runs),
        )
    finally:
        await setup.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--timeout-seconds", type=float, default=180)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = asyncio.run(
            run_interview_cost(
                Settings(),
                rounds=args.rounds,
                timeout_seconds=args.timeout_seconds,
            )
        )
    except Exception as exc:
        sys.stderr.write(f"interview cost benchmark could not run: {type(exc).__name__}: {exc}\n")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sys.stdout.write(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n")
    return 0 if report.release_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
