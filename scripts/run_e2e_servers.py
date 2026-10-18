"""Start API, frontend, and the deterministic worker for browser E2E runs."""

from __future__ import annotations

import base64
import os
import signal
import subprocess
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


def _wait_for_url(url: str, *, timeout: float = 120) -> None:
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
                if response.status < 500:
                    return
        except Exception:
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
    processes = [
        subprocess.Popen(  # noqa: S603
            command,
            cwd=ROOT if index < 2 else WEB,
            env=environment,
            stdout=subprocess.PIPE if index == 1 else None,
            text=True,
        )
        for index, command in enumerate(commands)
    ]
    worker_output: list[str] = []

    def stop(signum: int, _frame: object) -> None:
        for process in processes:
            if process.poll() is None:
                process.send_signal(signum)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        _wait_for_url(f"{API_URL}/health/live")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            line = processes[1].stdout.readline() if processes[1].stdout else ""
            if line:
                worker_output.append(line)
                if "ready" in line:
                    break
            time.sleep(0.1)
        if "ready" not in "".join(worker_output):
            raise RuntimeError(f"worker did not report ready: {''.join(worker_output)}")
        if processes[1].poll() is not None:
            raise RuntimeError(f"worker exited: {''.join(worker_output)}")
        _wait_for_url(WEB_URL)
        print("ready", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
