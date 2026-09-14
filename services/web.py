"""Standalone Web service for the built-in Oldman Admin."""

from __future__ import annotations

import os
from pathlib import Path

from config.settings import settings

from oldman.apps.admin import AdminSite, AdminUserModelAdmin, install_admin
from oldman.apps.admin.apps import app as admin_app
from oldman.auth.apps import app as auth_app
from oldman.db import db_manager
from oldman.runtime.web import WebApplication
from oldman.web.routing import WebApp
from oldman.web.staticfiles import StaticBundle, StaticBundleRegistry

ADMIN_EXTENSION_BUNDLE = "app:admin-extension"
ADMIN_EXTENSION_ENTRY = "src/admin-extension.css"
ADMIN_EXTENSION_DEV_SERVER = "http://localhost:5174"


class WebService(WebApplication):
    """Serve a standalone, SQLite-backed Admin demonstration."""

    SERVICE_NAME = "Oldman Admin Demo"

    def get_ext_config(self) -> dict[str, object]:
        """Enable the async template environment required by Admin."""
        return {
            "oas": False,
            "oas_autodoc": False,
            "templating_path_to_templates": settings.web.template.dir,
            "templating_enable_async": True,
            "logging": False,
        }

    def init(self) -> None:
        """Install sessions and the complete built-in Admin runtime."""
        super().init()
        app = self.runtime_app
        if app is None:
            raise RuntimeError("Sanic app was not initialized")

        # Register the models already loaded by this service's App Registry.
        from apps.demo.admin import DemoProjectAdmin
        from apps.demo.models import DemoProject

        from oldman.auth.models import User

        admin_site = AdminSite("oldman_admin_demo")
        admin_site.register(User, AdminUserModelAdmin)
        admin_site.register(DemoProject, DemoProjectAdmin)
        static_url = str(settings.web.static.url).rstrip("/")
        local_frontend = os.environ.get("OLDMAN_DEMO_SOURCE_FRONTEND") == "1"
        bundle_registry = StaticBundleRegistry()
        bundle_registry.register(
            StaticBundle(
                name=ADMIN_EXTENSION_BUNDLE,
                entry_path=ADMIN_EXTENSION_ENTRY,
                manifest_path=Path(settings.web.static.root) / "dist" / ".vite" / "manifest.json",
                static_url=f"{static_url}/dist",
                dev_server_url=ADMIN_EXTENSION_DEV_SERVER if local_frontend else "",
                dev_mode=local_frontend,
            )
        )
        app.ctx.static_bundle_registry = bundle_registry
        install_admin(
            app,
            admin_site=admin_site,
            dev_mode=local_frontend,
            dev_server_url=(
                settings.web.frontend.vite_dev_server_url if local_frontend else ""
            ),
            extension_bundle_name=ADMIN_EXTENSION_BUNDLE,
            auth_settings=auth_app.settings,
            admin_settings=admin_app.settings,
        )

    async def before_server_stop(self, app: WebApp) -> None:
        """Close the demo database engine."""
        await super().before_server_stop(app)
        await db_manager.close()

    def prepare_server(self, app: WebApp) -> None:
        """Prepare the local single-process server."""
        app.prepare(
            host=settings.web.listen_host,
            port=settings.web.listen_port,
            debug=settings.web.debug,
            motd=False,
            auto_reload=settings.web.auto_reload,
            single_process=True,
            workers=settings.web.workers,
            access_log=settings.web.access_log,
        )
