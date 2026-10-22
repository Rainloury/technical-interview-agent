"""Production Worker loop, lifecycle, and command-line contract."""

from __future__ import annotations

import asyncio
import json
import signal
from argparse import Namespace
from pathlib import Path
from typing import Any, ClassVar

import app.worker
import pytest
from app import cli
from app.config import Settings
from app.db.session import create_engine, create_session_factory
from app.llm.client import (
    LlmClient,
    LlmClientError,
    PromptMetadata,
    ProviderRequest,
    ProviderResult,
    TraceContext,
)
from app.storage import LocalPrivateStorage
from app.worker import WorkerResult, run_worker
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class FakeWorker:
    """Deterministic poller that records instances and waits for a stop event."""

    instances: ClassVar[list[FakeWorker]] = []
    stop_on_first_idle: ClassVar[bool] = False
    outcome: ClassVar[str] = "idle"

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: object,
        storage: object,
        llm: object,
        prompt_loader: object,
        embedding_client: object | None = None,
        worker_id: str | None = None,
    ) -> None:
        del settings, session_factory, storage, llm, prompt_loader, embedding_client
        self.worker_id = worker_id
        self.stop_event: asyncio.Event | None = None
        self.calls = 0
        FakeWorker.instances.append(self)

    async def run_once(self) -> WorkerResult:
        self.calls += 1
        if FakeWorker.stop_on_first_idle and self.stop_event is not None:
            self.stop_event.set()
        return WorkerResult(job_id=None, outcome=FakeWorker.outcome)


def _factory() -> async_sessionmaker[AsyncSession]:
    return create_session_factory(create_engine(Settings(app_env="test")))


def _storage() -> LocalPrivateStorage:
    return LocalPrivateStorage("/private/tmp/technical-interview-agent-worker-tests")


class Output(BaseModel):
    answer: str


class ClosingProvider:
    def __init__(self) -> None:
        self.closed = False

    async def generate(
        self, request: ProviderRequest, output_schema: type[BaseModel]
    ) -> ProviderResult:
        del request
        return ProviderResult(
            data=output_schema.model_validate({"answer": "ok"}),
            input_tokens=1,
            output_tokens=1,
            finish_reason="completed",
        )

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def reset_fake_worker() -> None:
    FakeWorker.instances = []
    FakeWorker.stop_on_first_idle = False
    FakeWorker.outcome = "idle"


async def test_local_provider_is_explicitly_unavailable_without_network() -> None:
    settings = Settings(app_env="test", llm_provider="local", _env_file=None)
    client = LlmClient(settings)

    with pytest.raises(LlmClientError) as raised:
        await client.generate(
            tier="FAST",
            prompt=PromptMetadata(name="resume_analysis", version="test"),
            system_prompt="system",
            user_prompt="user",
            output_schema=Output,
            context=TraceContext(),
        )

    assert raised.value.code == "local_provider_unavailable"
    await client.aclose()


async def test_worker_loop_starts_bounded_concurrency_and_stops_on_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.worker, "ResumeWorker", FakeWorker)
    stop_event = asyncio.Event()
    settings = Settings(app_env="test", worker_idle_seconds=0.01)
    FakeWorker.stop_on_first_idle = False

    task = asyncio.create_task(
        run_worker(
            settings=settings,
            session_factory=_factory(),
            storage=_storage(),
            llm=Any,  # type: ignore[arg-type]
            prompt_loader=Any,  # type: ignore[arg-type]
            concurrency=2,
            stop_event=stop_event,
            max_runtime_seconds=1,
        )
    )
    await asyncio.sleep(0.05)
    stop_event.set()
    await asyncio.wait_for(task, timeout=1)

    assert len(FakeWorker.instances) == 2
    assert all(worker.calls >= 1 for worker in FakeWorker.instances)


async def test_worker_loop_never_exceeds_iteration_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.worker, "ResumeWorker", FakeWorker)
    settings = Settings(app_env="test", worker_idle_seconds=0.001)

    await asyncio.wait_for(
        run_worker(
            settings=settings,
            session_factory=_factory(),
            storage=_storage(),
            llm=Any,  # type: ignore[arg-type]
            prompt_loader=Any,  # type: ignore[arg-type]
            concurrency=3,
            max_iterations=5,
            max_runtime_seconds=1,
        ),
        timeout=1,
    )

    assert sum(worker.calls for worker in FakeWorker.instances) == 5


