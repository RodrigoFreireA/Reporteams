"""
ReportChart Web backend.

Suporta:
- autenticacao por sessao
- bootstrap do primeiro usuario
- upload autenticado do .xlsx
- persistencia de dashboards por usuario
"""

import json
import logging
import mimetypes
import os
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
from datetime import datetime, timedelta, timezone

from flask import Flask, g, jsonify, redirect, request, session
from sqlalchemy import func
from werkzeug.middleware.proxy_fix import ProxyFix

from reportchart_web.config import (
    APP_ENV,
    LOGIN_RATE_LIMIT_LOCKOUT_SECONDS,
    LOGIN_RATE_LIMIT_MAX,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    PASSWORD_MIN_LENGTH,
    flask_config,
)
from reportchart_web.extensions import db
from reportchart_web.bootstrap import initialize_database
from reportchart_web.summary_provider import generate_ollama_summary
from reportchart_web.chart_configuration import (
    normalize_custom_chart_payload,
    normalize_profile_rule_payload,
    serialize_custom_chart,
    sync_custom_chart_types,
)
from reportchart_web.planner.roadmaps import (
    parse_saved_roadmap_items,
    parse_upload_roadmap_items,
    save_uploaded_roadmap,
    serialize_saved_roadmap,
)
from reportchart_web.security import (
    LOGIN_FAILURES,
    admin_required,
    check_password as _check_password,
    clear_login_failures as _clear_login_failures,
    csrf_required,
    login_required,
    login_retry_after as _login_retry_after,
    password_policy_message as _password_policy_message,
    rate_limited_response as _rate_limited_response,
    record_login_failure as _record_login_failure,
)

# Localiza generate_dashboard.py e assets tanto no codigo-fonte quanto no exe.
_here = os.path.dirname(os.path.abspath(__file__))
_RESOURCE_DIR = getattr(sys, "_MEIPASS", _here)
for _path in (_RESOURCE_DIR, _here):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from generate_dashboard import compute_json  # noqa: E402

logger = logging.getLogger(__name__)

# Garante Content-Type correto para assets estáticos em ambientes Windows/local.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_session_timestamp(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return _ensure_aware_utc(parsed)


app = Flask(
    __name__,
    static_folder=os.path.join(_RESOURCE_DIR, "static"),
    static_url_path="/static",
)
app.config.update(flask_config())
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

db.init_app(app)

from reportchart_web.models import (
    CustomChart,
    ProfileRule,
    Report,
    ReportLayout,
    ReportLayoutVersion,
    SavedRoadmap,
    Team,
    TeamMember,
    User,
)
from reportchart_web.repositories import ReportRepository, RoadmapRepository, TeamRepository, UserRepository
from reportchart_web.blueprints.auth import AuthServices, create_auth_blueprint
from reportchart_web.blueprints.public import create_public_blueprint
from reportchart_web.blueprints.teams import TeamServices, create_teams_blueprint
from reportchart_web.blueprints.admin_users import AdminUserServices, create_admin_users_blueprint
from reportchart_web.blueprints.admin_configuration import (
    AdminConfigurationServices,
    create_admin_configuration_blueprint,
)
from reportchart_web.blueprints.layouts import LayoutServices, create_layouts_blueprint
from reportchart_web.blueprints.reports import ReportServices, create_reports_blueprint
from reportchart_web.blueprints.planner import PlannerServices, create_planner_blueprint

LOGIN_FAILURES: dict[str, dict[str, object]] = {}

INDEX_HTML = os.path.join(_RESOURCE_DIR, "index.html")
VIEWS_DIR = os.path.join(_RESOURCE_DIR, "views")
app.register_blueprint(create_public_blueprint(INDEX_HTML, VIEWS_DIR))


USER_ROLES = {"admin", "user", "disabled"}
MANAGED_ROLES = {"admin", "user"}
SUMMARY_SCOPE_LABELS = {
    "kpis": "KPIs da Sprint",
    "delivery_person": "Entrega por Pessoa",
    "burndown": "Burndown Geral",
    "burndown_hu": "Burndown por HU",
    "burndown_sp": "Burndown por Story Points",
    "burnup": "Burnup Geral",
    "burnup_hu": "Burnup por HU",
    "burnup_sp": "Burnup por Story Points",
    "burndown_nao_prev": "Burndown Nao previstos por Tarefas",
    "burnup_nao_prev": "Burnup Nao previstos por Tarefas",
    "burndown_nao_prev_hu": "Burndown Nao previstos por HU",
    "burnup_nao_prev_hu": "Burnup Nao previstos por HU",
    "cfd": "CFD - Fluxo Cumulativo",
    "wip": "WIP por Perfil",
    "wip_bucket": "WIP por Bucket",
    "wip_profile": "WIP por Perfil",
    "hu_tasks": "Tarefas por HU",
    "areas": "Areas de Trabalho",
    "categoria": "Por Categoria",
    "colaborador": "Por Colaborador",
    "hu_inout": "Em HU vs Fora de HU",
    "dispersao": "CYCLE TIME SCATTERPLOT (data + volume da entrega)",
    "rotulos": "Lead & Cycle Time por Rotulo",
    "responsaveis": "Lead & Cycle Time por Responsavel",
    "aging": "Aging",
    "aging_tasks": "Aging por Tarefa",
    "histograma": "Histograma de Cycle Time",
}


def _serialize_user(user: User, report_count: int | None = None) -> dict:
    data = {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "session_revoked_at": user.session_revoked_at.isoformat() if user.session_revoked_at else None,
    }
    if report_count is not None:
        data["report_count"] = int(report_count)
    return data


def _serialize_report(report: Report) -> dict:
    return {
        "id": report.id,
        "title": report.title,
        "source_filename": report.source_filename,
        "project_name": report.project_name,
        "sprint_name": report.sprint_name,
        "export_date": report.export_date,
        "team_id": report.team_id,
        "team_name": report.team_name_snapshot or (report.team.name if report.team else None),
        "sprint_duration_days": report.sprint_duration_days_snapshot,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "updated_at": report.updated_at.isoformat() if report.updated_at else None,
    }


TEAM_ROLES = {"owner", "admin", "member"}
TEAM_MANAGEMENT_ROLES = {"owner", "admin"}
TEAM_MIN_SPRINT_DAYS = 1
TEAM_MAX_SPRINT_DAYS = 366


def _team_membership(team: Team, user_id: int | None = None) -> TeamMember | None:
    target_user_id = user_id or (g.user.id if g.user else None)
    if not target_user_id:
        return None
    return TeamRepository.membership(team.id, target_user_id)


def _team_can_manage(team: Team) -> bool:
    if not g.user:
        return False
    if _is_admin(g.user) or team.owner_user_id == g.user.id:
        return True
    membership = _team_membership(team)
    return bool(membership and membership.role in TEAM_MANAGEMENT_ROLES)


def _team_is_visible(team: Team) -> bool:
    if not g.user:
        return False
    if _is_admin(g.user) or team.owner_user_id == g.user.id:
        return True
    return _team_membership(team) is not None


def _serialize_team(team: Team, include_members: bool = False) -> dict:
    memberships = list(team.memberships or []) if include_members else []
    current_membership = _team_membership(team)
    data = {
        "id": team.id,
        "name": team.name,
        "project_name": team.project_name,
        "sprint_duration_days": int(team.sprint_duration_days or 15),
        "sprint_mode": team.sprint_mode or "calendar",
        "active": bool(team.active),
        "owner_user_id": team.owner_user_id,
        "owner_name": team.owner.display_name if team.owner else None,
        "member_count": len(memberships) if include_members else (
            db.session.query(func.count(TeamMember.id)).filter(TeamMember.team_id == team.id).scalar() or 0
        ),
        "current_user_role": current_membership.role if current_membership else (
            "owner" if g.user and team.owner_user_id == g.user.id else None
        ),
        "created_at": team.created_at.isoformat() if team.created_at else None,
        "updated_at": team.updated_at.isoformat() if team.updated_at else None,
    }
    if include_members:
        data["members"] = [
            {
                "id": membership.user.id,
                "display_name": membership.user.display_name,
                "email": membership.user.email,
                "role": membership.role,
                "created_at": membership.created_at.isoformat() if membership.created_at else None,
            }
            for membership in memberships
            if membership.user and membership.user.role != "disabled"
        ]
    return data


def _latest_layout_version(layout: ReportLayout) -> ReportLayoutVersion | None:
    return (
        ReportLayoutVersion.query.filter_by(layout_id=layout.id)
        .order_by(ReportLayoutVersion.version_number.desc())
        .first()
    )


