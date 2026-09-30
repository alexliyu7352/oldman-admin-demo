"""Admin Demo installation through App Registry and project migrations."""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from ruamel.yaml import YAML

from oldman.testing import find_free_port, gate_settings, owned_redis_server

ROOT = Path(__file__).resolve().parents[1]
ADMIN_DEMO = ROOT


def copy_admin_demo(destination: Path, *, redis_url: str) -> Path:
    """Copy only source files required by the isolated migration consumer.

    The settings come from the shared gate helper, which points every Redis alias at the
    test's own server. ``changepassword`` ends the user's sessions, and on the example
    settings it would do that on the developer's Redis, where a running demo keeps its
    sessions under the same key prefix and user ids.
    """
    project = destination / "admin_demo"
    project.mkdir()
    for directory in ("apps", "config", "services"):
        shutil.copytree(ADMIN_DEMO / directory, project / directory)
    shutil.copy2(ADMIN_DEMO / "pyproject.toml", project / "pyproject.toml")
    gate_settings(
        ADMIN_DEMO / "data" / "web_settings.example.yaml",
        project / "data",
        service_port=find_free_port(),
        redis_url=redis_url,
        namespace="admin_demo_migration",
        database_name="admin_demo.db",
        customize=_without_translations,
    )
    return project


def _without_translations(payload: dict) -> None:
    # The lifecycle check below does not need a Sanic translation environment.
    payload["i18n"]["use_i18n"] = False


def project_environment(project: Path) -> dict[str, str]:
    """Return deterministic imports and CLI localization for a copied demo."""
    environment = os.environ.copy()
    paths = [str(project)]
    if existing_path := environment.get("PYTHONPATH"):
        paths.append(existing_path)
    environment["PYTHONPATH"] = os.pathsep.join(paths)
    environment["OLDMAN_CLI_LANGUAGE"] = "en"
    environment["XDG_CONFIG_HOME"] = str(project / ".cli-config")
    environment["LANG"] = "C"
    return environment


