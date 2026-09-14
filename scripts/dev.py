#!/usr/bin/env python3
"""Run the Admin Demo and both source Vite servers as one local process group."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_OLDMAN = ROOT / ".local" / "oldman"
PYTHON = ROOT / ".venv" / "bin" / "python"


def require_local_environment() -> None:
    """Require bootstrap output before starting source development servers."""
    if not (LOCAL_OLDMAN / "frontend" / "apps" / "admin" / "package.json").is_file():
        raise RuntimeError("Local Oldman source is unavailable; run python3 scripts/bootstrap.py first")
    if not PYTHON.is_file():
        raise RuntimeError("Admin Demo virtual environment is unavailable; run python3 scripts/bootstrap.py first")
    if not (ROOT / "data" / "web_settings.yaml").is_file():
        raise RuntimeError("Copy data/web_settings.example.yaml to data/web_settings.yaml before starting the Demo")


def start(command: list[str], *, cwd: Path, environment: dict[str, str]) -> subprocess.Popen[bytes]:
    """Start one child in its own process group for reliable cleanup."""
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        start_new_session=True,
    )


def stop_all(processes: list[subprocess.Popen[bytes]]) -> None:
    """Stop every owned child without touching unrelated development processes."""
    for process in processes:
        if process.poll() is not None:
            continue
        process.terminate()
    for process in processes:
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)


def main() -> int:
    """Run source servers until one exits, then clean up the complete local stack."""
    require_local_environment()
    environment = dict(os.environ)
    environment["OLDMAN_DEMO_SOURCE_FRONTEND"] = "1"
    processes = [
        start(
            [
                "pnpm",
                "--dir",
                str(LOCAL_OLDMAN),
                "--filter",
                "oldman-admin",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                "5173",
                "--strictPort",
            ],
            cwd=LOCAL_OLDMAN,
            environment=environment,
        ),
        start(
            ["pnpm", "--dir", "frontend", "dev"],
            cwd=ROOT,
            environment=environment,
        ),
        start(
            [str(ROOT / "run.sh"), "web", "start"],
            cwd=ROOT,
            environment=environment,
        ),
    ]
    exit_code = 0
    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.2)
        exit_code = next(
            (process.returncode for process in processes if process.returncode is not None),
            1,
        )
    except KeyboardInterrupt:
        exit_code = 0
    finally:
        stop_all(processes)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