def _serialize_report_layout_version(version: ReportLayoutVersion | None) -> dict | None:
    if not version:
        return None
    return {
        "id": version.id,
        "layout_id": version.layout_id,
        "version_number": int(version.version_number or 0),
        "note": version.note,
        "created_by_user_id": version.created_by_user_id,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


def _serialize_report_layout(
    layout: ReportLayout,
    latest_version: ReportLayoutVersion | None = None,
) -> dict:
    if latest_version is None:
        latest_version = _latest_layout_version(layout)
    version_count = (
        db.session.query(func.count(ReportLayoutVersion.id))
        .filter(ReportLayoutVersion.layout_id == layout.id)
        .scalar()
        or 0
    )
    return {
        "id": layout.id,
        "title": layout.title,
        "created_at": layout.created_at.isoformat() if layout.created_at else None,
        "updated_at": layout.updated_at.isoformat() if layout.updated_at else None,
        "archived_at": layout.archived_at.isoformat() if layout.archived_at else None,
        "version_count": int(version_count),
        "latest_version": _serialize_report_layout_version(latest_version),
    }


def _split_terms(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).replace("\n", ";").replace(",", ";").split(";") if part.strip()]


def _normalize_text(value) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _serialize_profile_rule(rule: ProfileRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "labels_contains": rule.labels_contains or "",
        "assignee_contains": rule.assignee_contains or "",
        "bucket_contains": rule.bucket_contains or "",
        "base_profiles": _split_terms(rule.base_profiles),
        "base_profiles_text": rule.base_profiles or "",
        "priority": int(rule.priority or 0),
        "enabled": bool(rule.enabled),
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        "created_by_user_id": rule.created_by_user_id,
    }


def _bootstrap_required() -> bool:
    return db.session.query(User.id).limit(1).first() is None


def _self_registration_allowed() -> bool:
    return False


def _is_admin(user: User | None) -> bool:
    return bool(user and user.role == "admin")


def _admin_count() -> int:
    return db.session.query(func.count(User.id)).filter(User.role == "admin").scalar() or 0


def _user_report_counts() -> dict[int, int]:
    rows = db.session.query(Report.user_id, func.count(Report.id)).group_by(Report.user_id).all()
    return {int(user_id): int(count) for user_id, count in rows}


def _user_role_allowed(role: str, *, allow_disabled: bool) -> bool:
    return role in (USER_ROLES if allow_disabled else MANAGED_ROLES)


def _login_user(user: User) -> None:
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    session["login_at"] = _now_utc().isoformat()
    session["csrf_token"] = secrets.token_urlsafe(32)
    g.clear_session_cookie = False


def _logout_user() -> None:
    session.clear()
    session.modified = True
    g.clear_session_cookie = True


def _session_cookie_domains() -> list[str | None]:
    domains: list[str | None] = [None]
    configured_domain = app.config.get("SESSION_COOKIE_DOMAIN")
    if configured_domain:
        configured_domain = str(configured_domain).lstrip(".")
        domains.append(configured_domain)
        domains.append(f".{configured_domain}")

    host = request.host.split(":", 1)[0].strip().lower()
    if host:
        domains.append(host)
        if host.startswith("www.") and len(host) > 4:
            domains.append(host[4:])

    deduped: list[str | None] = []
    for domain in domains:
        if domain not in deduped:
            deduped.append(domain)
    return deduped


def _expire_session_cookie(response):
    cookie_name = app.config["SESSION_COOKIE_NAME"]
    cookie_path = app.config.get("SESSION_COOKIE_PATH", "/")
    for domain in _session_cookie_domains():
        response.delete_cookie(cookie_name, path=cookie_path, domain=domain)
    return response


def _payload_from_request() -> dict:
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


def _record_successful_login(user: User) -> None:
    user.last_login_at = _now_utc()
    db.session.commit()


app.register_blueprint(
    create_auth_blueprint(
        AuthServices(
            bootstrap_required=_bootstrap_required,
            self_registration_allowed=_self_registration_allowed,
            payload_from_request=_payload_from_request,
            serialize_user=_serialize_user,
            login_user=_login_user,
            logout_user=_logout_user,
            record_successful_login=_record_successful_login,
        )
    )
)


app.register_blueprint(
    create_teams_blueprint(
        TeamServices(
            payload_from_request=_payload_from_request,
            serialize_team=_serialize_team,
            serialize_user=_serialize_user,
            team_is_visible=_team_is_visible,
            team_can_manage=_team_can_manage,
            is_admin=_is_admin,
        )
    )
)
app.register_blueprint(
    create_admin_users_blueprint(
        AdminUserServices(
            payload_from_request=_payload_from_request,
            serialize_user=_serialize_user,
            user_role_allowed=_user_role_allowed,
            admin_count=_admin_count,
            now_utc=_now_utc,
        )
    )
)
app.register_blueprint(
    create_admin_configuration_blueprint(
        AdminConfigurationServices(
            payload_from_request=_payload_from_request,
            serialize_chart=serialize_custom_chart,
            normalize_chart=normalize_custom_chart_payload,
            sync_chart_types=sync_custom_chart_types,
            serialize_rule=_serialize_profile_rule,
            normalize_rule=normalize_profile_rule_payload,
        )
    )
)


def _session_was_revoked(user: User) -> bool:
    revoked_at = _ensure_aware_utc(user.session_revoked_at)
    if not revoked_at:
        return False
    login_at = _parse_session_timestamp(session.get("login_at"))
    return login_at is None or login_at <= revoked_at


def _get_owned_report(report_id: int) -> Report | None:
    if not g.user:
        return None
    return ReportRepository.by_id_for_user(report_id, g.user.id)


def _get_owned_saved_roadmap(roadmap_id: int) -> SavedRoadmap | None:
    if not g.user:
        return None
    return RoadmapRepository.by_id_for_user(roadmap_id, g.user.id)


def _load_report_payload(report: Report) -> dict:
    return json.loads(report.payload_json)


def _get_owned_report_layout(layout_id: int, include_archived: bool = False) -> ReportLayout | None:
    if not g.user:
        return None
    query = ReportLayout.query.filter_by(id=layout_id, user_id=g.user.id)
    if not include_archived:
        query = query.filter(ReportLayout.archived_at.is_(None))
    return query.first()


def _load_layout_payload(version: ReportLayoutVersion | None) -> dict:
    if not version:
        return {}
    return json.loads(version.payload_json)


def _clean_report_layout_title(value, default: str = "Relatorio visual") -> str:
    title = str(value or "").strip()
    if not title:
        title = default
    return title[:160]


def _clean_report_layout_note(value) -> str | None:
    note = str(value or "").strip()
    return note[:255] if note else None


def _normalize_report_builder_payload(payload) -> tuple[dict | None, set[int], str | None]:
    if not isinstance(payload, dict):
        return None, set(), "Payload do relatorio invalido."

    pages = payload.get("pages")
    if not isinstance(pages, list) or not pages:
        return None, set(), "Adicione pelo menos uma pagina ao relatorio."
    if len(pages) > 30:
        return None, set(), "O relatorio possui paginas demais."

    normalized_pages = []
    report_ids: set[int] = set()
    block_count = 0
    for page_index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            continue
        blocks = page.get("blocks")
        if blocks is None:
            blocks = []
        if not isinstance(blocks, list):
            return None, set(), "Uma das paginas possui blocos invalidos."
        if len(blocks) > 80:
            return None, set(), "Uma das paginas possui blocos demais."

        normalized_blocks = []
        for block_index, block in enumerate(blocks, start=1):
            if not isinstance(block, dict):
                continue
            raw_report_ids = block.get("reportIds") or []
            if not isinstance(raw_report_ids, list):
                return None, set(), "Um dos blocos possui dashboards invalidos."
            clean_report_ids = []
            for raw_id in raw_report_ids[:10]:
                try:
                    report_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if report_id <= 0:
                    continue
                clean_report_ids.append(report_id)
                report_ids.add(report_id)

            normalized_blocks.append(
                {
                    "id": str(block.get("id") or f"block-{page_index}-{block_index}")[:120],
                    "chartId": str(block.get("chartId") or "")[:80],
                    "type": str(block.get("type") or "bar_v")[:40],
                    "size": str(block.get("size") or "large")[:40],
                    "reportIds": clean_report_ids,
                }
            )
            block_count += 1

        normalized_pages.append(
            {
                "id": str(page.get("id") or f"page-{page_index}")[:120],
                "name": str(page.get("name") or f"Pagina {page_index}")[:120],
                "blocks": normalized_blocks,
            }
        )

    normalized = {
        "schema": "report_builder_v1",
        "title": _clean_report_layout_title(payload.get("title")),
        "pages": normalized_pages,
    }
    report_refs = []
    if isinstance(payload.get("reportRefs"), list):
        for ref in payload.get("reportRefs")[:120]:
            if not isinstance(ref, dict):
                continue
            try:
                report_id = int(ref.get("id"))
            except (TypeError, ValueError):
                continue
            if report_id <= 0:
                continue
            report_refs.append(
                {
                    "id": report_id,
                    "title": str(ref.get("title") or "")[:160],
                    "sprint_name": str(ref.get("sprint_name") or "")[:160],
                    "project_name": str(ref.get("project_name") or "")[:160],
                    "updated_at": str(ref.get("updated_at") or "")[:64],
                }
            )
    if report_refs:
        normalized["reportRefs"] = report_refs
    encoded = json.dumps(normalized, ensure_ascii=False)
    if len(encoded) > 2_000_000:
        return None, set(), "O relatorio salvo ficou grande demais."
    if block_count > 300:
        return None, set(), "O relatorio possui blocos demais."
    return normalized, report_ids, None


