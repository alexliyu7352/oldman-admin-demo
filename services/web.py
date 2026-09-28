"""Standalone Web service for the built-in Oldman Admin."""

from __future__ import annotations

import os

from config.settings import settings

from oldman.apps.admin import AdminSite, install_admin
from oldman.runtime.web import WebApplication
from oldman.web.staticfiles import app_bundle_registry, register_project_bundle

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


        admin_site = AdminSite("oldman_admin_demo")
        admin_site.register(DemoProject, DemoProjectAdmin)
        local_frontend = os.environ.get("OLDMAN_DEMO_SOURCE_FRONTEND") == "1"
        register_project_bundle(
            app_bundle_registry(app),
            name=ADMIN_EXTENSION_BUNDLE,
            entry_path=ADMIN_EXTENSION_ENTRY,
            static_root=settings.web.static.root,
            static_url=settings.web.static.url,
            dev_mode=local_frontend,
            dev_server_url=ADMIN_EXTENSION_DEV_SERVER if local_frontend else "",
        )
        install_admin(
            app,
            admin_site=admin_site,
            dev_mode=local_frontend,
            dev_server_url=(
                settings.web.frontend.vite_dev_server_url if local_frontend else ""
            ),
            extension_bundle_name=ADMIN_EXTENSION_BUNDLE,
        )

