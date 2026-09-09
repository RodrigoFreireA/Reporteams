"""Saved roadmap normalization and persistence helpers."""

from __future__ import annotations

import json
import re

from flask import g

from reportchart_web.extensions import db
from reportchart_web.models import SavedRoadmap
from reportchart_web.repositories import RoadmapRepository


def normalize_roadmap_date(value) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if match:
        return raw
    match = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", raw)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    return raw[:10]


def roadmap_date_label(value) -> str | None:
    raw = str(value or "").strip()
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if match:
        return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"
    return raw or None


def _extract_item_date(item) -> str | None:
    if isinstance(item, (list, tuple)) and item:
        text = str(item[0] or "")
    elif isinstance(item, dict):
        text = str(item.get("marco") or "")
    else:
        text = ""
    first = text.splitlines()[0].strip() if text.strip() else ""
    match = re.match(r"^(\d{2}/\d{2}/\d{4})", first)
    return match.group(1) if match else None


def _infer_project_date(items: list[list[object]]) -> str | None:
    for item in items:
        date = _extract_item_date(item)
        if date:
            return normalize_roadmap_date(date)
    return None


infer_project_date = _infer_project_date


def serialize_saved_roadmap(roadmap: SavedRoadmap, include_items: bool = True) -> dict:
    try:
        items = json.loads(roadmap.items_json)
    except (TypeError, json.JSONDecodeError):
        items = []
    data = {
        "id": roadmap.id,
        "title": roadmap.title,
        "project_date": roadmap.project_date,
        "project_date_label": roadmap_date_label(roadmap.project_date),
        "item_count": len(items) if isinstance(items, list) else 0,
        "source_filename": roadmap.source_filename,
        "created_at": roadmap.created_at.isoformat() if roadmap.created_at else None,
        "updated_at": roadmap.updated_at.isoformat() if roadmap.updated_at else None,
    }
    if include_items:
        data["items"] = items if isinstance(items, list) else []
    return data


def parse_saved_roadmap_items(roadmap: SavedRoadmap) -> list[list[object]]:
    try:
        payload = json.loads(roadmap.items_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Roadmap salvo invalido.") from exc
    if not isinstance(payload, list):
        raise ValueError("Roadmap salvo invalido.")

    items: list[list[object]] = []
    for item in payload[:100]:
        if not isinstance(item, (list, tuple)) or not item:
            continue
        marco = str(item[0] or "").strip()
        if not marco:
            continue
        try:
            posicao = float(str(item[1] if len(item) > 1 else 0).replace(",", "."))
        except (TypeError, ValueError):
            posicao = 0.0
        items.append([marco[:2400], posicao])
    return items


def clean_roadmap_title(value, *, fallback: str) -> str:
    title = re.sub(r"\s+", " ", str(value or "").strip())
    return (title or fallback)[:160]


def save_uploaded_roadmap(
    *,
    items: list[list[object]],
    title: str | None,
    project_date: str | None,
    source_filename: str | None,
    project_name: str | None,
) -> SavedRoadmap | None:
    if not items:
        return None

    normalized_date = normalize_roadmap_date(project_date) or _infer_project_date(items)
    date_label = roadmap_date_label(normalized_date)
    fallback_title = project_name or (f"Roadmap {date_label}" if date_label else "Roadmap")
    clean_title = clean_roadmap_title(title, fallback=fallback_title)
    items_json = json.dumps(items, ensure_ascii=False)
    roadmap = RoadmapRepository.duplicate_for_user(g.user.id, normalized_date, items_json)
    if roadmap:
        roadmap.title = clean_title
        roadmap.source_filename = (source_filename or roadmap.source_filename or "")[:255] or None
        return roadmap

    roadmap = SavedRoadmap(
        user_id=g.user.id,
        title=clean_title,
        project_date=normalized_date,
        items_json=items_json,
        source_filename=(source_filename or "")[:255] or None,
    )
    db.session.add(roadmap)
    return roadmap


def parse_upload_roadmap_items(raw: str | None) -> list[list[object]]:
    if not raw or not str(raw).strip():
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Roadmap manual invalido.") from exc
    if not isinstance(payload, list):
        raise ValueError("Roadmap manual deve ser uma lista de marcos.")

    items: list[list[object]] = []
    for item in payload[:100]:
        if not isinstance(item, dict):
            continue
        marco = str(item.get("marco") or "").strip()
        if not marco:
            continue
        try:
            posicao = float(str(item.get("posicao", "0")).replace(",", "."))
        except (TypeError, ValueError):
            posicao = 0.0
        items.append([marco[:2400], posicao])
    return items