def _report_layout_payload_allowed(report_ids: set[int]) -> bool:
    if not report_ids:
        return True
    owned_ids = {
        row[0]
        for row in db.session.query(Report.id)
        .filter(Report.user_id == g.user.id, Report.id.in_(report_ids))
        .all()
    }
    return report_ids.issubset(owned_ids)


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_iso_date_text(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _aging_reference_date_for_payload(data: dict):
    sprint_end = _parse_iso_date_text((data.get("meta") or {}).get("sprint_end"))
    today = datetime.now().date()
    if sprint_end and today > sprint_end:
        return sprint_end
    return today


def _task_label_values(task: dict) -> list[str]:
    unique: dict[str, str] = {}
    for raw_label in str(task.get("labels") or "").split(";"):
        label = raw_label.strip()
        key = _normalize_text(label)
        if key and key not in unique:
            unique[key] = label
    return list(unique.values())


def _build_aging_task_metric_rows(data: dict, filters: dict | None = None) -> list[dict]:
    filters = filters or {}
    selected_labels = {
        _normalize_text(value)
        for value in (filters.get("aging_task_labels") or [])
        if str(value or "").strip()
    }
    ref_date = _aging_reference_date_for_payload(data)
    rows = []

    for index, task in enumerate(data.get("task_rows") or []):
        if _parse_iso_date_text(task.get("date_done")):
            continue

        created_date = _parse_iso_date_text(task.get("date_created") or task.get("date_criacao"))
        start_date = _parse_iso_date_text(task.get("date_start"))
        base_date = created_date or start_date
        if base_date is None or base_date > ref_date:
            continue

        labels = _task_label_values(task)
        normalized_labels = {_normalize_text(label) for label in labels if _normalize_text(label)}
        if selected_labels and not (selected_labels & normalized_labels):
            continue

        aging_days = (ref_date - base_date).days
        if aging_days < 0:
            continue

        rows.append(
            {
                "label": str(task.get("title") or "").strip() or f"Tarefa {index + 1}",
                "value": aging_days,
                "age_days": aging_days,
                "labels": labels,
                "assignee": str(task.get("assignee") or "").strip() or "Sem atribuicao",
                "base_date": base_date.isoformat(),
            }
        )

    rows.sort(key=lambda row: (-_safe_int(row.get("age_days")), _normalize_text(row.get("label"))))
    return rows


def _round_number(value, digits: int = 2):
    number = _safe_float(value)
    return round(number, digits) if number is not None else None


def _top_count_rows(rows, *, limit: int = 3) -> list[dict]:
    normalized = []
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or not row:
            continue
        label = str(row[0] or "").strip()
        if not label:
            continue
        done = _safe_int(row[1] if len(row) > 1 else 0)
        pending = _safe_int(row[2] if len(row) > 2 else 0)
        total = done + pending
        normalized.append(
            {
                "label": label,
                "done": done,
                "pending": pending,
                "total": total,
            }
        )
    normalized.sort(key=lambda item: (-item["total"], -item["done"], item["label"].lower()))
    return normalized[:limit]


def _top_timing_rows(rows, *, limit: int = 3) -> list[dict]:
    normalized = []
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or not row:
            continue
        label = str(row[0] or "").strip()
        if not label:
            continue
        normalized.append(
            {
                "label": label,
                "done": _safe_int(row[1] if len(row) > 1 else 0),
                "pending": _safe_int(row[2] if len(row) > 2 else 0),
                "lead_time": _round_number(row[3] if len(row) > 3 else None),
                "cycle_time": _round_number(row[4] if len(row) > 4 else None),
            }
        )
    normalized.sort(
        key=lambda item: (
            -(item["cycle_time"] if item["cycle_time"] is not None else -1),
            -(item["lead_time"] if item["lead_time"] is not None else -1),
            item["label"].lower(),
        )
    )
    return normalized[:limit]


def _histogram_peak(hist_values) -> dict | None:
    if not hist_values:
        return None
    pairs = [(idx + 1, _safe_int(value)) for idx, value in enumerate(hist_values)]
    pairs = [(day, count) for day, count in pairs if count > 0]
    if not pairs:
        return None
    day, count = max(pairs, key=lambda item: (item[1], -item[0]))
    return {"cycle_days": day, "count": count}


def _wip_snapshot(data: dict) -> dict:
    wip = data.get("wip") or {}
    buckets = [str(bucket or "").strip() for bucket in (wip.get("buckets") or []) if str(bucket or "").strip()]
    matrix = wip.get("matrix") or {}
    snapshot = []
    total = 0
    for bucket in buckets:
        values = matrix.get(bucket) or []
        count = _safe_int(values[-1] if values else 0)
        total += count
        snapshot.append({"bucket": bucket, "count": count})
    snapshot.sort(key=lambda item: (-item["count"], item["bucket"].lower()))
    return {
        "date": (wip.get("dates") or [None])[-1],
        "items": snapshot,
        "total": total,
    }


def _format_number(value) -> str:
    if value is None:
        return "n/d"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}".replace(".", ",")
    return str(value)


def _build_summary_facts(data: dict) -> dict:
    meta = data.get("meta") or {}
    kpis = data.get("kpis") or {}
    warnings = data.get("warnings") or []
    warning_messages = []
    for item in warnings[:4]:
        if isinstance(item, dict):
            message = str(item.get("msg") or "").strip()
        else:
            message = str(item or "").strip()
        if message:
            warning_messages.append(message)

    return {
        "meta": {
            "sprint_name": meta.get("sprint_name"),
            "project_name": meta.get("projeto"),
            "export_date": meta.get("export_date"),
            "sprint_start": meta.get("sprint_start"),
            "sprint_end": meta.get("sprint_end"),
        },
        "kpis": {
            "total": _safe_int(kpis.get("total")),
            "done": _safe_int(kpis.get("done")),
            "pending": _safe_int(kpis.get("pending")),
            "backlog_total": _safe_int(kpis.get("backlog_total")),
            "sem_hu": _safe_int(kpis.get("sem_hu")),
            "storypoints": _round_number(kpis.get("storypoints")),
            "pct_entrega": _round_number((_safe_float(kpis.get("pct_entrega")) or 0) * 100),
            "ct_task": _round_number(kpis.get("ct_task")),
            "lt_task": _round_number(kpis.get("lt_task")),
            "ct_hu": _round_number(kpis.get("ct_hu")),
            "lt_hu": _round_number(kpis.get("lt_hu")),
            "ct_sp": _round_number(kpis.get("ct_sp")),
            "lt_sp": _round_number(kpis.get("lt_sp")),
            "stakeholders": _safe_int(kpis.get("stakeholders")),
            "hu_count": _safe_int(kpis.get("hu_count")),
            "sprint_days_calendar": _safe_int(kpis.get("sprint_days_calendar")),
            "sprint_days_business": _safe_int(kpis.get("sprint_days_business")),
        },
        "current_wip": _wip_snapshot(data),
        "histogram_peak": _histogram_peak(data.get("hist_31") or []),
        "top_areas": _top_count_rows(data.get("area_rows") or []),
        "top_categories": _top_count_rows(data.get("cat_rows") or []),
        "top_collaborators": _top_count_rows(data.get("collab_rows") or []),
        "top_label_timing": _top_timing_rows(data.get("rotulos_rows") or []),
        "top_owner_timing": _top_timing_rows(data.get("resp_rows") or []),
        "warnings": warning_messages,
    }