async def test_worker_loop_honors_max_runtime_when_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.worker, "ResumeWorker", FakeWorker)
    settings = Settings(app_env="test", worker_idle_seconds=10)
    FakeWorker.outcome = "succeeded"

    await asyncio.wait_for(
        run_worker(
            settings=settings,
            session_factory=_factory(),
            storage=_storage(),
            llm=Any,  # type: ignore[arg-type]
            prompt_loader=Any,  # type: ignore[arg-type]
            max_runtime_seconds=0.02,
        ),
        timeout=1,
    )

    assert FakeWorker.instances[0].calls >= 1


async def test_worker_loop_finishes_in_flight_work_within_shutdown_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowWorker(FakeWorker):
        finished = False

        async def run_once(self) -> WorkerResult:
            self.calls += 1
            await asyncio.sleep(0.05)
            SlowWorker.finished = True
            return WorkerResult(job_id=None, outcome="succeeded")

    monkeypatch.setattr(app.worker, "ResumeWorker", SlowWorker)
    stop_event = asyncio.Event()
    settings = Settings(app_env="test")

    task = asyncio.create_task(
        run_worker(
            settings=settings,
            session_factory=_factory(),
            storage=_storage(),
            llm=Any,  # type: ignore[arg-type]
            prompt_loader=Any,  # type: ignore[arg-type]
            stop_event=stop_event,
            shutdown_grace_seconds=0.2,
        )
    )
    await asyncio.sleep(0.01)
    stop_event.set()
    await asyncio.wait_for(task, timeout=1)

    assert SlowWorker.finished is True


async def test_worker_loop_cancels_in_flight_work_after_shutdown_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowWorker(FakeWorker):
        cancelled = False
        finished = False

        async def run_once(self) -> WorkerResult:
            self.calls += 1
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                SlowWorker.cancelled = True
                raise
            SlowWorker.finished = True
            return WorkerResult(job_id=None, outcome="succeeded")

    monkeypatch.setattr(app.worker, "ResumeWorker", SlowWorker)
    stop_event = asyncio.Event()
    settings = Settings(app_env="test")

    task = asyncio.create_task(
        run_worker(
            settings=settings,
            session_factory=_factory(),
            storage=_storage(),
            llm=Any,  # type: ignore[arg-type]
            prompt_loader=Any,  # type: ignore[arg-type]
            stop_event=stop_event,
            shutdown_grace_seconds=0.02,
        )
    )
    await asyncio.sleep(0.01)
    stop_event.set()
    await asyncio.wait_for(task, timeout=1)

    assert SlowWorker.cancelled is True
    assert SlowWorker.finished is False


