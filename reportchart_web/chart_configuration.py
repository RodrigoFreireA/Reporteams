"""Validation and serialization rules for custom dashboard charts."""

from __future__ import annotations

from reportchart_web.extensions import db
from reportchart_web.models import CustomChart, CustomChartTypeOption


CUSTOM_CHART_GROUPS = ("Resumo", "Andamento", "Distribuição", "Tempo")
CUSTOM_CHART_SORTS = {"metric_desc", "metric_asc", "label_asc", "label_desc"}
CHART_TYPE_ORDER = ("cards", "bar_v", "bar_h", "line", "area", "pie", "donut", "scatter")
CUSTOM_CHART_SOURCES = {
    "hu_tasks": {"types": {"bar_v", "bar_h", "pie", "donut"}, "metrics": {"done", "pending", "total"}, "icon": "📋"},
    "areas": {"types": {"bar_v", "bar_h", "pie", "donut"}, "metrics": {"done", "pending", "total"}, "icon": "👥"},
    "categoria": {"types": {"bar_v", "bar_h", "pie", "donut"}, "metrics": {"done", "pending", "total"}, "icon": "🏷️"},
    "colaborador": {"types": {"bar_v", "bar_h", "pie", "donut"}, "metrics": {"done", "pending", "total"}, "icon": "👤"},
    "hu_inout": {"types": {"bar_v", "pie", "donut"}, "metrics": {"count"}, "icon": "🔵"},
    "rotulos": {"types": {"bar_v", "bar_h"}, "metrics": {"done", "pending", "lead_time", "cycle_time"}, "icon": "⏱"},
    "responsaveis": {"types": {"bar_v", "bar_h"}, "metrics": {"done", "pending", "lead_time", "cycle_time"}, "icon": "⏱"},
    "aging_tasks": {"types": {"bar_h"}, "metrics": {"count"}, "icon": "🧾"},
    "histograma": {"types": {"bar_v", "line"}, "metrics": {"count"}, "icon": "📊"},
    "wip_profile": {"types": {"bar_v", "line", "area"}, "metrics": {"state_mix"}, "icon": "🧭"},
}


def _parse_optional_int(value, *, field: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"O campo {field} deve ser um numero inteiro.")