def _heuristic_summary_from_facts(facts: dict) -> str:
    meta = facts.get("meta") or {}
    kpis = facts.get("kpis") or {}
    current_wip = facts.get("current_wip") or {}
    peak = facts.get("histogram_peak")
    warning_messages = facts.get("warnings") or []

    title_bits = [str(meta.get("sprint_name") or "Sprint").strip()]
    project_name = str(meta.get("project_name") or "").strip()
    if project_name:
        title_bits.append(f"do projeto {project_name}")

    lines = [
        f"Resumo gerencial de {' '.join(bit for bit in title_bits if bit)}.",
        (
            f"- Panorama: {kpis.get('done', 0)} de {kpis.get('total', 0)} tarefas concluídas "
            f"({ _format_number(kpis.get('pct_entrega')) }%), com {kpis.get('pending', 0)} pendentes "
            f"e {kpis.get('backlog_total', 0)} itens marcados como backlog."
        ),
    ]

    if kpis.get("storypoints"):
        lines.append(
            f"- Escopo: { _format_number(kpis.get('storypoints')) } story points mapeados, "
            f"{kpis.get('hu_count', 0)} HU(s) e {kpis.get('stakeholders', 0)} responsáveis diferentes no recorte."
        )

    wip_items = current_wip.get("items") or []
    if wip_items:
        top_wip = ", ".join(
            f"{item['bucket']} ({item['count']})" for item in wip_items[:3] if item.get("count", 0) > 0
        )
        if top_wip:
            lines.append(
                f"- Fluxo atual ({current_wip.get('date') or 'último snapshot'}): maior acúmulo em {top_wip}."
            )

    ct_task = kpis.get("ct_task")
    lt_task = kpis.get("lt_task")
    if ct_task is not None or lt_task is not None:
        parts = []
        if ct_task is not None:
            parts.append(f"cycle time médio de { _format_number(ct_task) } dia(s)")
        if lt_task is not None:
            parts.append(f"lead time médio de { _format_number(lt_task) } dia(s)")
        lines.append(f"- Eficiência: tarefas concluídas com {' e '.join(parts)}.")

    top_areas = facts.get("top_areas") or []
    if top_areas:
        top_area = top_areas[0]
        lines.append(
            f"- Distribuição: a área com maior volume foi {top_area['label']} com {top_area['total']} tarefa(s)."
        )

    top_owner_timing = facts.get("top_owner_timing") or []
    if top_owner_timing and top_owner_timing[0].get("cycle_time") is not None:
        owner = top_owner_timing[0]
        lines.append(
            f"- Atenção: {owner['label']} aparece com o maior cycle time médio entre os responsáveis "
            f"({ _format_number(owner['cycle_time']) } dia(s))."
        )

    if peak:
        lines.append(
            f"- Histograma: o pico de frequência ocorreu em {peak['cycle_days']} dia(s) de cycle time, com {peak['count']} tarefa(s)."
        )

    if kpis.get("sem_hu", 0) > 0:
        lines.append(
            f"- Qualidade do dado: {kpis.get('sem_hu', 0)} tarefa(s) estão fora de HU e podem distorcer leituras por escopo."
        )

    if warning_messages:
        lines.append(f"- Alertas: {warning_messages[0]}")

    return "\n".join(lines[:7])


def _percentage(part, total):
    total_value = _safe_float(total)
    part_value = _safe_float(part)
    if total_value in (None, 0) or part_value is None:
        return None
    return round((part_value / total_value) * 100, 1)


def _latest_series_value(values) -> int:
    if not values:
        return 0
    return _safe_int(values[-1])


def _count_leading_static(values) -> int:
    if not values:
        return 0
    start = values[0]
    count = 0
    for value in values[1:]:
        if value == start:
            count += 1
            continue
        break
    return count


def _largest_drop(values, dates) -> dict | None:
    if not values or len(values) < 2:
        return None
    best = None
    for index in range(1, len(values)):
        previous = _safe_float(values[index - 1])
        current = _safe_float(values[index])
        if previous is None or current is None:
            continue
        drop = round(previous - current, 2)
        if drop <= 0:
            continue
        candidate = {
            "drop": drop,
            "date": dates[index] if index < len(dates) else None,
        }
        if best is None or candidate["drop"] > best["drop"]:
            best = candidate
    return best


def _first_date_at_or_below(values, dates, threshold=0) -> str | None:
    for index, value in enumerate(values or []):
        numeric = _safe_float(value)
        if numeric is not None and numeric <= threshold:
            return dates[index] if index < len(dates) else None
    return None


def _ordered_enabled_profile_rules() -> list[ProfileRule]:
    rules = db.session.query(ProfileRule).filter(ProfileRule.enabled.is_(True)).all()
    return sorted(
        rules,
        key=lambda rule: (
            int(rule.priority or 100),
            _normalize_text(rule.name),
        ),
    )


def _resolved_base_profile(task: dict) -> str:
    raw = str(task.get("profile_base_display") or task.get("profile_base") or "").strip()
    return raw or "Outros"


def _text_matches_terms(value, terms: list[str]) -> bool:
    haystack = _normalize_text(value)
    if not terms:
        return True
    return any(term for term in (_normalize_text(term) for term in terms) if term and term in haystack)


def _profile_rule_matches(task: dict, rule: ProfileRule) -> bool:
    base_profiles = [_normalize_text(part) for part in _split_terms(rule.base_profiles)]
    label_terms = _split_terms(rule.labels_contains)
    assignee_terms = _split_terms(rule.assignee_contains)
    bucket_terms = _split_terms(rule.bucket_contains)
    criteria_count = 0

    if base_profiles:
        criteria_count += 1
        task_profile = _normalize_text(task.get("profile_base") or task.get("profile_base_display"))
        if task_profile not in base_profiles:
            return False
    if label_terms:
        criteria_count += 1
        if not _text_matches_terms(task.get("labels"), label_terms):
            return False
    if assignee_terms:
        criteria_count += 1
        if not _text_matches_terms(task.get("assignee"), assignee_terms):
            return False
    if bucket_terms:
        criteria_count += 1
        if not _text_matches_terms(task.get("bucket"), bucket_terms):
            return False

    return criteria_count > 0


def _task_profile_name(task: dict, profile_rules: list[ProfileRule]) -> str:
    for rule in profile_rules:
        if _profile_rule_matches(task, rule):
            return str(rule.name or "").strip() or _resolved_base_profile(task)
    return _resolved_base_profile(task)


def _build_wip_profile_series(data: dict, selected_profile: str = "Todos") -> dict | None:
    tasks = data.get("task_rows") or []
    dates = (data.get("wip") or {}).get("dates") or []
    if not tasks or not dates:
        return None

    cutoff = ((data.get("meta") or {}).get("export_date") or dates[-1]) if dates else None
    profile_rules = _ordered_enabled_profile_rules()
    scoped_tasks = []
    for task in tasks:
        profile_name = _task_profile_name(task, profile_rules)
        if selected_profile not in ("", "Todos") and profile_name != selected_profile:
            continue
        scoped_tasks.append({"task": task, "profile_name": profile_name})

    if not scoped_tasks:
        return None

    backlog_series = []
    doing_series = []
    done_series = []
    peak_doing = {"count": 0, "date": None}

    for date_value in dates:
        if cutoff and str(date_value) > str(cutoff):
            backlog_series.append(backlog_series[-1] if backlog_series else 0)
            doing_series.append(doing_series[-1] if doing_series else 0)
            done_series.append(done_series[-1] if done_series else 0)
            continue

        counts = {"backlog": 0, "doing": 0, "done": 0}
        for item in scoped_tasks:
            task = item["task"]
            done_date = task.get("wip_done_date") or task.get("date_done") or task.get("date_due")
            start_date = task.get("date_start")
            if done_date and done_date <= date_value:
                counts["done"] += 1
                continue
            if start_date and start_date <= date_value and (not done_date or date_value < done_date):
                counts["doing"] += 1
                continue
            if task.get("is_backlog") and (not start_date or start_date > date_value) and (
                not done_date or date_value < done_date
            ):
                counts["backlog"] += 1

        backlog_series.append(counts["backlog"])
        doing_series.append(counts["doing"])
        done_series.append(counts["done"])
        if counts["doing"] >= peak_doing["count"]:
            peak_doing = {"count": counts["doing"], "date": date_value}

    return {
        "dates": dates,
        "selected_profile": selected_profile or "Todos",
        "backlog_series": backlog_series,
        "doing_series": doing_series,
        "done_series": done_series,
        "latest": {
            "date": dates[-1],
            "backlog": _latest_series_value(backlog_series),
            "doing": _latest_series_value(doing_series),
            "done": _latest_series_value(done_series),
        },
        "peak_doing": peak_doing,
        "task_count": len(scoped_tasks),
    }


def _sort_metric_rows(rows: list[dict], sort_mode: str = "metric_desc", limit: int | None = None) -> list[dict]:
    normalized = list(rows)
    if sort_mode == "metric_asc":
        normalized.sort(key=lambda item: (item.get("value", 0), _normalize_text(item.get("label"))))
    elif sort_mode == "label_asc":
        normalized.sort(key=lambda item: _normalize_text(item.get("label")))
    elif sort_mode == "label_desc":
        normalized.sort(key=lambda item: _normalize_text(item.get("label")), reverse=True)
    else:
        normalized.sort(key=lambda item: (-(_safe_float(item.get("value")) or 0), _normalize_text(item.get("label"))))

    if limit and limit > 0:
        normalized = normalized[:limit]
    return normalized