async def test_llm_client_releases_provider_resources() -> None:
    provider = ClosingProvider()
    client = LlmClient(Settings(app_env="test"), provider=provider)

    await client.aclose()

    assert provider.closed is True


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"concurrency": 0}, "concurrency"),
        ({"max_iterations": 0}, "max_iterations"),
        ({"max_runtime_seconds": 0}, "max_runtime_seconds"),
        ({"idle_seconds": 0}, "idle_seconds"),
    ],
)
async def test_worker_loop_rejects_unbounded_or_invalid_limits(
    kwargs: dict[str, float | int],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        await run_worker(
            settings=Settings(app_env="test"),
            session_factory=_factory(),
            storage=_storage(),
            llm=Any,  # type: ignore[arg-type]
            prompt_loader=Any,  # type: ignore[arg-type]
            concurrency=int(kwargs.get("concurrency", 1)),
            max_iterations=(int(kwargs["max_iterations"]) if "max_iterations" in kwargs else None),
            max_runtime_seconds=(
                float(kwargs["max_runtime_seconds"]) if "max_runtime_seconds" in kwargs else None
            ),
            idle_seconds=(float(kwargs["idle_seconds"]) if "idle_seconds" in kwargs else None),
        )


async def test_worker_runner_installs_handlers_and_releases_resources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[object] = []

    class FakeEngine:
        async def dispose(self) -> None:
            events.append("engine-disposed")

    class FakeStorage:
        async def aclose(self) -> None:
            events.append("storage-closed")

    class FakeLoop:
        def add_signal_handler(self, signum: int, callback: object, *args: object) -> None:
            events.append(("add", signum, callback, args))

        def remove_signal_handler(self, signum: int) -> None:
            events.append(("remove", signum))

    async def fake_run_worker(**kwargs: object) -> None:
        events.append(("run", kwargs))

    monkeypatch.setattr(app.worker, "create_engine", lambda _settings: FakeEngine())
    monkeypatch.setattr(app.worker, "create_resume_storage", lambda _settings: FakeStorage())
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: FakeLoop())
    monkeypatch.setattr(app.worker, "run_worker", fake_run_worker)

    runner = app.worker.WorkerRunner(
        settings=Settings(
            app_env="test",
            worker_health_file=str(tmp_path / "worker-health.json"),
            _env_file=None,
        ),
        llm_factory=lambda _settings: object(),
    )
    await runner.run()

    assert [event[1] for event in events if isinstance(event, tuple) and event[0] == "add"] == [
        signal.SIGINT,
        signal.SIGTERM,
    ]
    assert [event[1] for event in events if isinstance(event, tuple) and event[0] == "remove"] == [
        signal.SIGINT,
        signal.SIGTERM,
    ]
    assert "storage-closed" in events
    assert "engine-disposed" in events
    assert not (tmp_path / "worker-health.json").exists()


async def test_worker_runner_rejects_incomplete_production_configuration_before_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fail_setup(_settings: Settings) -> object:
        nonlocal called
        called = True
        raise AssertionError("setup should not run")

    monkeypatch.setattr(app.worker, "create_engine", fail_setup)
    runner = app.worker.WorkerRunner(
        settings=Settings(app_env="production"),
        llm_factory=lambda _settings: object(),
    )

    with pytest.raises(ValueError, match="missing deployed configuration"):
        await runner.run()

    assert called is False


def test_worker_heartbeat_interval_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(worker_heartbeat_interval_seconds=0)


async def test_worker_runner_preserves_llm_initialization_error_and_releases_resources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []

    class FakeEngine:
        async def dispose(self) -> None:
            events.append("engine-disposed")

    class FakeStorage:
        async def aclose(self) -> None:
            events.append("storage-closed")

    class FakeLoop:
        def add_signal_handler(self, signum: int, callback: object, *args: object) -> None:
            del signum, callback, args

        def remove_signal_handler(self, signum: int) -> None:
            del signum

    def fail_llm(_settings: Settings) -> object:
        raise RuntimeError("llm initialization failed")

    monkeypatch.setattr(app.worker, "create_engine", lambda _settings: FakeEngine())
    monkeypatch.setattr(app.worker, "create_resume_storage", lambda _settings: FakeStorage())
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: FakeLoop())

    runner = app.worker.WorkerRunner(
        settings=Settings(
            app_env="test",
            worker_health_file=str(tmp_path / "worker-health.json"),
            _env_file=None,
        ),
        llm_factory=fail_llm,
    )

    with pytest.raises(RuntimeError, match="llm initialization failed"):
        await runner.run()

    assert events == ["storage-closed", "engine-disposed"]
    assert not (tmp_path / "worker-health.json").exists()


async def test_worker_runner_writes_live_health_while_running(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    health_file = tmp_path / "worker-health.json"
    observed: list[dict[str, object]] = []

    class FakeEngine:
        async def dispose(self) -> None:
            return None

    class FakeStorage:
        async def aclose(self) -> None:
            return None

    class FakeLoop:
        def add_signal_handler(self, signum: int, callback: object, *args: object) -> None:
            del signum, callback, args

        def remove_signal_handler(self, signum: int) -> None:
            del signum

    async def fake_run_worker(**kwargs: object) -> None:
        del kwargs
        observed.append(json.loads(health_file.read_text(encoding="utf-8")))
        await asyncio.sleep(0)

    monkeypatch.setattr(app.worker, "create_engine", lambda _settings: FakeEngine())
    monkeypatch.setattr(app.worker, "create_resume_storage", lambda _settings: FakeStorage())
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: FakeLoop())
    monkeypatch.setattr(app.worker, "run_worker", fake_run_worker)

    runner = app.worker.WorkerRunner(
        settings=Settings(
            app_env="test",
            worker_health_file=str(health_file),
            _env_file=None,
        ),
        llm_factory=lambda _settings: object(),
    )
    await runner.run()

    assert len(observed) == 1
    assert observed[0]["state"] == "running"
    worker_id = observed[0]["worker_id"]
    assert isinstance(worker_id, str)
    assert worker_id.startswith("resume-worker-")
    assert not health_file.exists()


