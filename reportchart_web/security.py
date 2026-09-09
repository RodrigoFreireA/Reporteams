"""Authentication policies and request guards.

The module owns security decisions that are independent from SQLAlchemy
models. Flask request/session objects are used only at the HTTP boundary.
"""

from __future__ import annotations

import secrets
import time
import unicodedata
from functools import wraps

from flask import g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .config import (
    LOGIN_RATE_LIMIT_LOCKOUT_SECONDS,
    LOGIN_RATE_LIMIT_MAX,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    PASSWORD_MIN_LENGTH,
)


LOGIN_FAILURES: dict[str, dict[str, object]] = {}


def _normalize_password(value: str) -> str:
    text = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def password_is_strong(password: str) -> bool:
    if len(password) < PASSWORD_MIN_LENGTH:
        return False
    has_alpha = any(ch.isalpha() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    normalized = _normalize_password(password)
    common_passwords = {
        "admin123456", "password123", "reportchart123", "senha123",
        "senha12345", "senha123456", "senha12345678",
    }
    if normalized in common_passwords or len(set(normalized)) < 4:
        return False
    return has_alpha and has_digit


def password_policy_message() -> str:
    return (
        f"A senha deve ter ao menos {PASSWORD_MIN_LENGTH} caracteres, com letras e numeros, "
        "sem padroes obvios."
    )


def hash_password(password: str) -> str:
    return generate_password_hash(password, method="scrypt")


def check_password(hash_value: str, password: str) -> bool:
    return check_password_hash(hash_value, password)


def login_rate_key(email: str) -> str:
    remote_addr = request.remote_addr or "unknown"
    return f"{remote_addr}:{email[:320]}"


def login_retry_after(email: str) -> int:
    if LOGIN_RATE_LIMIT_MAX <= 0:
        return 0
    now = time.monotonic()
    key = login_rate_key(email)
    record = LOGIN_FAILURES.get(key)
    if not record:
        return 0
    locked_until = float(record.get("locked_until") or 0)
    if locked_until > now:
        return max(1, int(locked_until - now))
    attempts = [
        attempt for attempt in record.get("attempts", [])
        if isinstance(attempt, (int, float)) and now - float(attempt) < LOGIN_RATE_LIMIT_WINDOW_SECONDS
    ]
    if attempts:
        record["attempts"] = attempts
    else:
        LOGIN_FAILURES.pop(key, None)
    return 0


def record_login_failure(email: str) -> int:
    if LOGIN_RATE_LIMIT_MAX <= 0:
        return 0
    now = time.monotonic()
    key = login_rate_key(email)
    record = LOGIN_FAILURES.setdefault(key, {"attempts": [], "locked_until": 0})
    attempts = [
        attempt for attempt in record.get("attempts", [])
        if isinstance(attempt, (int, float)) and now - float(attempt) < LOGIN_RATE_LIMIT_WINDOW_SECONDS
    ]
    attempts.append(now)
    record["attempts"] = attempts
    if len(attempts) >= LOGIN_RATE_LIMIT_MAX:
        locked_until = now + LOGIN_RATE_LIMIT_LOCKOUT_SECONDS
        record["locked_until"] = locked_until
        return max(1, int(locked_until - now))
    return 0


def clear_login_failures(email: str) -> None:
    LOGIN_FAILURES.pop(login_rate_key(email), None)


def rate_limited_response(retry_after: int):
    response = jsonify({
        "ok": False,
        "erro": "Muitas tentativas de login. Aguarde alguns minutos e tente novamente.",
    })
    response.status_code = 429
    response.headers["Retry-After"] = str(max(1, retry_after))
    return response


def csrf_valid() -> bool:
    expected = session.get("csrf_token")
    provided = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    return bool(expected and provided and secrets.compare_digest(expected, provided))


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.user:
            return jsonify({"ok": False, "erro": "Autenticação necessária."}), 401
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.user:
            return jsonify({"ok": False, "erro": "Autenticacao necessaria."}), 401
        if g.user.role != "admin":
            return jsonify({"ok": False, "erro": "Acesso restrito ao administrador."}), 403
        return fn(*args, **kwargs)
    return wrapper


def csrf_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not csrf_valid():
            return jsonify({"ok": False, "erro": "CSRF inválido."}), 403
        return fn(*args, **kwargs)
    return wrapper
