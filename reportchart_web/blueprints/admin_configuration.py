"""Custom chart and profile-rule configuration endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from flask import Blueprint, g, jsonify

from reportchart_web.extensions import db
from reportchart_web.models import CustomChart, ProfileRule
from reportchart_web.repositories import CustomChartRepository, ProfileRuleRepository
from reportchart_web.security import admin_required, csrf_required, login_required


@dataclass(frozen=True)
class AdminConfigurationServices:
    payload_from_request: callable
    serialize_chart: callable
    normalize_chart: callable
    sync_chart_types: callable
    serialize_rule: callable
    normalize_rule: callable


def create_admin_configuration_blueprint(services: AdminConfigurationServices) -> Blueprint:
    blueprint = Blueprint("admin_configuration", __name__)

    @blueprint.get("/api/charts/custom")
    @login_required
    def list_custom_charts():
        charts = CustomChartRepository.enabled()
        return jsonify({"ok": True, "charts": [services.serialize_chart(chart) for chart in charts]})

    @blueprint.get("/api/admin/custom-charts")
    @login_required
    @admin_required
    def admin_list_custom_charts():
        charts = CustomChartRepository.all()
        return jsonify({"ok": True, "charts": [services.serialize_chart(chart) for chart in charts]})

    @blueprint.post("/api/admin/custom-charts")
    @login_required
    @admin_required
    @csrf_required
    def admin_create_custom_chart():
        try:
            normalized = services.normalize_chart(services.payload_from_request())
        except ValueError:
            return jsonify({"ok": False, "erro": "Dados do gráfico inválidos."}), 400
        available_types = normalized.pop("available_types")
        chart = CustomChart(created_by_user_id=g.user.id, **normalized)
        db.session.add(chart)
        db.session.flush()
        services.sync_chart_types(chart, available_types)
        db.session.commit()
        return jsonify({"ok": True, "chart": services.serialize_chart(chart)}), 201

    @blueprint.patch("/api/admin/custom-charts/<int:chart_id>")
    @login_required
    @admin_required
    @csrf_required
    def admin_update_custom_chart(chart_id: int):
        chart = CustomChartRepository.by_id(chart_id)
        if not chart:
            return jsonify({"ok": False, "erro": "Grafico customizado nao encontrado."}), 404
        try:
            normalized = services.normalize_chart(services.payload_from_request(), current=chart)
        except ValueError:
            return jsonify({"ok": False, "erro": "Dados do gráfico inválidos."}), 400
        available_types = normalized.pop("available_types")
        for key, value in normalized.items():
            setattr(chart, key, value)
        services.sync_chart_types(chart, available_types)
        db.session.commit()
        return jsonify({"ok": True, "chart": services.serialize_chart(chart)})

    @blueprint.delete("/api/admin/custom-charts/<int:chart_id>")
    @login_required
    @admin_required
    @csrf_required
    def admin_delete_custom_chart(chart_id: int):
        chart = CustomChartRepository.by_id(chart_id)
        if not chart:
            return jsonify({"ok": False, "erro": "Grafico customizado nao encontrado."}), 404
        db.session.delete(chart)
        db.session.commit()
        return jsonify({"ok": True, "deleted_chart_id": chart_id})

    @blueprint.get("/api/profile-rules")
    @login_required
    def list_profile_rules():
        rules = ProfileRuleRepository.enabled()
        return jsonify({"ok": True, "rules": [services.serialize_rule(rule) for rule in rules]})

    @blueprint.get("/api/admin/profile-rules")
    @login_required
    @admin_required
    def admin_list_profile_rules():
        rules = ProfileRuleRepository.all()
        return jsonify({"ok": True, "rules": [services.serialize_rule(rule) for rule in rules]})

    @blueprint.post("/api/admin/profile-rules")
    @login_required
    @admin_required
    @csrf_required
    def admin_create_profile_rule():
        try:
            normalized = services.normalize_rule(services.payload_from_request())
        except ValueError:
            return jsonify({"ok": False, "erro": "Dados do perfil inválidos."}), 400
        rule = ProfileRule(created_by_user_id=g.user.id, **normalized)
        db.session.add(rule)
        db.session.commit()
        return jsonify({"ok": True, "rule": services.serialize_rule(rule)}), 201

    @blueprint.patch("/api/admin/profile-rules/<int:rule_id>")
    @login_required
    @admin_required
    @csrf_required
    def admin_update_profile_rule(rule_id: int):
        rule = ProfileRuleRepository.by_id(rule_id)
        if not rule:
            return jsonify({"ok": False, "erro": "Perfil customizado nao encontrado."}), 404
        try:
            normalized = services.normalize_rule(services.payload_from_request(), current=rule)
        except ValueError:
            return jsonify({"ok": False, "erro": "Dados do perfil inválidos."}), 400
        for key, value in normalized.items():
            setattr(rule, key, value)
        db.session.commit()
        return jsonify({"ok": True, "rule": services.serialize_rule(rule)})

    @blueprint.delete("/api/admin/profile-rules/<int:rule_id>")
    @login_required
    @admin_required
    @csrf_required
    def admin_delete_profile_rule(rule_id: int):
        rule = ProfileRuleRepository.by_id(rule_id)
        if not rule:
            return jsonify({"ok": False, "erro": "Perfil customizado nao encontrado."}), 404
        db.session.delete(rule)
        db.session.commit()
        return jsonify({"ok": True, "deleted_rule_id": rule_id})

    return blueprint