async def test_worker_runner_refreshes_health_while_worker_is_running(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    health_file = tmp_path / "worker-health.json"
    observed_mtimes: list[float] = []

    class FakeEngine:
        async def dispose(self) -> None:
            return None

    class FakeStorage:
        async def aclose(self) -> None:
            return None

    class FakeLoop:
        def add_signal_handler(self, signum: int, callback: object, *args: object) -> None:
            del signum, callback, args

        def remove_signal_handler(self, signum: int) -> None:
            del signum

    async def fake_run_worker(**kwargs: object) -> None:
        del kwargs
        observed_mtimes.append(health_file.stat().st_mtime_ns)
        await asyncio.sleep(0.06)
        observed_mtimes.append(health_file.stat().st_mtime_ns)

    monkeypatch.setattr(app.worker, "create_engine", lambda _settings: FakeEngine())
    monkeypatch.setattr(app.worker, "create_resume_storage", lambda _settings: FakeStorage())
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: FakeLoop())
    monkeypatch.setattr(app.worker, "run_worker", fake_run_worker)

    runner = app.worker.WorkerRunner(
        settings=Settings(
            app_env="test",
            worker_health_file=str(health_file),
            worker_heartbeat_interval_seconds=0.02,
            _env_file=None,
        ),
        llm_factory=lambda _settings: object(),
    )
    await runner.run()

    assert len(observed_mtimes) == 2
    assert observed_mtimes[0] < observed_mtimes[1]
    assert not health_file.exists()


def test_cli_dispatches_worker_without_reload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seen: list[Settings] = []
    executed: list[bool] = []
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "LLM_PROVIDER=openai\n"
        'APP_ALLOWED_ORIGINS=["http://127.0.0.1:3001"]\n'
        'CSRF_ALLOWED_ORIGINS=["http://127.0.0.1:3001"]\n',
        encoding="utf-8",
    )

    class FakeParser:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def add_argument(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def parse_args(self, _argv: object = None) -> Namespace:
            return Namespace(command="worker", reload=False)

    class FakeRunner:
        def __init__(self, **kwargs: Any) -> None:
            seen.append(kwargs["settings"])

        async def run(self) -> None:
            executed.append(True)

    def fake_run(coroutine: Any) -> None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coroutine)
        finally:
            loop.close()

    monkeypatch.setattr("app.cli.argparse.ArgumentParser", FakeParser)
    monkeypatch.setattr("app.cli.asyncio.run", fake_run)
    monkeypatch.setattr("app.worker.WorkerRunner", FakeRunner)
    monkeypatch.setattr("app.cli.get_settings", lambda: Settings(_env_file=dotenv))

    cli.main()

    assert executed == [True]
    assert len(seen) == 1
    assert seen[0].app_env == "development"
    assert seen[0].llm_provider == "openai"
    assert seen[0].app_allowed_origins == ["http://127.0.0.1:3001"]


def test_cli_dispatches_migration(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    class FakeParser:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def add_argument(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def parse_args(self, _argv: object = None) -> Namespace:
            return Namespace(command="migrate", reload=False)

        def error(self, message: str) -> None:
            raise AssertionError(message)

    def fake_alembic_main(*, argv: list[str]) -> None:
        seen.append(argv)

    monkeypatch.setattr("app.cli.argparse.ArgumentParser", FakeParser)
    monkeypatch.setattr("alembic.config.main", fake_alembic_main)

    cli.main()

    assert seen == [["upgrade", "head"]]
