"""Database initialization and first-admin bootstrap."""

from __future__ import annotations

import logging
import os
import sys

from sqlalchemy import inspect, text

from reportchart_web.config import APP_ENV
from reportchart_web.extensions import db
from reportchart_web.models import User
from reportchart_web.security import hash_password, password_is_strong

logger = logging.getLogger(__name__)


def ensure_user_session_columns() -> None:
    columns = {column["name"] for column in inspect(db.engine).get_columns("users")}
    column_type = "TIMESTAMP WITH TIME ZONE" if db.engine.dialect.name == "postgresql" else "DATETIME"
    with db.engine.begin() as connection:
        if "last_login_at" not in columns:
            connection.execute(text(f"ALTER TABLE users ADD COLUMN last_login_at {column_type}"))
        if "session_revoked_at" not in columns:
            connection.execute(text(f"ALTER TABLE users ADD COLUMN session_revoked_at {column_type}"))


def ensure_report_team_columns() -> None:
    columns = {column["name"] for column in inspect(db.engine).get_columns("reports")}
    column_type = "INTEGER"
    text_type = "VARCHAR(120)"
    with db.engine.begin() as connection:
        if "team_id" not in columns:
            connection.execute(text(f"ALTER TABLE reports ADD COLUMN team_id {column_type}"))
        if "team_name_snapshot" not in columns:
            connection.execute(text(f"ALTER TABLE reports ADD COLUMN team_name_snapshot {text_type}"))
        if "sprint_duration_days_snapshot" not in columns:
            connection.execute(text("ALTER TABLE reports ADD COLUMN sprint_duration_days_snapshot INTEGER"))


def ensure_default_admin() -> None:
    if APP_ENV != "desktop" and not getattr(sys, "frozen", False):
        return
    email = (os.environ.get("REPORTCHART_BOOTSTRAP_ADMIN_EMAIL") or "").strip().lower()
    password = os.environ.get("REPORTCHART_BOOTSTRAP_ADMIN_PASSWORD") or ""
    display_name = (os.environ.get("REPORTCHART_BOOTSTRAP_ADMIN_NAME") or "Administrador").strip()[:120]
    if not email and not password:
        return
    if not email or "@" not in email or not password_is_strong(password):
        raise RuntimeError(
            "Defina REPORTCHART_BOOTSTRAP_ADMIN_EMAIL e uma "
            "REPORTCHART_BOOTSTRAP_ADMIN_PASSWORD forte para o bootstrap automatico."
        )
    admin_exists = db.session.query(User.id).filter_by(email=email).first() is not None
    if admin_exists:
        return
    db.session.add(
        User(
            email=email,
            display_name=display_name or "Administrador",
            password_hash=hash_password(password),
            role="admin",
        )
    )
    db.session.commit()
    logger.info("Usuario administrador inicial criado para %s", email)


def initialize_database(app) -> None:
    with app.app_context():
        db.create_all()
        ensure_user_session_columns()
        ensure_report_team_columns()
        ensure_default_admin()