def _parse_optional_bool(value, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_optional_text(value, *, max_len: int) -> str | None:
    text = str(value or "").strip()
    return text[:max_len] or None


def _order_chart_types(source_meta: dict, values) -> list[str]:
    selected = {str(value or "").strip() for value in (values or []) if str(value or "").strip()}
    return [chart_type for chart_type in CHART_TYPE_ORDER if chart_type in source_meta.get("types", set()) and chart_type in selected]


def available_types_for_chart(chart: CustomChart | None) -> list[str]:
    if not chart:
        return []
    source_meta = CUSTOM_CHART_SOURCES.get(chart.source_key, {})
    option_types = [option.chart_type for option in getattr(chart, "type_options", [])]
    ordered = _order_chart_types(source_meta, option_types)
    if ordered:
        return ordered
    fallback = str(chart.chart_type or "").strip()
    return [fallback] if fallback and fallback in source_meta.get("types", set()) else []


def normalize_custom_chart_payload(payload: dict, current: CustomChart | None = None) -> dict:
    source_key = (payload.get("source_key") if "source_key" in payload else getattr(current, "source_key", "")) or ""
    source_key = str(source_key).strip()
    if source_key not in CUSTOM_CHART_SOURCES:
        raise ValueError("Fonte de dados do grafico customizado invalida.")
    source_meta = CUSTOM_CHART_SOURCES[source_key]

    name = str((payload.get("name") if "name" in payload else getattr(current, "name", "")) or "").strip()
    if not name:
        raise ValueError("Informe um nome para o grafico.")
    group_name = str((payload.get("group") if "group" in payload else getattr(current, "group_name", CUSTOM_CHART_GROUPS[2])) or "").strip() or CUSTOM_CHART_GROUPS[2]
    if group_name not in CUSTOM_CHART_GROUPS:
        raise ValueError("Categoria do menu invalida para o grafico.")
    subtitle = str((payload.get("subtitle") if "subtitle" in payload else getattr(current, "subtitle", None)) or "").strip()[:255] or None
    metric_key = str((payload.get("metric_key") if "metric_key" in payload else getattr(current, "metric_key", "")) or "").strip()
    if metric_key not in source_meta["metrics"]:
        raise ValueError("Metrica invalida para a fonte de dados selecionada.")

    current_types = available_types_for_chart(current)
    raw_chart_types = payload.get("chart_types") if "chart_types" in payload else current_types
    if isinstance(raw_chart_types, (str, bytes)):
        raw_chart_types = [raw_chart_types]
    available_types = _order_chart_types(source_meta, raw_chart_types)
    if "chart_types" in payload and not available_types:
        raise ValueError("Selecione ao menos um tipo de grafico disponivel.")
    if not available_types:
        fallback_type = payload.get("chart_type") if "chart_type" in payload else getattr(current, "chart_type", None)
        available_types = _order_chart_types(source_meta, [fallback_type]) or _order_chart_types(source_meta, source_meta.get("types", set()))[:1]
    if not available_types:
        raise ValueError("Selecione ao menos um tipo de grafico disponivel.")

    chart_type = str((payload.get("chart_type") if "chart_type" in payload else getattr(current, "chart_type", available_types[0])) or available_types[0]).strip()
    if chart_type not in source_meta["types"] or chart_type not in available_types:
        raise ValueError("Tipo inicial invalido para a fonte de dados selecionada.")
    sort_mode = str((payload.get("sort_mode") if "sort_mode" in payload else getattr(current, "sort_mode", "metric_desc")) or "metric_desc").strip()
    if sort_mode not in CUSTOM_CHART_SORTS:
        raise ValueError("Ordenacao invalida para o grafico.")
    limit = _parse_optional_int(payload.get("limit") if "limit" in payload else getattr(current, "limit", None), field="limit")
    if limit is not None and not 1 <= limit <= 50:
        raise ValueError("O limite deve ficar entre 1 e 50.")
    sort_order = int(_parse_optional_int(payload.get("sort_order") if "sort_order" in payload else getattr(current, "sort_order", 0), field="sort_order") or 0)
    if not 0 <= sort_order <= 9999:
        raise ValueError("A ordem de exibicao deve ficar entre 0 e 9999.")
    enabled = _parse_optional_bool(payload.get("enabled") if "enabled" in payload else getattr(current, "enabled", True), default=True)
    return {
        "name": name[:160], "group_name": group_name, "subtitle": subtitle,
        "source_key": source_key, "metric_key": metric_key, "chart_type": chart_type,
        "available_types": available_types, "sort_mode": sort_mode, "limit": limit,
        "enabled": enabled, "sort_order": sort_order,
    }


def normalize_profile_rule_payload(payload: dict, current=None) -> dict:
    name = str((payload.get("name") if "name" in payload else getattr(current, "name", "")) or "").strip()
    if not name:
        raise ValueError("Informe o nome do perfil customizado.")
    values = {}
    for key in ("labels_contains", "assignee_contains", "bucket_contains"):
        values[key] = _normalize_optional_text(payload.get(key) if key in payload else getattr(current, key, None), max_len=500)
    values["base_profiles"] = _normalize_optional_text(
        payload.get("base_profiles_text") if "base_profiles_text" in payload else payload.get("base_profiles") if "base_profiles" in payload else getattr(current, "base_profiles", None),
        max_len=500,
    )
    if not any(values.values()):
        raise ValueError("Defina ao menos um criterio para o perfil customizado.")
    priority = int(_parse_optional_int(payload.get("priority") if "priority" in payload else getattr(current, "priority", 100), field="priority") or 0)
    if not 0 <= priority <= 9999:
        raise ValueError("A prioridade deve ficar entre 0 e 9999.")
    return {"name": name[:80], **values, "priority": priority, "enabled": _parse_optional_bool(payload.get("enabled") if "enabled" in payload else getattr(current, "enabled", True), default=True)}


def sync_custom_chart_types(chart: CustomChart, available_types: list[str]) -> None:
    desired = list(dict.fromkeys(available_types))
    existing = {option.chart_type: option for option in list(getattr(chart, "type_options", []))}
    for chart_type, option in existing.items():
        if chart_type not in desired:
            db.session.delete(option)
    for chart_type in desired:
        if chart_type not in existing:
            db.session.add(CustomChartTypeOption(chart=chart, chart_type=chart_type))


def serialize_custom_chart(chart: CustomChart) -> dict:
    source_meta = CUSTOM_CHART_SOURCES.get(chart.source_key, {})
    return {
        "id": chart.id, "chart_id": f"custom_{chart.id}", "name": chart.name,
        "group": chart.group_name, "subtitle": chart.subtitle, "source_key": chart.source_key,
        "metric_key": chart.metric_key, "chart_type": chart.chart_type,
        "available_types": available_types_for_chart(chart), "sort_mode": chart.sort_mode,
        "limit": chart.limit, "enabled": bool(chart.enabled), "sort_order": int(chart.sort_order or 0),
        "icon": source_meta.get("icon") or "✨",
        "created_at": chart.created_at.isoformat() if chart.created_at else None,
        "updated_at": chart.updated_at.isoformat() if chart.updated_at else None,
        "created_by_user_id": chart.created_by_user_id,
    }
