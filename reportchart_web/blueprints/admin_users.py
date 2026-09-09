"""Administrative user management endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from flask import Blueprint, g, jsonify
from sqlalchemy import func

from reportchart_web.extensions import db
from reportchart_web.models import Report, ReportLayout, ReportLayoutVersion, User
from reportchart_web.repositories import UserRepository
from reportchart_web.security import (
    admin_required,
    csrf_required,
    hash_password,
    login_required,
    password_is_strong,
    password_policy_message,
)


@dataclass(frozen=True)
class AdminUserServices:
    payload_from_request: callable
    serialize_user: callable
    user_role_allowed: callable
    admin_count: callable
    now_utc: callable


def create_admin_users_blueprint(services: AdminUserServices) -> Blueprint:
    blueprint = Blueprint("admin_users", __name__)

    def report_count(user_id: int) -> int:
        return db.session.query(func.count(Report.id)).filter(Report.user_id == user_id).scalar() or 0

    @blueprint.get("/api/admin/users")
    @login_required
    @admin_required
    def list_users():
        counts = {
            user_id: int(count)
            for user_id, count in db.session.query(Report.user_id, func.count(Report.id)).group_by(Report.user_id).all()
        }
        return jsonify({
            "ok": True,
            "users": [services.serialize_user(user, report_count=counts.get(user.id, 0)) for user in UserRepository.all()],
        })

    @blueprint.post("/api/admin/users")
    @login_required
    @admin_required
    @csrf_required
    def create_user():
        payload = services.payload_from_request()
        email = (payload.get("email") or "").strip().lower()
        display_name = (payload.get("display_name") or "").strip()
        password = payload.get("password") or ""
        role = (payload.get("role") or "user").strip().lower()
        if not display_name:
            return jsonify({"ok": False, "erro": "Informe o nome do usuario."}), 400
        if not email or "@" not in email:
            return jsonify({"ok": False, "erro": "Informe um e-mail valido."}), 400
        if not services.user_role_allowed(role, allow_disabled=True):
            return jsonify({"ok": False, "erro": "Perfil de usuario invalido."}), 400
        if not password_is_strong(password):
            return jsonify({"ok": False, "erro": password_policy_message()}), 400
        if UserRepository.by_email(email):
            return jsonify({"ok": False, "erro": "Ja existe um usuario com esse e-mail."}), 409
        user = User(email=email, display_name=display_name[:120], password_hash=hash_password(password), role=role)
        db.session.add(user)
        db.session.commit()
        return jsonify({"ok": True, "user": services.serialize_user(user, report_count=0)}), 201

    @blueprint.patch("/api/admin/users/<int:user_id>")
    @login_required
    @admin_required
    @csrf_required
    def update_user(user_id: int):
        user = UserRepository.by_id(user_id)
        if not user:
            return jsonify({"ok": False, "erro": "Usuario nao encontrado."}), 404
        payload = services.payload_from_request()
        display_name = (payload.get("display_name") or "").strip()
        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password") or ""
        requested_role = payload.get("role")
        if not display_name or not email or "@" not in email:
            return jsonify({"ok": False, "erro": "Informe nome e e-mail validos."}), 400
        existing = User.query.filter(User.email == email, User.id != user.id).first()
        if existing:
            return jsonify({"ok": False, "erro": "Ja existe um usuario com esse e-mail."}), 409
        if requested_role is not None:
            requested_role = str(requested_role).strip().lower()
            if not services.user_role_allowed(requested_role, allow_disabled=True):
                return jsonify({"ok": False, "erro": "Perfil de usuario invalido."}), 400
            if user.id == g.user.id and requested_role != "admin":
                return jsonify({"ok": False, "erro": "Voce nao pode remover seu proprio acesso admin."}), 400
            if user.role == "admin" and requested_role != "admin" and services.admin_count() <= 1:
                return jsonify({"ok": False, "erro": "Nao e possivel remover o ultimo admin."}), 400
            user.role = requested_role
        if password:
            if not password_is_strong(password):
                return jsonify({"ok": False, "erro": password_policy_message()}), 400
            user.password_hash = hash_password(password)
        user.display_name, user.email = display_name[:120], email
        db.session.commit()
        response = {"ok": True, "user": services.serialize_user(user, report_count=report_count(user.id))}
        if user.id == g.user.id:
            response["current_user"] = services.serialize_user(user)
        return jsonify(response)

    @blueprint.post("/api/admin/users/<int:user_id>/sessions/revoke")
    @login_required
    @admin_required
    @csrf_required
    def revoke_sessions(user_id: int):
        user = UserRepository.by_id(user_id)
        if not user:
            return jsonify({"ok": False, "erro": "Usuario nao encontrado."}), 404
        if user.id == g.user.id:
            return jsonify({"ok": False, "erro": "Use sair para encerrar sua propria sessao."}), 400
        user.session_revoked_at = services.now_utc()
        db.session.commit()
        return jsonify({"ok": True, "user": services.serialize_user(user, report_count=report_count(user.id))})

    @blueprint.delete("/api/admin/users/<int:user_id>")
    @login_required
    @admin_required
    @csrf_required
    def delete_user(user_id: int):
        user = UserRepository.by_id(user_id)
        if not user:
            return jsonify({"ok": False, "erro": "Usuario nao encontrado."}), 404
        if user.id == g.user.id:
            return jsonify({"ok": False, "erro": "Voce nao pode excluir sua propria conta."}), 400
        if user.role == "admin" and services.admin_count() <= 1:
            return jsonify({"ok": False, "erro": "Nao e possivel excluir o ultimo admin."}), 400
        layout_ids = [row[0] for row in db.session.query(ReportLayout.id).filter(ReportLayout.user_id == user.id).all()]
        if layout_ids:
            ReportLayoutVersion.query.filter(ReportLayoutVersion.layout_id.in_(layout_ids)).delete(synchronize_session=False)
            ReportLayout.query.filter(ReportLayout.id.in_(layout_ids)).delete(synchronize_session=False)
        Report.query.filter_by(user_id=user.id).delete(synchronize_session=False)
        db.session.delete(user)
        db.session.commit()
        return jsonify({"ok": True, "deleted_user_id": user_id})

    return blueprint