def _extract_metric_rows(
    data: dict,
    source_key: str,
    metric_key: str,
    *,
    sort_mode: str = "metric_desc",
    limit: int | None = None,
    filters: dict | None = None,
) -> list[dict]:
    rows = []
    if source_key == "hu_tasks":
        for row in data.get("hu_list") or []:
            done = _safe_int(row[1] if len(row) > 1 else 0)
            pending = _safe_int(row[2] if len(row) > 2 else 0)
            label = (data.get("hu_full_names") or {}).get(row[0], row[0])
            value = done if metric_key == "done" else pending if metric_key == "pending" else done + pending
            rows.append({"label": str(label), "value": value, "done": done, "pending": pending})
    elif source_key in {"areas", "categoria", "colaborador"}:
        source_rows = {
            "areas": data.get("area_rows") or [],
            "categoria": data.get("cat_rows") or [],
            "colaborador": data.get("collab_rows") or [],
        }[source_key]
        for row in source_rows:
            done = _safe_int(row[1] if len(row) > 1 else 0)
            pending = _safe_int(row[2] if len(row) > 2 else 0)
            value = done if metric_key == "done" else pending if metric_key == "pending" else done + pending
            rows.append({"label": str(row[0]), "value": value, "done": done, "pending": pending})
    elif source_key == "hu_inout":
        for row in data.get("in_out") or []:
            rows.append({"label": str(row[0]), "value": _safe_int(row[1] if len(row) > 1 else 0)})
    elif source_key in {"rotulos", "responsaveis"}:
        source_rows = (data.get("rotulos_rows") or []) if source_key == "rotulos" else (data.get("resp_rows") or [])
        for row in source_rows:
            done = _safe_int(row[1] if len(row) > 1 else 0)
            pending = _safe_int(row[2] if len(row) > 2 else 0)
            lead_time = _round_number(row[3] if len(row) > 3 else None)
            cycle_time = _round_number(row[4] if len(row) > 4 else None)
            if metric_key == "done":
                value = done
            elif metric_key == "pending":
                value = pending
            elif metric_key == "lead_time":
                value = _safe_float(lead_time) or 0
            else:
                value = _safe_float(cycle_time) or 0
            rows.append(
                {
                    "label": str(row[0]),
                    "value": value,
                    "done": done,
                    "pending": pending,
                    "lead_time": lead_time,
                    "cycle_time": cycle_time,
                }
            )
    elif source_key == "histograma":
        for index, value in enumerate(data.get("hist_31") or []):
            rows.append({"label": f"{index + 1} dia(s)", "value": _safe_int(value), "cycle_days": index + 1})
    elif source_key == "aging_tasks":
        rows.extend(_build_aging_task_metric_rows(data, filters))

    if source_key != "histograma":
        rows = [row for row in rows if _safe_float(row.get("value")) not in (None, 0)]

    rows = _sort_metric_rows(rows, sort_mode=sort_mode, limit=limit)
    if source_key == "histograma" and sort_mode.startswith("label"):
        rows.sort(key=lambda row: int(row.get("cycle_days") or 0))
    return rows


def _build_group_distribution_facts(rows: list, general_facts: dict, scope: dict) -> dict:
    normalized = []
    for row in rows or []:
        done = _safe_int(row[1] if len(row) > 1 else 0)
        pending = _safe_int(row[2] if len(row) > 2 else 0)
        normalized.append(
            {
                "label": str(row[0]),
                "done": done,
                "pending": pending,
                "total": done + pending,
            }
        )
    normalized = [row for row in normalized if row["total"] > 0]
    if not normalized:
        return {"kind": "grouped", "groups": 0}
    normalized.sort(key=lambda item: (-item["total"], _normalize_text(item["label"])))
    top_pending = max(normalized, key=lambda item: (item["pending"], item["total"], item["label"]))
    total_visible = sum(row["total"] for row in normalized)
    return {
        "kind": "grouped",
        "scope_label": scope["label"],
        "groups": len(normalized),
        "top": normalized[0],
        "top_pending": top_pending,
        "visible_total": total_visible,
        "visible_share_of_total": _percentage(total_visible, (general_facts.get("kpis") or {}).get("total")),
    }


def _build_generic_metric_facts(rows: list[dict], general_facts: dict, scope: dict) -> dict:
    visible_total = round(sum(_safe_float(row.get("value")) or 0 for row in rows), 2)
    top = rows[0] if rows else None
    return {
        "kind": "metric_rows",
        "scope_label": scope["label"],
        "metric_key": scope.get("metric_key"),
        "groups": len(rows),
        "top": top,
        "visible_total": visible_total,
        "visible_share_of_general": _percentage(visible_total, (general_facts.get("kpis") or {}).get("total")),
    }


def _build_timing_facts(rows: list, general_facts: dict, scope: dict) -> dict:
    normalized = _top_timing_rows(rows or [], limit=50)
    if not normalized:
        return {"kind": "timing", "groups": 0}
    worst_cycle = max(
        [row for row in normalized if row.get("cycle_time") is not None],
        key=lambda item: item["cycle_time"],
        default=None,
    )
    worst_lead = max(
        [row for row in normalized if row.get("lead_time") is not None],
        key=lambda item: item["lead_time"],
        default=None,
    )
    return {
        "kind": "timing",
        "scope_label": scope["label"],
        "groups": len(normalized),
        "worst_cycle": worst_cycle,
        "worst_lead": worst_lead,
        "overall_cycle": (general_facts.get("kpis") or {}).get("ct_task"),
        "overall_lead": (general_facts.get("kpis") or {}).get("lt_task"),
    }


def _build_histogram_facts(data: dict, general_facts: dict, scope: dict) -> dict:
    hist_values = data.get("hist_31") or []
    total_tasks = sum(_safe_int(value) for value in hist_values)
    weighted = None
    if total_tasks > 0:
        weighted = _round_number(
            sum((index + 1) * _safe_int(value) for index, value in enumerate(hist_values)) / total_tasks
        )
    return {
        "kind": "histograma",
        "scope_label": scope["label"],
        "peak": _histogram_peak(hist_values),
        "weighted_average": weighted,
        "task_count": total_tasks,
        "overall_cycle": (general_facts.get("kpis") or {}).get("ct_task"),
    }


def _build_inout_facts(data: dict, general_facts: dict, scope: dict) -> dict:
    inside = 0
    outside = 0
    for row in data.get("in_out") or []:
        label = _normalize_text(row[0] if len(row) > 0 else "")
        count = _safe_int(row[1] if len(row) > 1 else 0)
        if "fora" in label:
            outside += count
        else:
            inside += count
    total = inside + outside
    return {
        "kind": "hu_inout",
        "scope_label": scope["label"],
        "inside": inside,
        "outside": outside,
        "total": total,
        "outside_share": _percentage(outside, total),
        "overall_outside": (general_facts.get("kpis") or {}).get("sem_hu"),
    }


def _build_cfd_facts(data: dict, general_facts: dict, scope: dict) -> dict:
    cfd = data.get("cfd") or {}
    dates = cfd.get("dates") or []
    todo = cfd.get("todo") or []
    doing = cfd.get("doing") or []
    done = cfd.get("done") or []
    max_doing = max((_safe_int(value) for value in doing), default=0)
    peak_index = next((index for index, value in enumerate(doing) if _safe_int(value) == max_doing), None)
    total_latest = _latest_series_value(todo) + _latest_series_value(doing) + _latest_series_value(done)
    return {
        "kind": "cfd",
        "scope_label": scope["label"],
        "latest": {
            "date": dates[-1] if dates else None,
            "todo": _latest_series_value(todo),
            "doing": _latest_series_value(doing),
            "done": _latest_series_value(done),
            "total": total_latest,
        },
        "peak_doing": {
            "count": max_doing,
            "date": dates[peak_index] if peak_index is not None and peak_index < len(dates) else None,
        },
        "overall_done": (general_facts.get("kpis") or {}).get("done"),
    }


def _build_burndown_facts(data: dict, source_key: str, general_facts: dict, scope: dict) -> dict:
    if source_key == "burndown_sp":
        source = data.get("burndown_sp") or {}
        rows = [row for row in (source.get("rows") or []) if row[0] is not None]
        dates = [row[0] for row in rows]
        meta_values = [_safe_float(row[1]) or 0 for row in rows]
        actual_values = [_safe_float(row[2]) or 0 for row in rows]
        plan_values = []
        unit_label = "SP"
    else:
        source = data.get(source_key) or {}
        rows = [row for row in (source.get("rows") or []) if row[0] is not None]
        dates = [row[0] for row in rows]
        meta_values = [_safe_float(row[1]) or 0 for row in rows]
        plan_values = [_safe_float(row[2]) or 0 for row in rows]
        actual_values = [_safe_float(row[3]) or 0 for row in rows]
        unit_label = "HU" if source_key == "burndown_hu" else "tarefas"
    if not actual_values:
        return {"kind": "burndown", "scope_label": scope["label"], "unit_label": unit_label}
    return {
        "kind": "burndown",
        "scope_label": scope["label"],
        "unit_label": unit_label,
        "start_remaining": _round_number(actual_values[0]),
        "end_remaining": _round_number(actual_values[-1]),
        "meta_end": _round_number(meta_values[-1] if meta_values else None),
        "plan_end": _round_number(plan_values[-1] if plan_values else None),
        "zero_date": _first_date_at_or_below(actual_values, dates),
        "flatline_days": _count_leading_static(actual_values),
        "largest_drop": _largest_drop(actual_values, dates),
        "gap_vs_plan_end": _round_number((actual_values[-1] - plan_values[-1]) if plan_values else None),
        "overall_pending": (general_facts.get("kpis") or {}).get("pending"),
        "overall_delivery_pct": (general_facts.get("kpis") or {}).get("pct_entrega"),
    }


