"""Saved Planner report endpoints."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging

from flask import Blueprint, g, jsonify, request

from reportchart_web.extensions import db
from reportchart_web.models import Team
from reportchart_web.repositories import ReportRepository, TeamRepository
from reportchart_web.security import csrf_required, login_required

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportServices:
    serialize_report: callable
    owned_report: callable
    load_payload: callable
    payload_from_request: callable
    team_is_visible: callable
    generate_summary: callable


def create_reports_blueprint(services: ReportServices) -> Blueprint:
    blueprint = Blueprint("reports", __name__)

    @blueprint.get("/api/reports")
    @login_required
    def list_reports():
        reports = ReportRepository.all_for_user(g.user.id)
        return jsonify({"ok": True, "reports": [services.serialize_report(report) for report in reports]})

    @blueprint.get("/api/reports/<int:report_id>")
    @login_required
    def get_report(report_id: int):
        report = services.owned_report(report_id)
        if not report:
            return jsonify({"ok": False, "erro": "Dashboard não encontrado."}), 404
        return jsonify({"ok": True, "report": services.serialize_report(report), "data": services.load_payload(report)})

    @blueprint.patch("/api/reports/<int:report_id>/team")
    @login_required
    @csrf_required
    def assign_report_team(report_id: int):
        report = services.owned_report(report_id)
        if not report:
            return jsonify({"ok": False, "erro": "Dashboard nao encontrado."}), 404
        payload = services.payload_from_request()
        raw_team_id = str(payload.get("team_id") or "").strip()
        team = None
        if raw_team_id:
            try:
                team_id = int(raw_team_id)
            except ValueError:
                return jsonify({"ok": False, "erro": "Equipe selecionada invalida."}), 400
            team = TeamRepository.by_id(team_id)
            if not team or not team.active or not services.team_is_visible(team):
                return jsonify({"ok": False, "erro": "Equipe selecionada nao encontrada ou inativa."}), 404
        report.team_id = team.id if team else None
        report.team_name_snapshot = team.name[:120] if team else None
        report.sprint_duration_days_snapshot = team.sprint_duration_days if team else None
        data = services.load_payload(report)
        meta = data.setdefault("meta", {})
        if team:
            meta.update({
                "team_id": team.id,
                "team_name": team.name,
                "team_project_name": team.project_name,
                "team_sprint_duration_days": team.sprint_duration_days,
                "team_sprint_mode": team.sprint_mode,
            })
        else:
            for key in ("team_id", "team_name", "team_project_name", "team_sprint_duration_days", "team_sprint_mode"):
                meta.pop(key, None)
        report.payload_json = json.dumps(data, ensure_ascii=False)
        db.session.commit()
        return jsonify({"ok": True, "report": services.serialize_report(report), "data": data})

    @blueprint.post("/api/reports/<int:report_id>/summary")
    @login_required
    @csrf_required
    def summarize_report(report_id: int):
        report = services.owned_report(report_id)
        if not report:
            return jsonify({"ok": False, "erro": "Dashboard não encontrado."}), 404
        payload = request.get_json(silent=True) or {}
        chart_id = str(payload.get("chart_id") or "").strip() or None
        filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
        try:
            summary = services.generate_summary(services.load_payload(report), chart_id=chart_id, filters=filters)
        except Exception:
            logger.exception("Falha ao gerar resumo do dashboard")
            return jsonify({"ok": False, "erro": "Falha ao gerar o resumo do dashboard."}), 500
        return jsonify({"ok": True, **summary})

    @blueprint.delete("/api/reports/<int:report_id>")
    @login_required
    @csrf_required
    def delete_report(report_id: int):
        report = services.owned_report(report_id)
        if not report:
            return jsonify({"ok": False, "erro": "Dashboard não encontrado."}), 404
        db.session.delete(report)
        db.session.commit()
        return jsonify({"ok": True})

    return blueprint
