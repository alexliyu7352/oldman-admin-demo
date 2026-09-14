"""Typed settings for the standalone Admin demo."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from oldman.conf.schemas import (
    DatabaseConfig,
    DefaultSettings,
    FrontendConfig,
    I18nConfig,
    I18nLanguageConfig,
    SessionConfig,
    StaticConfig,
    StorageBackendConfig,
    StoragesConfig,
    TemplateConfig,
    WebConfig,
)

BASE_DIR = Path(__file__).resolve().parents[1]


def default_database_config() -> DatabaseConfig:
    """Return the demo's isolated SQLite database."""
    database_path = BASE_DIR / "data" / "admin_demo.db"
    return DatabaseConfig(url=f"sqlite+aiosqlite:///{database_path.as_posix()}")


def default_template_config() -> TemplateConfig:
    """Return the optional consumer template override directory."""
    return TemplateConfig(dir=BASE_DIR / "templates")


def default_static_config() -> StaticConfig:
    """Return the demo's collected static root and public URL."""
    return StaticConfig(
        dir=BASE_DIR / "static",
        root=str(BASE_DIR / "static"),
        url="/static",
    )


def default_storages_config() -> StoragesConfig:
    """Return the demo's isolated media filesystem storage."""
    return StoragesConfig(
        default=StorageBackendConfig(
            backend="oldman.storage.backends.filesystem.FileSystemStorage",
            options={"location": BASE_DIR / "media"},
        )
    )


def default_session_config() -> SessionConfig:
    """Return the Redis Session contract used by this standalone service."""
    return SessionConfig(
        enabled=True,
        expiry=86400,
        prefix="oldman_admin_demo_session:",
        user_prefix="oldman_admin_demo_user:",
        cookie_name="oldman_admin_demo_session_id",
    )


def default_web_config() -> WebConfig:
    """Assemble the demo's browser-facing service settings."""
    return WebConfig(
        session=default_session_config(),
        template=default_template_config(),
        static=default_static_config(),
        frontend=FrontendConfig(),
    )


def default_i18n_config() -> I18nConfig:
    """Enable the Admin's built-in common language menu by default."""
    return I18nConfig(
        use_i18n=True,
        default_language="en",
        languages={
            "en": I18nLanguageConfig(flag="us"),
            "zh-Hans": I18nLanguageConfig(flag="cn"),
            "zh-Hant": I18nLanguageConfig(flag="tw"),
        },
    )


class Settings(DefaultSettings):
    """Admin demo settings schema."""

    database: DatabaseConfig = Field(default_factory=default_database_config, description="Database settings")
    i18n: I18nConfig = Field(default_factory=default_i18n_config, description="Admin internationalization settings")
    web: WebConfig = Field(default_factory=default_web_config, description="Web service settings")
    storages: StoragesConfig = Field(default_factory=default_storages_config, description="Named file storage settings")
