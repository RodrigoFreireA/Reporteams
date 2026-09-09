"""Authentication policies and request guards.

The module owns security decisions that are independent from SQLAlchemy
models. Flask request/session objects are used only at the HTTP boundary.
"""

from __future__ import annotations

import secrets
import hashlib
import logging
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
    RATE_LIMIT_REDIS_URL,
)

try:
    import redis
except ImportError:  # pragma: no cover - optional for local development
    redis = None


logger = logging.getLogger(__name__)
_REDIS_CLIENT = None
_REDIS_UNAVAILABLE = False

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


def _redis_client():
    global _REDIS_CLIENT, _REDIS_UNAVAILABLE
    if _REDIS_UNAVAILABLE or not RATE_LIMIT_REDIS_URL or redis is None:
        return None
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    try:
        _REDIS_CLIENT = redis.Redis.from_url(
            RATE_LIMIT_REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        _REDIS_CLIENT.ping()
        return _REDIS_CLIENT
    except Exception:
        logger.warning("Redis indisponivel; usando rate limit local neste processo.")
        _REDIS_CLIENT = None
        _REDIS_UNAVAILABLE = True
        return None


def _redis_key(email: str, suffix: str) -> str:
    digest = hashlib.sha256(login_rate_key(email).encode("utf-8")).hexdigest()
    return f"reportchart:login:{digest}:{suffix}"


def _memory_login_retry_after(email: str) -> int:
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


def login_retry_after(email: str) -> int:
    client = _redis_client()
    if client is not None:
        try:
            ttl = client.ttl(_redis_key(email, "lock"))
            return max(1, int(ttl)) if ttl and ttl > 0 else 0
        except Exception:
            logger.warning("Falha no Redis; mantendo fallback local do rate limit.")
    return _memory_login_retry_after(email)


def _memory_record_login_failure(email: str) -> int:
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


def record_login_failure(email: str) -> int:
    client = _redis_client()
    if client is not None:
        try:
            attempts_key = _redis_key(email, "attempts")
            attempts = int(client.incr(attempts_key))
            if attempts == 1:
                client.expire(attempts_key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
            if attempts >= LOGIN_RATE_LIMIT_MAX:
                client.set(
                    _redis_key(email, "lock"),
                    "1",
                    ex=LOGIN_RATE_LIMIT_LOCKOUT_SECONDS,
                )
                return LOGIN_RATE_LIMIT_LOCKOUT_SECONDS
            return 0
        except Exception:
            logger.warning("Falha no Redis; mantendo fallback local do rate limit.")
    return _memory_record_login_failure(email)


def clear_login_failures(email: str) -> None:
    client = _redis_client()
    if client is not None:
        try:
            client.delete(_redis_key(email, "attempts"), _redis_key(email, "lock"))
        except Exception:
            logger.warning("Falha ao limpar rate limit compartilhado.")
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