def _build_wip_facts(data: dict, general_facts: dict, scope: dict, filters: dict) -> dict:
    source_key = scope.get("source_key")
    selected_profile = str((filters or {}).get("profile") or "Todos").strip() or "Todos"
    if source_key == "wip_profile":
        series = _build_wip_profile_series(data, selected_profile=selected_profile)
        if not series:
            return {"kind": "wip_profile", "scope_label": scope["label"], "selected_profile": selected_profile}
        return {
            "kind": "wip_profile",
            "scope_label": scope["label"],
            "selected_profile": selected_profile,
            "latest": series["latest"],
            "peak_doing": series["peak_doing"],
            "task_count": series["task_count"],
            "overall_done": (general_facts.get("kpis") or {}).get("done"),
            "overall_backlog": (general_facts.get("kpis") or {}).get("backlog_total"),
            "overall_pending": (general_facts.get("kpis") or {}).get("pending"),
        }

    snapshot = _wip_snapshot(data)
    items = {row["bucket"]: row["count"] for row in snapshot.get("items") or []}
    return {
        "kind": "wip_bucket",
        "scope_label": scope["label"],
        "latest": {
            "date": snapshot.get("date"),
            "backlog": _safe_int(items.get("Backlog")),
            "doing": _safe_int(items.get("Em produção") or items.get("Em producao") or items.get("Doing")),
            "done": _safe_int(items.get("Concluído") or items.get("Concluido") or items.get("Done")),
        },
        "overall_done": (general_facts.get("kpis") or {}).get("done"),
        "overall_backlog": (general_facts.get("kpis") or {}).get("backlog_total"),
        "overall_pending": (general_facts.get("kpis") or {}).get("pending"),
    }


