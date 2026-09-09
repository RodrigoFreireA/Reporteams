"""Planner roadmap and Excel upload endpoints."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import shutil
import tempfile
import zipfile

from flask import Blueprint, g, jsonify, request
from werkzeug.utils import secure_filename

from reportchart_web.extensions import db
from reportchart_web.models import Report, Team
from reportchart_web.repositories import RoadmapRepository
from reportchart_web.security import csrf_required, login_required

logger = logging.getLogger(__name__)

MAX_XLSX_ZIP_MEMBERS = 2_000
MAX_XLSX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


def _is_safe_xlsx_archive(path: str) -> bool:
    """Reject malformed or oversized ZIP containers before Excel parsing."""
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > MAX_XLSX_ZIP_MEMBERS:
                return False

            total_size = 0
            for member in members:
                normalized_name = member.filename.replace("\\", "/")
                if normalized_name.startswith("/") or ".." in normalized_name.split("/"):
                    return False
                if member.file_size < 0:
                    return False
                total_size += member.file_size
                if total_size > MAX_XLSX_UNCOMPRESSED_BYTES:
                    return False
    except (OSError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return False
    return True


@dataclass(frozen=True)
class PlannerServices:
    serialize_roadmap: callable
    owned_roadmap: callable
    parse_saved_items: callable
    parse_manual_items: callable
    save_roadmap: callable
    compute_json: callable
    serialize_report: callable
    team_is_visible: callable


def create_planner_blueprint(services: PlannerServices) -> Blueprint:
    blueprint = Blueprint("planner", __name__)

    @blueprint.get("/api/roadmaps")
    @login_required
    def list_saved_roadmaps():
        roadmaps = RoadmapRepository.all_for_user(g.user.id)
        return jsonify({"ok": True, "roadmaps": [services.serialize_roadmap(item) for item in roadmaps]})

    @blueprint.get("/api/roadmaps/<int:roadmap_id>")
    @login_required
    def get_saved_roadmap(roadmap_id: int):
        roadmap = services.owned_roadmap(roadmap_id)
        if not roadmap:
            return jsonify({"ok": False, "erro": "Roadmap nao encontrado."}), 404
        return jsonify({"ok": True, "roadmap": services.serialize_roadmap(roadmap)})

    @blueprint.post("/upload")
    @login_required
    @csrf_required
    def upload():
        if "arquivo" not in request.files:
            return jsonify({"ok": False, "erro": "Nenhum arquivo enviado."}), 400

        arquivo = request.files["arquivo"]
        if not arquivo.filename:
            return jsonify({"ok": False, "erro": "Nome de arquivo vazio."}), 400

        safe_name = secure_filename(arquivo.filename)
        if not safe_name or not safe_name.lower().endswith(".xlsx"):
            return jsonify({"ok": False, "erro": "Envie um .xlsx exportado do Microsoft Planner."}), 400

        planner_format = (request.form.get("planner_format") or "legacy").strip().lower()
        if planner_format not in {"legacy", "teams_new"}:
            return jsonify({"ok": False, "erro": "Formato de Excel nao reconhecido."}), 400

        ignore_labels = request.form.get("rotulos_ignorar", "").strip() or None
        selected_roadmap = None
        selected_roadmap_items: list[list[object]] = []
        manual_roadmap_items: list[list[object]] = []
        try:
            raw_roadmap_id = str(request.form.get("roadmap_id") or "").strip()
            if raw_roadmap_id:
                try:
                    roadmap_id = int(raw_roadmap_id)
                except ValueError as exc:
                    raise ValueError("Roadmap selecionado invalido.") from exc
                selected_roadmap = services.owned_roadmap(roadmap_id)
                if not selected_roadmap:
                    return jsonify({"ok": False, "erro": "Roadmap selecionado nao encontrado."}), 404
                selected_roadmap_items = services.parse_saved_items(selected_roadmap)
            else:
                manual_roadmap_items = services.parse_manual_items(request.form.get("roadmap_json"))
        except ValueError:
            return jsonify({"ok": False, "erro": "Roadmap inválido."}), 400

        selected_team = None
        raw_team_id = str(request.form.get("team_id") or "").strip()
        if raw_team_id:
            try:
                team_id = int(raw_team_id)
            except ValueError:
                return jsonify({"ok": False, "erro": "Equipe selecionada invalida."}), 400
            selected_team = db.session.get(Team, team_id)
            if not selected_team or not selected_team.active or not services.team_is_visible(selected_team):
                return jsonify({"ok": False, "erro": "Equipe selecionada nao encontrada ou inativa."}), 404

        work_dir = tempfile.mkdtemp()
        input_path = os.path.join(work_dir, "input.xlsx")
        arquivo.save(input_path)
        if not zipfile.is_zipfile(input_path) or not _is_safe_xlsx_archive(input_path):
            shutil.rmtree(work_dir, ignore_errors=True)
            return jsonify({"ok": False, "erro": "Arquivo .xlsx inválido."}), 400

        try:
            data = services.compute_json(input_path, ignore_labels=ignore_labels, planner_format=planner_format)
            upload_roadmap_items = selected_roadmap_items or manual_roadmap_items
            associated_roadmap = selected_roadmap
            if upload_roadmap_items:
                data["roadmap_items"] = upload_roadmap_items
                data["warnings"] = [
                    warning for warning in data.get("warnings", [])
                    if "roadmap" not in str(warning.get("msg", "")).lower()
                ]
            meta = data.setdefault("meta", {})
            if selected_team:
                meta.update({
                    "team_id": selected_team.id,
                    "team_name": selected_team.name,
                    "team_project_name": selected_team.project_name,
                    "team_sprint_duration_days": selected_team.sprint_duration_days,
                    "team_sprint_mode": selected_team.sprint_mode,
                })
            if manual_roadmap_items:
                associated_roadmap = services.save_roadmap(
                    items=manual_roadmap_items,
                    title=request.form.get("roadmap_title"),
                    project_date=request.form.get("roadmap_project_date"),
                    source_filename=safe_name,
                    project_name=(meta.get("projeto") or None),
                )
                if associated_roadmap:
                    db.session.flush()
            if associated_roadmap:
                meta["roadmap_source"] = services.serialize_roadmap(associated_roadmap, include_items=False)
            report = Report(
                user_id=g.user.id,
                title=(meta.get("sprint_name") or os.path.splitext(safe_name)[0])[:160],
                source_filename=safe_name[:255],
                project_name=(meta.get("projeto") or "")[:160] or None,
                sprint_name=(meta.get("sprint_name") or "")[:160] or None,
                export_date=(meta.get("export_date") or "")[:32] or None,
                team_id=selected_team.id if selected_team else None,
                team_name_snapshot=selected_team.name[:120] if selected_team else None,
                sprint_duration_days_snapshot=selected_team.sprint_duration_days if selected_team else None,
                payload_json=json.dumps(data, ensure_ascii=False),
            )
            db.session.add(report)
            db.session.commit()
            return jsonify({
                "ok": True,
                "report": services.serialize_report(report),
                "data": data,
                "roadmap": services.serialize_roadmap(associated_roadmap) if associated_roadmap else None,
            })
        except ValueError:
            return jsonify({"ok": False, "erro": "Dados do Planner inválidos."}), 400
        except Exception:
            logger.exception("Falha ao processar upload do Planner")
            return jsonify({"ok": False, "erro": "Falha ao processar o arquivo."}), 500
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    return blueprint
