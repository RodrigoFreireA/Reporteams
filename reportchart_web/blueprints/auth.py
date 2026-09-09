"""Session authentication HTTP endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from flask import Blueprint, g, jsonify, session

from reportchart_web.extensions import db
from reportchart_web.models import User
from reportchart_web.repositories import UserRepository
from reportchart_web.security import (
    check_password,
    clear_login_failures,
    csrf_required,
    hash_password,
    login_required,
    login_retry_after,
    password_is_strong,
    password_policy_message,
    rate_limited_response,
    record_login_failure,
)


@dataclass(frozen=True)
class AuthServices:
    bootstrap_required: callable
    self_registration_allowed: callable
    payload_from_request: callable
    serialize_user: callable
    login_user: callable
    logout_user: callable
    record_successful_login: callable


def create_auth_blueprint(services: AuthServices) -> Blueprint:
    blueprint = Blueprint("auth", __name__)

    @blueprint.get("/api/me")
    def me():
        if not g.user:
            return jsonify(
                {
                    "ok": True,
                    "authenticated": False,
                    "bootstrap_required": services.bootstrap_required(),
                    "allow_self_registration": services.self_registration_allowed(),
                }
            )
        return jsonify(
            {
                "ok": True,
                "authenticated": True,
                "bootstrap_required": False,
                "allow_self_registration": services.self_registration_allowed(),
                "csrf_token": session.get("csrf_token"),
                "user": services.serialize_user(g.user),
            }
        )

    @blueprint.post("/api/bootstrap")
    def bootstrap():
        if not services.bootstrap_required():
            return jsonify({"ok": False, "erro": "Bootstrap já concluído."}), 409
        payload = services.payload_from_request()
        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password") or ""
        display_name = (payload.get("display_name") or "").strip() or "Administrador"
        if not email or "@" not in email:
            return jsonify({"ok": False, "erro": "Informe um e-mail válido."}), 400
        if not password_is_strong(password):
            return jsonify({"ok": False, "erro": password_policy_message()}), 400
        user = User(
            email=email,
            display_name=display_name[:120],
            password_hash=hash_password(password),
            role="admin",
        )
        db.session.add(user)
        db.session.commit()
        services.login_user(user)
        return jsonify(
            {
                "ok": True,
                "authenticated": True,
                "csrf_token": session.get("csrf_token"),
                "user": services.serialize_user(user),
            }
        )

    @blueprint.post("/api/login")
    def login():
        if services.bootstrap_required():
            return jsonify({"ok": False, "erro": "Crie o primeiro usuário antes de entrar."}), 409
        payload = services.payload_from_request()
        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password") or ""
        retry_after = login_retry_after(email)
        if retry_after:
            return rate_limited_response(retry_after)
        user = UserRepository.by_email(email)
        if not user or not check_password(user.password_hash, password):
            retry_after = record_login_failure(email)
            if retry_after:
                return rate_limited_response(retry_after)
            return jsonify({"ok": False, "erro": "Credenciais inválidas."}), 401
        if user.role == "disabled":
            return jsonify({"ok": False, "erro": "Usuario desativado."}), 403
        clear_login_failures(email)
        services.record_successful_login(user)
        services.login_user(user)
        return jsonify(
            {
                "ok": True,
                "authenticated": True,
                "csrf_token": session.get("csrf_token"),
                "user": services.serialize_user(user),
            }
        )

    @blueprint.post("/api/register")
    def register():
        return jsonify({"ok": False, "erro": "Cadastro publico desativado."}), 403

    @blueprint.post("/api/logout")
    @login_required
    @csrf_required
    def logout():
        services.logout_user()
        return jsonify({"ok": True})

    return blueprint