def _summary_task_hu(task: dict) -> str:
    task = task or {}
    for field in ("title", "hu", "labels"):
        value = str(task.get(field) or "")
        match = re.search(r"\bHU\s*0*\d+\b", value, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", "", match.group(0)).upper()
    return ""


def _summary_task_storypoint_weights(tasks: list[dict], hu_storypoints: dict) -> list[float]:
    counts: dict[str, int] = {}
    for task in tasks:
        hu = _summary_task_hu(task)
        if hu:
            counts[hu] = counts.get(hu, 0) + 1
    weights = []
    for task in tasks:
        hu = _summary_task_hu(task)
        sp = _safe_float((hu_storypoints or {}).get(hu)) or 0
        count = counts.get(hu, 0)
        weights.append((sp / count) if hu and sp > 0 and count > 0 else 0)
    return weights


def _build_person_delivery_facts(data: dict, general_facts: dict, scope: dict, filters: dict) -> dict:
    tasks = data.get("task_rows") or []
    raw_people = (filters or {}).get("delivery_people")
    has_people_filter = isinstance(raw_people, list)
    selected_people = [
        str(value or "").strip()
        for value in (raw_people or [])
        if str(value or "").strip()
    ] if has_people_filter else []
    selected_person = str((filters or {}).get("delivery_person") or "").strip()
    selected_people_set = set(selected_people)
    hu_storypoints = (data.get("burndown_sp") or {}).get("hu_sp") or {}
    weights = _summary_task_storypoint_weights(tasks, hu_storypoints)
    rows: dict[str, dict] = {}

    for idx, task in enumerate(tasks):
        done_date = str(task.get("date_done") or task.get("wip_done_date") or "").strip()
        if not done_date:
            continue
        person = str(task.get("assignee") or "").strip() or "Sem atribuição"
        if has_people_filter and person not in selected_people_set:
            continue
        if not has_people_filter and selected_person and selected_person != "Todos" and person != selected_person:
            continue
        current = rows.setdefault(done_date[:10], {"date": done_date[:10], "tasks": 0, "sp": 0.0})
        current["tasks"] += 1
        current["sp"] += float(weights[idx] or 0)

    ordered = sorted(rows.values(), key=lambda row: row["date"])
    total_tasks = sum(int(row["tasks"]) for row in ordered)
    total_sp = sum(float(row["sp"]) for row in ordered)
    peak_tasks = max(ordered, key=lambda row: (row["tasks"], row["sp"]), default=None)
    peak_sp = max(ordered, key=lambda row: (row["sp"], row["tasks"]), default=None)
    if has_people_filter:
        selected_label = (
            ", ".join(selected_people[:3]) + ("..." if len(selected_people) > 3 else "")
            if selected_people else "Nenhuma pessoa selecionada"
        )
    else:
        selected_label = selected_person or "Todos"
    return {
        "kind": "person_delivery",
        "scope_label": scope["label"],
        "selected_person": selected_label,
        "selected_people": selected_people,
        "day_count": len(ordered),
        "total_tasks": total_tasks,
        "total_sp": _round_number(total_sp),
        "peak_tasks": {
            "date": peak_tasks.get("date"),
            "tasks": peak_tasks.get("tasks"),
        } if peak_tasks else None,
        "peak_sp": {
            "date": peak_sp.get("date"),
            "sp": _round_number(peak_sp.get("sp")),
        } if peak_sp else None,
        "overall_storypoints": (general_facts.get("kpis") or {}).get("storypoints"),
    }


def _build_dispersao_facts(data: dict, general_facts: dict, scope: dict) -> dict:
    disp = data.get("dispersao") or {}
    cts = data.get("cts") or {}

    days = []
    hu_rows = []
    outside_daily = []

    cts_dates = cts.get("dates") or []
    cts_labels = cts.get("hu_labels") or []
    cts_matrix = cts.get("matrix") or []
    cts_has_data = bool(cts_dates) and (
        any(any(_safe_int(v) > 0 for v in row) for row in cts_matrix if isinstance(row, list))
        or any(_safe_int(v) > 0 for v in (cts.get("fora_hu") or []))
    )
    if cts_has_data:
        days = [str(value) for value in cts_dates]
        outside_daily = list(cts.get("fora_hu") or [])
        for idx, label in enumerate(cts_labels):
            values = cts_matrix[idx] if idx < len(cts_matrix) and isinstance(cts_matrix[idx], list) else []
            hu_rows.append({"label": str(label), "values": values})
    else:
        raw_days = disp.get("days")
        if isinstance(raw_days, list):
            days = [str(value) for value in raw_days]
        else:
            day_count = _safe_int(raw_days)
            if day_count > 0:
                start_raw = disp.get("bd_start")
                start_date = None
                if start_raw:
                    try:
                        start_date = datetime.strptime(str(start_raw), "%Y-%m-%d").date()
                    except ValueError:
                        start_date = None
                if start_date is not None:
                    days = [
                        (start_date + timedelta(days=offset)).strftime("%Y-%m-%d")
                        for offset in range(day_count)
                    ]
                else:
                    days = [str(offset + 1) for offset in range(day_count)]

        hu_matrix = disp.get("hu_matrix") or {}
        for idx, hu_name in enumerate(disp.get("hu_list") or []):
            if isinstance(hu_matrix, list):
                values = hu_matrix[idx] if idx < len(hu_matrix) and isinstance(hu_matrix[idx], list) else []
            else:
                values = hu_matrix.get(hu_name) or []
            hu_rows.append(
                {
                    "label": str((data.get("hu_full_names") or {}).get(hu_name, hu_name)),
                    "values": values,
                }
            )
        outside_daily = list(disp.get("nao_hu_daily") or [])

    day_len = max(
        len(days),
        len(outside_daily),
        max((len(row.get("values") or []) for row in hu_rows), default=0),
    )
    if day_len and len(days) < day_len:
        days.extend(str(index + 1) for index in range(len(days), day_len))

    total_by_day = [0] * day_len
    top_hu = None
    for row in hu_rows:
        values = row.get("values") or []
        hu_total = sum(_safe_int(value) for value in values)
        if top_hu is None or hu_total > top_hu["count"]:
            top_hu = {
                "label": row.get("label"),
                "count": hu_total,
            }
        for index, value in enumerate(values):
            if index < len(total_by_day):
                total_by_day[index] += _safe_int(value)
    for index, value in enumerate(outside_daily):
        if index < len(total_by_day):
            total_by_day[index] += _safe_int(value)
    peak_index = max(range(len(total_by_day)), key=lambda idx: total_by_day[idx], default=None)
    total_events = sum(total_by_day)
    return {
        "kind": "dispersao",
        "scope_label": scope["label"],
        "total_events": total_events,
        "peak_day": {
            "date": days[peak_index] if peak_index is not None and peak_index < len(days) else None,
            "count": total_by_day[peak_index] if peak_index is not None and peak_index < len(total_by_day) else 0,
        },
        "top_hu": top_hu,
        "overall_done": (general_facts.get("kpis") or {}).get("done"),
    }


def _resolve_summary_scope(chart_id: str | None, data: dict) -> dict:
    raw_chart_id = str(chart_id or "").strip()
    if not raw_chart_id or raw_chart_id == "kpis":
        return {
            "kind": "general",
            "chart_id": "kpis",
            "label": SUMMARY_SCOPE_LABELS["kpis"],
            "source_key": "kpis",
            "metric_key": None,
            "custom": False,
        }

    if raw_chart_id.startswith("custom_"):
        custom_id = str(raw_chart_id).split("_", 1)[-1]
        chart = db.session.get(CustomChart, int(custom_id)) if custom_id.isdigit() else None
        if chart:
            return {
                "kind": "section",
                "chart_id": raw_chart_id,
                "label": chart.name,
                "subtitle": chart.subtitle,
                "source_key": chart.source_key,
                "metric_key": chart.metric_key,
                "sort_mode": chart.sort_mode,
                "limit": chart.limit,
                "custom": True,
            }

    burnup_source_map = {
        "burnup": "burndown",
        "burnup_hu": "burndown_hu",
        "burnup_sp": "burndown_sp",
        "burnup_nao_prev": "burndown_nao_prev",
        "burnup_nao_prev_hu": "burndown_nao_prev_hu",
    }
    source_key = burnup_source_map.get(raw_chart_id, raw_chart_id)
    label = SUMMARY_SCOPE_LABELS.get(raw_chart_id, raw_chart_id)
    if raw_chart_id == "wip" and not (data.get("task_rows") or []):
        source_key = "wip_bucket"
        label = SUMMARY_SCOPE_LABELS["wip_bucket"]
    elif raw_chart_id == "wip":
        source_key = "wip_profile"
    return {
        "kind": "section",
        "chart_id": raw_chart_id,
        "label": label,
        "source_key": source_key,
        "metric_key": None,
        "custom": False,
    }


def _build_section_summary_facts(data: dict, scope: dict, filters: dict | None = None) -> dict:
    filters = filters or {}
    general_facts = _build_summary_facts(data)
    source_key = scope.get("source_key")

    if source_key in {"burndown", "burndown_hu", "burndown_sp", "burndown_nao_prev", "burndown_nao_prev_hu"}:
        section = _build_burndown_facts(data, source_key, general_facts, scope)
    elif source_key == "cfd":
        section = _build_cfd_facts(data, general_facts, scope)
    elif source_key in {"wip_profile", "wip_bucket"}:
        section = _build_wip_facts(data, general_facts, scope, filters)
    elif source_key == "delivery_person":
        section = _build_person_delivery_facts(data, general_facts, scope, filters)
    elif source_key in {"areas", "categoria", "colaborador"}:
        rows = {
            "areas": data.get("area_rows") or [],
            "categoria": data.get("cat_rows") or [],
            "colaborador": data.get("collab_rows") or [],
        }[source_key]
        section = _build_group_distribution_facts(rows, general_facts, scope)
    elif source_key == "hu_tasks":
        mapped_rows = [
            [
                (data.get("hu_full_names") or {}).get(row[0], row[0]),
                row[1] if len(row) > 1 else 0,
                row[2] if len(row) > 2 else 0,
            ]
            for row in (data.get("hu_list") or [])
        ]
        section = _build_group_distribution_facts(mapped_rows, general_facts, scope)
    elif source_key in {"rotulos", "responsaveis"} and not scope.get("custom"):
        rows = (data.get("rotulos_rows") or []) if source_key == "rotulos" else (data.get("resp_rows") or [])
        section = _build_timing_facts(rows, general_facts, scope)
    elif source_key == "hu_inout":
        section = _build_inout_facts(data, general_facts, scope)
    elif source_key == "histograma":
        section = _build_histogram_facts(data, general_facts, scope)
    elif source_key == "dispersao":
        section = _build_dispersao_facts(data, general_facts, scope)
    else:
        metric_key = scope.get("metric_key") or "total"
        rows = _extract_metric_rows(
            data,
            source_key,
            metric_key,
            sort_mode=str(scope.get("sort_mode") or "metric_desc"),
            limit=_safe_int(scope.get("limit")) or None,
            filters=filters,
        )
        section = _build_generic_metric_facts(rows, general_facts, scope)

    return {
        "scope": {
            **scope,
            "filters": filters,
        },
        "general": general_facts,
        "section": section,
    }


def _heuristic_section_summary_from_facts(facts: dict) -> str:
    scope = facts.get("scope") or {}
    general = facts.get("general") or {}
    section = facts.get("section") or {}
    kpis = general.get("kpis") or {}
    kind = section.get("kind")
    label = scope.get("label") or "Secao"
    lines = [f"Resumo da secao {label} comparado ao panorama geral da sprint."]

    if kind == "burndown":
        lines.append(
            f"- Curva atual: saiu de {_format_number(section.get('start_remaining'))} e fechou com {_format_number(section.get('end_remaining'))} {section.get('unit_label') or 'itens'} em aberto."
        )
        if section.get("zero_date"):
            lines.append(
                f"- Entrega: o grafico zerou em {section['zero_date']}, coerente com o panorama geral de {_format_number(kpis.get('pct_entrega'))}% entregue."
            )
        elif section.get("end_remaining") not in (None, 0):
            lines.append(
                f"- Pendencia: a secao ainda terminou com {_format_number(section.get('end_remaining'))} {section.get('unit_label') or 'itens'}, enquanto o resumo geral aponta {kpis.get('pending', 0)} tarefa(s) pendentes."
            )
        if section.get("flatline_days", 0) > 0:
            lines.append(f"- Ritmo: houve {section['flatline_days']} dia(s) iniciais sem reducao relevante na curva.")
        if section.get("largest_drop"):
            lines.append(
                f"- Maior queima: {section['largest_drop']['drop']} {section.get('unit_label') or 'itens'} em {section['largest_drop'].get('date') or 'um unico dia'}."
            )
        gap_vs_plan = section.get("gap_vs_plan_end")
        if gap_vs_plan is not None:
            if gap_vs_plan > 0:
                lines.append(
                    f"- Planejamento: o fechamento ficou {gap_vs_plan} {section.get('unit_label') or 'itens'} acima do planejado."
                )
            elif gap_vs_plan < 0:
                lines.append(
                    f"- Planejamento: o fechamento ficou {abs(gap_vs_plan)} {section.get('unit_label') or 'itens'} abaixo do planejado."
                )
    elif kind == "cfd":
        latest = section.get("latest") or {}
        lines.append(
            f"- Snapshot final ({latest.get('date') or 'ultimo dia'}): {latest.get('done', 0)} concluidas, {latest.get('doing', 0)} em progresso e {latest.get('todo', 0)} a fazer."
        )
        if latest.get("total"):
            lines.append(
                f"- Comparacao geral: a faixa concluida representa {_format_number(_percentage(latest.get('done'), latest.get('total')))}% do fluxo observado, contra {_format_number(kpis.get('pct_entrega'))}% de entrega no resumo geral."
            )
        if section.get("peak_doing", {}).get("count"):
            lines.append(
                f"- Gargalo de fluxo: o pico de itens simultaneos em progresso foi {section['peak_doing']['count']} em {section['peak_doing'].get('date') or 'um dia do periodo'}."
            )
    elif kind in {"wip_profile", "wip_bucket"}:
        latest = section.get("latest") or {}
        prefix = (
            f" para o perfil {section.get('selected_profile')}"
            if section.get("selected_profile") not in (None, "", "Todos")
            else ""
        )
        lines.append(
            f"- Snapshot{prefix}: backlog {latest.get('backlog', 0)}, em producao {latest.get('doing', 0)} e concluido {latest.get('done', 0)}."
        )
        if section.get("selected_profile") not in (None, "", "Todos") and section.get("task_count") is not None:
            lines.append(
                f"- Recorte filtrado: {section['task_count']} tarefa(s) entram nesse perfil, contra {kpis.get('total', 0)} no panorama geral."
            )
        if section.get("peak_doing", {}).get("count"):
            lines.append(
                f"- Pico de WIP: {section['peak_doing']['count']} item(ns) em producao em {section['peak_doing'].get('date') or 'um dia do periodo'}."
            )
        lines.append(
            f"- Comparacao geral: o resumo geral indica {kpis.get('backlog_total', 0)} itens em backlog e {kpis.get('pending', 0)} pendentes no total da sprint."
        )
    elif kind == "person_delivery":
        person = section.get("selected_person") or "Todos"
        prefix = "" if person == "Todos" else (
            " com nenhuma pessoa selecionada"
            if person == "Nenhuma pessoa selecionada"
            else f" de {person}"
        )
        lines.append(
            f"- Entrega{prefix}: {section.get('total_tasks', 0)} tarefa(s) concluida(s), equivalentes a {_format_number(section.get('total_sp'))} SP pelo fatiamento das HUs."
        )
        lines.append(
            f"- Distribuicao diaria: houve entrega em {section.get('day_count', 0)} dia(s) do periodo analisado."
        )
        if section.get("peak_tasks"):
            lines.append(
                f"- Pico em tarefas: {section['peak_tasks'].get('tasks', 0)} tarefa(s) em {section['peak_tasks'].get('date') or 'um dia do periodo'}."
            )
        if section.get("peak_sp"):
            lines.append(
                f"- Pico em SP: {_format_number(section['peak_sp'].get('sp'))} SP em {section['peak_sp'].get('date') or 'um dia do periodo'}."
            )
    elif kind == "grouped":
        top = section.get("top") or {}
        if top:
            lines.append(
                f"- Maior concentracao: {top.get('label')} lidera com {top.get('total', 0)} tarefa(s), sendo {top.get('done', 0)} concluidas e {top.get('pending', 0)} pendentes."
            )
            lines.append(
                f"- Comparacao geral: isso representa {_format_number(_percentage(top.get('total'), kpis.get('total')))}% do volume total de {kpis.get('total', 0)} tarefas."
            )
        if section.get("top_pending", {}).get("pending"):
            pending_row = section["top_pending"]
            lines.append(
                f"- Atencao local: {pending_row.get('label')} concentra o maior saldo pendente da secao ({pending_row.get('pending', 0)})."
            )
        lines.append(
            f"- Cobertura: a secao distribui {section.get('visible_total', 0)} tarefa(s) em {section.get('groups', 0)} agrupamento(s)."
        )
    elif kind == "timing":
        if section.get("worst_cycle"):
            lines.append(
                f"- Maior cycle time: {section['worst_cycle']['label']} aparece com {_format_number(section['worst_cycle']['cycle_time'])} dia(s), contra media geral de {_format_number(section.get('overall_cycle'))}."
            )
        if section.get("worst_lead"):
            lines.append(
                f"- Maior lead time: {section['worst_lead']['label']} chega a {_format_number(section['worst_lead']['lead_time'])} dia(s), frente a {_format_number(section.get('overall_lead'))} no geral."
            )
        lines.append(f"- Cobertura: a secao expoe {section.get('groups', 0)} linha(s) comparativas de timing.")
    elif kind == "hu_inout":
        lines.append(
            f"- Cobertura por HU: {section.get('inside', 0)} tarefa(s) estao dentro de HU e {section.get('outside', 0)} fora de HU."
        )
        lines.append(
            f"- Comparacao geral: o saldo fora de HU equivale a {_format_number(section.get('outside_share'))}% deste recorte e conversa com {kpis.get('sem_hu', 0)} item(ns) sem HU no resumo geral."
        )
    elif kind == "histograma":
        peak = section.get("peak") or {}
        if peak:
            lines.append(
                f"- Pico de frequencia: {peak.get('count', 0)} tarefa(s) concentradas em {peak.get('cycle_days', 0)} dia(s) de cycle time."
            )
        if section.get("weighted_average") is not None:
            lines.append(
                f"- Comparacao geral: a media ponderada do histograma fica em {_format_number(section.get('weighted_average'))} dia(s), contra cycle time medio geral de {_format_number(section.get('overall_cycle'))}."
            )
        lines.append(
            f"- Cobertura: o histograma consolida {section.get('task_count', 0)} tarefa(s) com cycle time conhecido."
        )
    elif kind == "dispersao":
        if section.get("peak_day", {}).get("date"):
            lines.append(
                f"- Pico diario: {section['peak_day']['count']} conclusoes em {section['peak_day']['date']}."
            )
        if section.get("top_hu"):
            lines.append(
                f"- HU mais frequente: {section['top_hu']['label']} concentrou {section['top_hu']['count']} entrega(s) no periodo."
            )
        lines.append(
            f"- Comparacao geral: a secao registra {section.get('total_events', 0)} marcacoes diarias para um total de {kpis.get('done', 0)} itens concluidos no panorama geral."
        )
    elif kind == "metric_rows":
        top = section.get("top") or {}
        metric_key = section.get("metric_key") or "valor"
        if top:
            lines.append(
                f"- Destaque do recorte: {top.get('label')} lidera com {_format_number(top.get('value'))} em {metric_key}."
            )
        lines.append(
            f"- Cobertura: a configuracao atual mostra {section.get('groups', 0)} grupo(s) somando {_format_number(section.get('visible_total'))} unidades visiveis."
        )
        if metric_key == "done":
            reference = kpis.get("done")
        elif metric_key == "pending":
            reference = kpis.get("pending")
        elif metric_key == "total":
            reference = kpis.get("total")
        elif metric_key == "lead_time":
            reference = kpis.get("lt_task")
        elif metric_key == "cycle_time":
            reference = kpis.get("ct_task")
        else:
            reference = None
        if reference not in (None, 0):
            lines.append(
                f"- Comparacao geral: o total visivel desta secao representa {_format_number(_percentage(section.get('visible_total'), reference))}% da referencia geral usada para {metric_key}."
            )
    else:
        lines.append(
            f"- Comparacao geral: o dashboard segue com {kpis.get('done', 0)} concluidas, {kpis.get('pending', 0)} pendentes e {kpis.get('backlog_total', 0)} em backlog."
        )

    warning_messages = general.get("warnings") or []
    if warning_messages:
        lines.append(f"- Alerta geral: {warning_messages[0]}")
    return "\n".join(lines[:6])


def _generate_report_summary(data: dict, chart_id: str | None = None, filters: dict | None = None) -> dict:
    scope = _resolve_summary_scope(chart_id, data)
    if scope.get("kind") == "section":
        facts = _build_section_summary_facts(data, scope, filters=filters)
        heuristic_summary = _heuristic_section_summary_from_facts(facts)
    else:
        facts = _build_summary_facts(data)
        heuristic_summary = _heuristic_summary_from_facts(facts)

    provider = str(app.config.get("AI_SUMMARY_PROVIDER") or "heuristic").strip().lower()
    if provider == "ollama":
        try:
            summary, model_name = generate_ollama_summary(
                facts,
                model=str(app.config["AI_SUMMARY_MODEL"]),
                url=str(app.config["AI_SUMMARY_OLLAMA_URL"]),
                timeout=float(app.config["AI_SUMMARY_TIMEOUT"]),
            )
            return {
                "summary": summary,
                "provider": "ollama",
                "model": model_name,
                "generated_at": _now_utc().isoformat(),
                "facts": facts,
                "scope": scope,
            }
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError, OSError) as exc:
            return {
                "summary": heuristic_summary,
                "provider": "heuristic_fallback",
                "model": app.config["AI_SUMMARY_MODEL"],
                "generated_at": _now_utc().isoformat(),
                "facts": facts,
                "scope": scope,
                "warning": f"Falha ao consultar Ollama: {exc}",
            }

    return {
        "summary": heuristic_summary,
        "provider": "heuristic",
        "model": None,
        "generated_at": _now_utc().isoformat(),
        "facts": facts,
        "scope": scope,
    }


