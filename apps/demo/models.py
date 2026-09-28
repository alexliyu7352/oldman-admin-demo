"""Small business model used by the Admin demo."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, Integer, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from oldman.db.models import DatabaseModel
from oldman.i18n import gettext_lazy as _


class DemoProject(DatabaseModel):
    """Editable project record used to demonstrate generic Admin CRUD."""

    __tablename__ = "admin_demo_project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    owner: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    class Meta:
        """Provide request-time labels for automatic Admin presentation."""

        verbose_name = _("Project")
        verbose_name_plural = _("Projects")
