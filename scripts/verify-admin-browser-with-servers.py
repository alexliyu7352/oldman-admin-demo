#!/usr/bin/env python3
"""Run the complete Admin Chrome gate against one isolated Demo instance."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
USERNAME = "oldman_admin"
PASSWORD = "oldman_admin_123"


class BrowserGateError(RuntimeError):
    """Report an isolated service or browser failure."""


def load_service_wrapper() -> ModuleType:
    """Load the focused wrapper so both gates share one service lifecycle."""
    path = ROOT / "scripts" / "verify-notifications-browser-with-server.py"
    spec = importlib.util.spec_from_file_location(
        "verify_admin_notifications_browser_with_server",
        path,
    )
    if spec is None or spec.loader is None:
        raise BrowserGateError(f"Unable to load browser service wrapper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_browser(
    environment: dict[str, str],
    *,
    service_port: int,
    evidence_dir: Path,
) -> dict[str, object]:
    """Run the Admin browser assertions and require a clean JSON result."""
    child_environment = {
        **environment,
        "OLDMAN_ADMIN_EVIDENCE_DIR": str(evidence_dir),
        "OLDMAN_ADMIN_URL": f"http://127.0.0.1:{service_port}/",
        "OLDMAN_ADMIN_USERNAME": USERNAME,
        "OLDMAN_ADMIN_PASSWORD": PASSWORD,
    }
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify-admin-browser.py")],
        cwd=ROOT,
        env=child_environment,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise BrowserGateError(
            f"Admin browser returned invalid JSON: {completed.stdout[-4000:]}"
        ) from exc
    if (
        completed.returncode != 0
        or not isinstance(result, dict)
        or result.get("ok") is not True
        or result.get("failures") != []
        or result.get("consoleErrors") != []
        or result.get("pageErrors") != []
        or result.get("badResponses") != []
    ):
        raise BrowserGateError(f"Admin browser gate failed: {result}")
    return result


def prepare_crud_data(environment: dict[str, str], config_file: Path) -> None:
    """Prepare fixture and permission users only in this gate's newly migrated database."""
    source = """
import asyncio
import sys
from oldman import bootstrap_service

context = bootstrap_service('web', config_file=sys.argv[1])
from oldman.auth import get_user_model
from oldman.db import db_manager
from oldman.db.fixtures import load_data, resolve_fixture_path

async def main():
    try:
        await load_data(context.apps, db_manager, resolve_fixture_path(context.apps, 'demo'))
        user_model = get_user_model()
        async with db_manager.get_session() as session:
            for username, password, display_name, superuser in (
                ('browser_staff', 'BrowserStaff123', 'Browser Staff', False),
                ('browser_superuser_guard', 'BrowserGuard123', 'Browser Guard Superuser', True),
            ):
                user = user_model(username=username, display_name=display_name,
                                  is_active=True, is_staff=True, is_superuser=superuser)
                user.set_password(password)
                session.add(user)
    finally:
        await db_manager.close()

asyncio.run(main())
"""
    subprocess.run(
        [sys.executable, "-c", source, str(config_file)],
        cwd=ROOT, env=environment, check=True, timeout=30,
    )


def main() -> int:
    """Prepare owned state, run Chrome, and clean every child service."""
    wrapper = load_service_wrapper()
    environment = wrapper.minimal_environment(os.environ)
    with tempfile.TemporaryDirectory(
        prefix="oldman-admin-browser-gate-"
    ) as temporary_directory:
        state_root = Path(temporary_directory)
        service_port = wrapper.find_free_port()
        with wrapper.owned_redis_server(
            state_root / "redis",
            environment=environment,
        ) as redis_url:
            wrapper.collect_gate_static(state_root, environment=environment)
            config_file = wrapper.prepare_gate_settings(
                state_root,
                redis_url=redis_url,
                service_port=service_port,
            )
            # 这些助手现在来自 oldman.testing.gates，参数是关键字形式，和通知门禁那边同一套。
            wrapper.migrate_gate_database(config_file, state_root, project_root=ROOT)
            wrapper.ensure_gate_admin(
                config_file,
                environment=environment,
                project_root=ROOT,
                username=USERNAME,
                password=PASSWORD,
            )
            prepare_crud_data(environment, config_file)
            with wrapper.owned_service(
                config_file,
                environment=environment,
                project_root=ROOT,
                name="admin-service",
            ) as process:
                wrapper.wait_for_service(process, service_port, name="Admin service")
                result = run_browser(
                    environment,
                    service_port=service_port,
                    evidence_dir=state_root / "evidence",
                )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
