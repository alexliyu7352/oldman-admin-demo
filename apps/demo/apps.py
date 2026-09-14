"""Installable metadata for the Admin Demo business models."""

from oldman.apps import AppConfig
from oldman.i18n import gettext_lazy as _


class DemoAppConfig(AppConfig):
    """Describe the models demonstrated by the standalone Admin service."""

    label = "demo"
    display_name = _("Admin Demo")
    icon = "ri-dashboard-line"


app = DemoAppConfig()

__all__ = ["DemoAppConfig", "app"]
