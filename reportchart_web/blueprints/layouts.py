"""Saved report layout and version endpoints."""

from __future__ import annotations

from dataclasses import dataclass
import json

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

from reportchart_web.extensions import db
from reportchart_web.models import ReportLayout, ReportLayoutVersion
from reportchart_web.security import csrf_required, login_required


@dataclass(frozen=True)
class LayoutServices:
    owned_layout: callable
    serialize_layout: callable
    serialize_version: callable
    latest_version: callable
    load_payload: callable
    clean_title: callable
    clean_note: callable
    normalize_payload: callable
    payload_allowed: callable
    now_utc: callable


def create_layouts_blueprint(services: LayoutServices) -> Blueprint:
    blueprint = Blueprint("layouts", __name__)

    @blueprint.get("/api/report-layouts")
    @login_required
    def list_layouts():
        layouts = ReportLayout.query.filter(
            ReportLayout.user_id == g.user.id,
            ReportLayout.archived_at.is_(None),
        ).order_by(ReportLayout.updated_at.desc()).all()
        return jsonify({"ok": True, "layouts": [services.serialize_layout(layout) for layout in layouts]})

    @blueprint.post("/api/report-layouts")
    @login_required
    @csrf_required
    def create_layout():
        body = request.get_json(silent=True) or {}
        title = services.clean_title(body.get("title"))
        payload, report_ids, error = services.normalize_payload(body.get("payload"))
        if error:
            return jsonify({"ok": False, "erro": error}), 400
        if not services.payload_allowed(report_ids):
            return jsonify({"ok": False, "erro": "Um dos dashboards selecionados nao esta disponivel."}), 400
        payload["title"] = title
        layout = ReportLayout(user_id=g.user.id, title=title)
        db.session.add(layout)
        db.session.flush()
        version = ReportLayoutVersion(
            layout_id=layout.id, version_number=1,
            payload_json=json.dumps(payload, ensure_ascii=False),
            note=services.clean_note(body.get("note")) or "Criacao",
            created_by_user_id=g.user.id,
        )
        db.session.add(version)
        db.session.commit()
        return jsonify({"ok": True, "layout": services.serialize_layout(layout, version),
                        "version": services.serialize_version(version), "payload": payload})

    @blueprint.get("/api/report-layouts/<int:layout_id>")
    @login_required
    def get_layout(layout_id: int):
        layout = services.owned_layout(layout_id)
        if not layout:
            return jsonify({"ok": False, "erro": "Relatorio salvo nao encontrado."}), 404
        version = services.latest_version(layout)
        return jsonify({"ok": True, "layout": services.serialize_layout(layout, version),
                        "version": services.serialize_version(version), "payload": services.load_payload(version)})

    @blueprint.patch("/api/report-layouts/<int:layout_id>")
    @login_required
    @csrf_required
    def update_layout(layout_id: int):
        layout = services.owned_layout(layout_id)
        if not layout:
            return jsonify({"ok": False, "erro": "Relatorio salvo nao encontrado."}), 404
        body = request.get_json(silent=True) or {}
        if "title" in body:
            layout.title = services.clean_title(body.get("title"), default=layout.title)
        version = services.latest_version(layout)
        if "payload" in body:
            payload, report_ids, error = services.normalize_payload(body.get("payload"))
            if error:
                return jsonify({"ok": False, "erro": error}), 400
            if not services.payload_allowed(report_ids):
                return jsonify({"ok": False, "erro": "Um dos dashboards selecionados nao esta disponivel."}), 400
            payload["title"] = layout.title
            version = ReportLayoutVersion(
                layout_id=layout.id, version_number=int(version.version_number if version else 0) + 1,
                payload_json=json.dumps(payload, ensure_ascii=False),
                note=services.clean_note(body.get("note")) or "Atualizacao",
                created_by_user_id=g.user.id,
            )
            db.session.add(version)
        layout.updated_at = services.now_utc()
        db.session.commit()
        return jsonify({"ok": True, "layout": services.serialize_layout(layout, version),
                        "version": services.serialize_version(version), "payload": services.load_payload(version)})

    @blueprint.delete("/api/report-layouts/<int:layout_id>")
    @login_required
    @csrf_required
    def delete_layout(layout_id: int):
        layout = services.owned_layout(layout_id)
        if not layout:
            return jsonify({"ok": False, "erro": "Relatorio salvo nao encontrado."}), 404
        layout.archived_at = services.now_utc()
        layout.updated_at = services.now_utc()
        db.session.commit()
        return jsonify({"ok": True, "deleted_layout_id": layout_id})

    @blueprint.get("/api/report-layouts/<int:layout_id>/versions")
    @login_required
    def list_versions(layout_id: int):
        layout = services.owned_layout(layout_id)
        if not layout:
            return jsonify({"ok": False, "erro": "Relatorio salvo nao encontrado."}), 404
        versions = ReportLayoutVersion.query.filter_by(layout_id=layout.id).order_by(
            ReportLayoutVersion.version_number.desc()
        ).all()
        return jsonify({"ok": True, "layout": services.serialize_layout(layout, versions[0] if versions else None),
                        "versions": [services.serialize_version(version) for version in versions]})

    @blueprint.get("/api/report-layouts/<int:layout_id>/versions/<int:version_id>")
    @login_required
    def get_version(layout_id: int, version_id: int):
        layout = services.owned_layout(layout_id)
        if not layout:
            return jsonify({"ok": False, "erro": "Relatorio salvo nao encontrado."}), 404
        version = ReportLayoutVersion.query.filter_by(id=version_id, layout_id=layout.id).first()
        if not version:
            return jsonify({"ok": False, "erro": "Versao nao encontrada."}), 404
        return jsonify({"ok": True, "layout": services.serialize_layout(layout),
                        "version": services.serialize_version(version), "payload": services.load_payload(version)})

    @blueprint.delete("/api/report-layouts/<int:layout_id>/versions/<int:version_id>")
    @login_required
    @csrf_required
    def delete_version(layout_id: int, version_id: int):
        layout = services.owned_layout(layout_id)
        if not layout:
            return jsonify({"ok": False, "erro": "Relatorio salvo nao encontrado."}), 404
        version = ReportLayoutVersion.query.filter_by(id=version_id, layout_id=layout.id).first()
        if not version:
            return jsonify({"ok": False, "erro": "Versao nao encontrada."}), 404
        count = db.session.query(func.count(ReportLayoutVersion.id)).filter(
            ReportLayoutVersion.layout_id == layout.id
        ).scalar() or 0
        if int(count) <= 1:
            return jsonify({"ok": False, "erro": "Nao e possivel excluir a unica versao do relatorio."}), 400
        deleted_id = version.id
        db.session.delete(version)
        layout.updated_at = services.now_utc()
        db.session.commit()
        latest = services.latest_version(layout)
        return jsonify({"ok": True, "deleted_version_id": deleted_id,
                        "layout": services.serialize_layout(layout, latest),
                        "latest_version": services.serialize_version(latest)})

    @blueprint.post("/api/report-layouts/<int:layout_id>/versions/<int:version_id>/restore")
    @login_required
    @csrf_required
    def restore_version(layout_id: int, version_id: int):
        layout = services.owned_layout(layout_id)
        if not layout:
            return jsonify({"ok": False, "erro": "Relatorio salvo nao encontrado."}), 404
        source = ReportLayoutVersion.query.filter_by(id=version_id, layout_id=layout.id).first()
        if not source:
            return jsonify({"ok": False, "erro": "Versao nao encontrada."}), 404
        body = request.get_json(silent=True) or {}
        latest = services.latest_version(layout)
        restored = ReportLayoutVersion(
            layout_id=layout.id, version_number=int(latest.version_number if latest else 0) + 1,
            payload_json=source.payload_json,
            note=services.clean_note(body.get("note")) or f"Restaurada da versao {source.version_number}",
            created_by_user_id=g.user.id,
        )
        layout.updated_at = services.now_utc()
        db.session.add(restored)
        db.session.commit()
        return jsonify({"ok": True, "layout": services.serialize_layout(layout, restored),
                        "version": services.serialize_version(restored), "payload": services.load_payload(restored)})

    return blueprint
