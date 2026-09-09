"""Retention operations for persisted Planner-derived data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from .extensions import db
from .models import Report, SavedRoadmap


def purge_expired_planner_data(
    retention_days: int,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Delete reports and saved roadmaps older than the retention window."""
    if retention_days <= 0:
        raise ValueError("retention_days precisa ser maior que zero")

    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(days=retention_days)
    deleted_reports = db.session.execute(
        delete(Report).where(Report.updated_at < cutoff)
    ).rowcount or 0
    deleted_roadmaps = db.session.execute(
        delete(SavedRoadmap).where(SavedRoadmap.updated_at < cutoff)
    ).rowcount or 0
    db.session.commit()
    return {
        "deleted_reports": int(deleted_reports),
        "deleted_roadmaps": int(deleted_roadmaps),
        "cutoff": cutoff.isoformat(),
    }