app.register_blueprint(
    create_layouts_blueprint(
        LayoutServices(
            owned_layout=_get_owned_report_layout,
            serialize_layout=_serialize_report_layout,
            serialize_version=_serialize_report_layout_version,
            latest_version=_latest_layout_version,
            load_payload=_load_layout_payload,
            clean_title=_clean_report_layout_title,
            clean_note=_clean_report_layout_note,
            normalize_payload=_normalize_report_builder_payload,
            payload_allowed=_report_layout_payload_allowed,
            now_utc=_now_utc,
        )
    )
)
app.register_blueprint(
    create_reports_blueprint(
        ReportServices(
            serialize_report=_serialize_report,
            owned_report=_get_owned_report,
            load_payload=_load_report_payload,
            payload_from_request=_payload_from_request,
            team_is_visible=_team_is_visible,
            generate_summary=_generate_report_summary,
        )
    )
)
@app.before_request
def load_current_user():
    g.clear_session_cookie = False
    user_id = session.get("user_id")
    g.user = db.session.get(User, user_id) if user_id else None
    if g.user and (g.user.role == "disabled" or _session_was_revoked(g.user)):
        session.clear()
        session.modified = True
        g.clear_session_cookie = True
        g.user = None


@app.after_request
def add_security_headers(response):
    if getattr(g, "clear_session_cookie", False):
        _expire_session_cookie(response)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers[
        "Content-Security-Policy"
    ] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.plot.ly; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    if APP_ENV == "production" and request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.register_blueprint(
    create_planner_blueprint(
        PlannerServices(
            serialize_roadmap=serialize_saved_roadmap,
            owned_roadmap=_get_owned_saved_roadmap,
            parse_saved_items=parse_saved_roadmap_items,
            parse_manual_items=parse_upload_roadmap_items,
            save_roadmap=save_uploaded_roadmap,
            compute_json=compute_json,
            serialize_report=_serialize_report,
            team_is_visible=_team_is_visible,
        )
    )
)


initialize_database(app)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"\n  ReportChart Web -> http://{host}:{port}\n")
    app.run(host=host, port=port, debug=False)
