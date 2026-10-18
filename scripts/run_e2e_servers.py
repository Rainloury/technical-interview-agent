"""Start API, frontend, and the deterministic worker for browser E2E runs."""

from __future__ import annotations

import base64
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
RESET_FILE = Path(
    os.getenv("MAIL_LOCAL_RESET_FILE", "/private/tmp/technical-interview-agent-password-reset.json")
)
API_URL = os.getenv("API_URL", "http://127.0.0.1:8100")
WEB_URL = os.getenv("WEB_URL", "http://127.0.0.1:3101")
WEB_COMMAND = os.getenv("PLAYWRIGHT_WEB_COMMAND", "npm run dev -- --port 3101").split()


def _wait_for_url(
    url: str,
    *,
    timeout: float = 120,
    processes: tuple[subprocess.Popen[str], ...] = (),
) -> None:
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for process in processes:
            returncode = process.poll()
            if returncode is not None:
                raise RuntimeError(f"service exited with code {returncode}: {url}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
                if response.status < 500:
                    return
        except (OSError, ValueError):
            time.sleep(0.25)
    raise RuntimeError(f"service did not become ready: {url}")


def main() -> int:
    encryption_key = (
        os.getenv("DATA_ENCRYPTION_KEY") or base64.urlsafe_b64encode(os.urandom(32)).decode()
    )
    environment = {
        **os.environ,
        "DATA_ENCRYPTION_KEY": encryption_key,
        "APP_ENV": "development",
        "COOKIE_SECURE": "false",
        "AUTH_RATE_LIMIT_PER_MINUTE": "100",
        "APP_ALLOWED_ORIGINS": f'["{WEB_URL}"]',
        "CSRF_ALLOWED_ORIGINS": f'["{WEB_URL}"]',
        "PASSWORD_RESET_BASE_URL": f"{WEB_URL}/reset-password",
        "SMTP_HOST": "",
        "MAIL_LOCAL_RESET_FILE": str(RESET_FILE),
        "RESUME_STORAGE_DIR": os.getenv(
            "RESUME_STORAGE_DIR", "/private/tmp/technical-interview-agent-resume-files"
        ),
        "VITE_API_BASE_URL": API_URL,
    }
    commands = (
        [
            "env",
            "-u",
            "SMTP_HOST",
            "-u",
            "OSS_ENDPOINT",
            "-u",
            "OSS_BUCKET",
            "-u",
            "OSS_ACCESS_KEY_ID",
            "-u",
            "OSS_ACCESS_KEY_SECRET",
            "-u",
            "RESUME_STORAGE_BACKEND",
            "uv",
            "run",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8100",
        ],
        ["uv", "run", "python", "-m", "scripts.e2e_resume_worker"],
        WEB_COMMAND,
    )
    processes = tuple(
        subprocess.Popen(  # noqa: S603
            command,
            cwd=ROOT if index < 2 else WEB,
            env=environment,
            stdout=subprocess.PIPE if index == 1 else None,
            text=True,
        )
        for index, command in enumerate(commands)
    )
    worker_output: list[str] = []
    stop_requested = False

    def stop(signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True
        for process in processes:
            if process.poll() is None:
                process.send_signal(signum)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        _wait_for_url(f"{API_URL}/health/live", processes=processes)
        deadline = time.monotonic() + 120
        while "ready" not in "".join(worker_output) and time.monotonic() < deadline:
            if processes[1].poll() is not None:
                break
            line = processes[1].stdout.readline() if processes[1].stdout else ""
            if line:
                worker_output.append(line)
                continue
            time.sleep(0.1)
        if "ready" not in "".join(worker_output):
            raise RuntimeError(f"worker did not report ready: {''.join(worker_output)}")
        if processes[1].poll() is not None:
            raise RuntimeError(f"worker exited: {''.join(worker_output)}")
        _wait_for_url(WEB_URL, processes=processes)
        print("ready", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        if stop_requested:
            return 0
        failed = next(
            (process for process in processes if process.poll() not in (None, 0)),
            None,
        )
        if failed is not None:
            raise RuntimeError(f"E2E service exited with code {failed.returncode}")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0) from None
    except Exception as error:
        print(f"E2E service startup failed: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1) from None