def run_cli(
    project: Path,
    *args: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one public Oldman command in the copied project.

    stdin is closed: the framework's questions do not read piped answers, so a command that
    needs one gets it from `environment` (preset answers) or fails naming the variable.
    """
    return subprocess.run(
        [sys.executable, "-m", "oldman.cli", *args],
        cwd=project,
        env={**project_environment(project), **(environment or {})},
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def run_python(project: Path, source: str) -> subprocess.CompletedProcess[str]:
    """Run a programmatic migration or service lifecycle in isolation."""
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=project,
        env=project_environment(project),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


class AdminDemoMigrationTests(unittest.TestCase):
    """Treat the Admin Demo as a normal deployable migration consumer."""

    def test_source_contract_has_one_service_config_and_no_runtime_ddl(self) -> None:
        """The demo installs its App explicitly and assumes deployment migrated."""
        self.assertFalse((ADMIN_DEMO / "data" / "settings.example.yaml").exists())
        settings_path = ADMIN_DEMO / "data" / "web_settings.example.yaml"
        self.assertTrue(settings_path.is_file())
        settings = YAML(typ="safe", pure=True).load(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(
            settings["apps"],
            [
                "oldman.auth",
                "oldman.apps.admin",
                "oldman.web.messages.notifications",
                "apps.demo",
            ],
        )

        self.assertTrue((ADMIN_DEMO / "apps" / "demo" / "apps.py").is_file())
        self.assertFalse((ADMIN_DEMO / "scripts" / "create_admin.py").exists())
        migrations = tuple(path for path in (ADMIN_DEMO / "apps" / "demo" / "migrations").glob("*.py") if path.name != "__init__.py")
        self.assertEqual(len(migrations), 1)
        service_source = (ADMIN_DEMO / "services" / "web.py").read_text(encoding="utf-8")
        self.assertNotIn("configure_admin_database", service_source)
        self.assertNotIn("create_db_and_tables", service_source)

    def test_clean_copy_migrates_then_runs_fixtures_and_admin_commands(self) -> None:
        """Settings, migrations and data writers work from an empty SQLite file."""
        with (
            tempfile.TemporaryDirectory() as temporary_directory,
            owned_redis_server(Path(temporary_directory) / "redis", environment=os.environ) as redis_url,
        ):
            project = copy_admin_demo(Path(temporary_directory), redis_url=redis_url)

            settings_sync = run_cli(project, "web", "settings", "sync")
            # `changepassword` below ends the user's sessions through this store: check it before anything runs.
            synced = YAML(typ="safe", pure=True).load((project / "data" / "web_settings.yaml").read_text(encoding="utf-8"))
            session_store = synced["redis"][synced["web"]["session"]["redis_alias"]]["redis_url"]
            self.assertTrue(session_store.startswith(redis_url), session_store)
            history = run_cli(project, "db", "history")
            before = run_cli(project, "db", "status")
            migrated = run_python(
                project,
                """
                from pathlib import Path

                from oldman.db.migrations.commands import migrate
                from oldman.db.migrations.project import load_migration_project

                project = load_migration_project(Path.cwd())

                class Answers:
                    is_interactive = False

                    def choose(self, prompt, choices):
                        assert "internal migration state" in prompt
                        return "first use"

                    def confirm(self, prompt, *, default=False):
                        raise AssertionError(prompt)

                    def text(self, prompt, *, default):
                        raise AssertionError(prompt)

                migrate(project, Answers())
                """,
            )
            after = run_cli(project, "db", "status")
            fixtures = run_cli(project, "web", "loaddata", "demo")
            unchanged_on_restart = run_python(
                project,
                """
                import asyncio
                from pathlib import Path
                from types import SimpleNamespace

                from oldman import bootstrap_service
                from oldman.db import db_manager
                from sqlalchemy import select
                from oldman.runtime.discovery import (
                    get_service_definition,
                    load_service_class,
                )

                async def main():
                    context = bootstrap_service("web")
                    from apps.demo.models import DemoProject
                    from oldman.auth.models import User

                    async with db_manager.get_session() as session:
                        first = await session.get(DemoProject, 1)
                        first.owner = "My own team"
                        await session.delete(await session.get(DemoProject, 2))
                        session.add(User(username="browser_staff", password_hash="my-hash", is_active=False, is_staff=False))
                        session.add(User(username="browser_lifecycle", password_hash="another-hash"))

                    async def snapshot():
                        async with db_manager.get_read_session() as session:
                            projects = list(await session.execute(select(DemoProject.__table__).order_by(DemoProject.id)))
                            users = list(await session.execute(select(User.__table__).order_by(User.id)))
                            return projects, users

                    before = await snapshot()
                    definition = get_service_definition("web", Path.cwd())
                    service_class = load_service_class(definition)
                    service = service_class(config=context)
                    app = SimpleNamespace(ctx=SimpleNamespace())
                    for _ in range(2):
                        await service.before_server_start(app)
                        await service.before_server_stop(app)
                        assert await snapshot() == before, "Restart changed project or account data"
                    await db_manager.close()

                asyncio.run(main())
                """,
            )
            create_admin = run_cli(
                project,
                "web",
                "createsuperuser",
                "--username",
                "migration_admin",
                "--email",
                "migration@example.com",
                "--noinput",
                environment={"OLDMAN_SUPERUSER_PASSWORD": "MigrationAdmin123"},
            )
            change_password = run_cli(
                project,
                "web",
                "changepassword",
                "migration_admin",
                environment={"OLDMAN_ANSWER_CHANGEPASSWORD_PASSWORD": "ChangedAdmin123"},
            )
            credentials = run_python(
                project,
                """
                import asyncio

                from oldman import bootstrap_service
                from oldman.auth import authenticate_user
                from oldman.db import db_manager

                bootstrap_service("web")

                async def main():
                    try:
                        old_password = await authenticate_user(
                            "migration_admin",
                            "MigrationAdmin123",
                        )
                        changed_password = await authenticate_user(
                            "migration_admin",
                            "ChangedAdmin123",
                        )
                        assert old_password is None
                        assert changed_password is not None
                        assert changed_password.is_staff
                        assert changed_password.is_superuser
                    finally:
                        await db_manager.close()

                asyncio.run(main())
                """,
            )

            database = project / "data" / "admin_demo.db"
            with sqlite3.connect(database) as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                registry = dict(connection.execute("SELECT table_name, app_label FROM oldman_schema_registry"))
                project_count = connection.execute("SELECT COUNT(*) FROM admin_demo_project").fetchone()[0]
                admin_count = connection.execute("SELECT COUNT(*) FROM oldman_user WHERE username='migration_admin'").fetchone()[0]

        self.assertEqual(settings_sync.returncode, 0, settings_sync.stderr)
        self.assertEqual(history.returncode, 0, history.stderr)
        self.assertIn("auth:", history.stdout)
        self.assertIn("demo:", history.stdout)
        self.assertEqual(before.returncode, 0, before.stderr)
        self.assertIn("not initialized", before.stdout.lower())
        self.assertIn("auth: current=none; heads=b7c396a46832; pending=b7c396a46832", before.stdout)
        self.assertIn("demo: current=none; heads=5742191f06e5; pending=5742191f06e5", before.stdout)
        self.assertEqual(migrated.returncode, 0, migrated.stdout + migrated.stderr)
        self.assertEqual(after.returncode, 0, after.stderr)
        self.assertIn("auth: current=", after.stdout)
        self.assertIn("demo: current=", after.stdout)
        self.assertEqual(fixtures.returncode, 0, fixtures.stdout + fixtures.stderr)
        self.assertEqual(unchanged_on_restart.returncode, 0, unchanged_on_restart.stdout + unchanged_on_restart.stderr)
        self.assertEqual(
            create_admin.returncode,
            0,
            create_admin.stdout + create_admin.stderr,
        )
        self.assertEqual(
            change_password.returncode,
            0,
            change_password.stdout + change_password.stderr,
        )
        self.assertEqual(
            credentials.returncode,
            0,
            credentials.stdout + credentials.stderr,
        )
        self.assertTrue(
            {
                "oldman_user",
                "admin_demo_project",
                "oldman_migration_owner",
                "oldman_schema_registry",
                "oldman_alembic_version",
            }.issubset(tables)
        )
        self.assertEqual(registry["oldman_user"], "auth")
        self.assertEqual(registry["oldman_notification"], "notifications")
        self.assertEqual(registry["admin_demo_project"], "demo")
        self.assertEqual(project_count, 24)  # The deleted fixture must not be recreated on restart.
        self.assertEqual(admin_count, 1)


if __name__ == "__main__":
    unittest.main()
