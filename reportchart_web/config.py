"""Environment-backed configuration for the ReportChart application.

This module deliberately contains no Flask or SQLAlchemy imports. Keeping
configuration here makes startup policy testable and prevents route modules
from owning environment parsing.
"""

from __future__ import annotations

import os
import secrets
import sys
import urllib.parse
from datetime import timedelta


APP_ENV = (os.environ.get("APP_ENV") or "development").strip().lower()
WEAK_SECRET_KEYS = {"change-me", "changeme", "troque-esta-chave", "secret", "password"}
PASSWORD_MIN_LENGTH = int((os.environ.get("PASSWORD_MIN_LENGTH") or "12").strip() or "12")
LOGIN_RATE_LIMIT_MAX = int((os.environ.get("LOGIN_RATE_LIMIT_MAX") or "5").strip() or "5")
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(
    (os.environ.get("LOGIN_RATE_LIMIT_WINDOW_SECONDS") or "900").strip() or "900"
)
LOGIN_RATE_LIMIT_LOCKOUT_SECONDS = int(
    (os.environ.get("LOGIN_RATE_LIMIT_LOCKOUT_SECONDS") or "900").strip() or "900"
)


def bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def default_data_root() -> str:
    configured = (os.environ.get("REPORTCHART_DATA_DIR") or "").strip()
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    if getattr(sys, "frozen", False):
        base_dir = (
            os.environ.get("LOCALAPPDATA")
            or os.environ.get("APPDATA")
            or os.path.expanduser("~")
        )
        return os.path.join(base_dir, "ReportChart")
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def generate_local_secret_key() -> str:
    """Generate an ephemeral key for local desktop sessions.

    Production deployments must provide APP_SECRET_KEY through a secret
    manager. Desktop sessions intentionally expire when the process restarts;
    this avoids persisting a signing secret as clear text on disk.
    """
    return secrets.token_urlsafe(48)


def default_database_uri() -> str:
    instance_dir = os.path.join(default_data_root(), "instance")
    os.makedirs(instance_dir, exist_ok=True)
    return f"sqlite:///{os.path.join(instance_dir, 'reportchart.db')}"


def normalize_database_uri(uri: str) -> str:
    if uri.startswith("postgres://"):
        return "postgresql+psycopg://" + uri[len("postgres://") :]
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg://" + uri[len("postgresql://") :]
    return uri


def secret_key_from_env() -> str:
    secret_key = os.environ.get("APP_SECRET_KEY")
    if APP_ENV == "production":
        weak_secret = (secret_key or "").strip().lower()
        if not secret_key or len(secret_key) < 32 or weak_secret in WEAK_SECRET_KEYS:
            raise RuntimeError(
                "APP_SECRET_KEY precisa ser definido em producao com pelo menos 32 caracteres."
            )
    if secret_key:
        return secret_key
    if APP_ENV == "desktop" or getattr(sys, "frozen", False):
        return generate_local_secret_key()
    return secrets.token_urlsafe(48)


def validated_base_url_from_env(name: str, default: str) -> str:
    raw_url = (os.environ.get(name) or default).strip().rstrip("/")
    parsed = urllib.parse.urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"{name} precisa usar URL http(s) valida.")
    return raw_url


def flask_config() -> dict[str, object]:
    """Return the complete Flask runtime configuration."""
    return {
        "MAX_CONTENT_LENGTH": 50 * 1024 * 1024,
        "SECRET_KEY": secret_key_from_env(),
        "SQLALCHEMY_DATABASE_URI": normalize_database_uri(
            os.environ.get("DATABASE_URL") or default_database_uri()
        ),
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SESSION_COOKIE_NAME": "reportchart_session",
        "SESSION_COOKIE_PATH": "/",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": bool_env(
            "SESSION_COOKIE_SECURE", default=(APP_ENV == "production")
        ),
        "SESSION_COOKIE_DOMAIN": os.environ.get("SESSION_COOKIE_DOMAIN") or None,
        "ALLOW_SELF_REGISTRATION": False,
        "AI_SUMMARY_PROVIDER": (os.environ.get("AI_SUMMARY_PROVIDER") or "heuristic").strip().lower(),
        "AI_SUMMARY_MODEL": (os.environ.get("AI_SUMMARY_MODEL") or "gemma3:1b").strip(),
        "AI_SUMMARY_OLLAMA_URL": validated_base_url_from_env(
            "AI_SUMMARY_OLLAMA_URL", "http://127.0.0.1:11434"
        ),
        "AI_SUMMARY_TIMEOUT": int((os.environ.get("AI_SUMMARY_TIMEOUT") or "60").strip() or "60"),
        "PERMANENT_SESSION_LIFETIME": timedelta(days=7),
    }
