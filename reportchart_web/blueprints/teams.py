"""Team administration HTTP endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from flask import Blueprint, g, jsonify

from reportchart_web.extensions import db
from reportchart_web.models import Team, TeamMember
from reportchart_web.repositories import TeamRepository, UserRepository
from reportchart_web.security import csrf_required, login_required


TEAM_ROLES = {"owner", "admin", "member"}
TEAM_MANAGEMENT_ROLES = {"owner", "admin"}
TEAM_MIN_SPRINT_DAYS = 1
TEAM_MAX_SPRINT_DAYS = 366


@dataclass(frozen=True)
class TeamServices:
    payload_from_request: callable
    serialize_team: callable
    serialize_user: callable
    team_is_visible: callable
    team_can_manage: callable
    is_admin: callable


def _team_payload(payload: dict, *, existing: Team | None = None) -> tuple[dict | None, str | None]:
    name = str(payload.get("name") if "name" in payload else (existing.name if existing else "")).strip()
    project_name = str(
        payload.get("project_name") if "project_name" in payload else (existing.project_name if existing else "")
    ).strip()
    raw_duration = payload.get("sprint_duration_days", existing.sprint_duration_days if existing else 15)
    try:
        duration = int(raw_duration)
    except (TypeError, ValueError):
        return None, "A duracao da sprint deve ser um numero inteiro de dias."
    sprint_mode = str(
        payload.get("sprint_mode") if "sprint_mode" in payload else (existing.sprint_mode if existing else "calendar")
    ).strip().lower()
    active = payload.get("active", existing.active if existing else True)
    if not name:
        return None, "Informe o nome da equipe."
    if len(name) > 120:
        return None, "O nome da equipe deve ter no maximo 120 caracteres."
    if duration < TEAM_MIN_SPRINT_DAYS or duration > TEAM_MAX_SPRINT_DAYS:
        return None, f"A duracao da sprint deve ficar entre {TEAM_MIN_SPRINT_DAYS} e {TEAM_MAX_SPRINT_DAYS} dias."
    if sprint_mode not in {"calendar", "business"}:
        return None, "Modo de contagem da sprint invalido."
    return {
        "name": name,
        "project_name": project_name[:160] or None,
        "sprint_duration_days": duration,
        "sprint_mode": sprint_mode,
        "active": bool(active),
    }, None


def create_teams_blueprint(services: TeamServices) -> Blueprint:
    blueprint = Blueprint("teams", __name__)

    @blueprint.get("/api/teams")
    @login_required
    def list_teams():
        teams = TeamRepository.all()
        visible = [team for team in teams if services.team_is_visible(team)]
        return jsonify({"ok": True, "teams": [services.serialize_team(team) for team in visible]})

    @blueprint.post("/api/teams")
    @login_required
    @csrf_required
    def create_team():
        values, error = _team_payload(services.payload_from_request())
        if error:
            return jsonify({"ok": False, "erro": error}), 400
        team = Team(owner_user_id=g.user.id, **values)
        db.session.add(team)
        db.session.flush()
        db.session.add(TeamMember(team_id=team.id, user_id=g.user.id, role="owner"))
        db.session.commit()
        return jsonify({"ok": True, "team": services.serialize_team(team, include_members=True)}), 201

    @blueprint.get("/api/teams/<int:team_id>")
    @login_required
    def get_team(team_id: int):
        team = TeamRepository.by_id(team_id)
        if not team or not services.team_is_visible(team):
            return jsonify({"ok": False, "erro": "Equipe nao encontrada."}), 404
        return jsonify({"ok": True, "team": services.serialize_team(team, include_members=True)})

    @blueprint.patch("/api/teams/<int:team_id>")
    @login_required
    @csrf_required
    def update_team(team_id: int):
        team = TeamRepository.by_id(team_id)
        if not team or not services.team_is_visible(team):
            return jsonify({"ok": False, "erro": "Equipe nao encontrada."}), 404
        if not services.team_can_manage(team):
            return jsonify({"ok": False, "erro": "Voce nao pode administrar esta equipe."}), 403
        values, error = _team_payload(services.payload_from_request(), existing=team)
        if error:
            return jsonify({"ok": False, "erro": error}), 400
        for key, value in values.items():
            setattr(team, key, value)
        db.session.commit()
        return jsonify({"ok": True, "team": services.serialize_team(team, include_members=True)})

    @blueprint.delete("/api/teams/<int:team_id>")
    @login_required
    @csrf_required
    def archive_team(team_id: int):
        team = TeamRepository.by_id(team_id)
        if not team or not services.team_is_visible(team):
            return jsonify({"ok": False, "erro": "Equipe nao encontrada."}), 404
        if not services.team_can_manage(team):
            return jsonify({"ok": False, "erro": "Voce nao pode administrar esta equipe."}), 403
        team.active = False
        db.session.commit()
        return jsonify({"ok": True, "team": services.serialize_team(team)})

    @blueprint.get("/api/teams/users")
    @login_required
    def list_team_users():
        can_manage = services.is_admin(g.user) or TeamRepository.can_manage_any(g.user.id, TEAM_MANAGEMENT_ROLES)
        if not can_manage:
            return jsonify({"ok": False, "erro": "Acesso restrito a administradores de equipe."}), 403
        return jsonify({"ok": True, "users": [services.serialize_user(user) for user in UserRepository.all_active()]})

    @blueprint.post("/api/teams/<int:team_id>/members")
    @login_required
    @csrf_required
    def add_team_member(team_id: int):
        team = TeamRepository.by_id(team_id)
        if not team or not services.team_is_visible(team):
            return jsonify({"ok": False, "erro": "Equipe nao encontrada."}), 404
        if not services.team_can_manage(team):
            return jsonify({"ok": False, "erro": "Voce nao pode administrar os membros desta equipe."}), 403
        payload = services.payload_from_request()
        try:
            user_id = int(payload.get("user_id"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "erro": "Selecione um usuario valido."}), 400
        role = str(payload.get("role") or "member").strip().lower()
        if role not in {"admin", "member"}:
            return jsonify({"ok": False, "erro": "Perfil de equipe invalido."}), 400
        user = UserRepository.by_id(user_id)
        if not user or user.role == "disabled":
            return jsonify({"ok": False, "erro": "Usuario nao encontrado ou desativado."}), 404
        membership = TeamRepository.membership(team.id, user.id)
        if membership:
            membership.role = role if user.id != team.owner_user_id else "owner"
        else:
            db.session.add(TeamMember(team_id=team.id, user_id=user.id, role=role))
        db.session.commit()
        return jsonify({"ok": True, "team": services.serialize_team(team, include_members=True)})

    @blueprint.delete("/api/teams/<int:team_id>/members/<int:user_id>")
    @login_required
    @csrf_required
    def remove_team_member(team_id: int, user_id: int):
        team = TeamRepository.by_id(team_id)
        if not team or not services.team_is_visible(team):
            return jsonify({"ok": False, "erro": "Equipe nao encontrada."}), 404
        if not services.team_can_manage(team):
            return jsonify({"ok": False, "erro": "Voce nao pode administrar os membros desta equipe."}), 403
        if team.owner_user_id == user_id:
            return jsonify({"ok": False, "erro": "O proprietario nao pode ser removido da equipe."}), 400
        membership = TeamRepository.membership(team.id, user_id)
        if not membership:
            return jsonify({"ok": False, "erro": "Membro nao encontrado."}), 404
        db.session.delete(membership)
        db.session.commit()
        return jsonify({"ok": True, "team": services.serialize_team(team, include_members=True)})

    return blueprint
