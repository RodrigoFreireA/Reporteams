"""SQLAlchemy persistence models for users, teams and dashboard artifacts."""

from __future__ import annotations

from datetime import datetime, timezone

from .extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(320), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(512), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)
    session_revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)


class Team(db.Model):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    project_name = db.Column(db.String(160), nullable=True)
    sprint_duration_days = db.Column(db.Integer, nullable=False, default=15)
    sprint_mode = db.Column(db.String(20), nullable=False, default="calendar")
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    owner = db.relationship("User", foreign_keys=[owner_user_id])


class TeamMember(db.Model):
    __tablename__ = "team_members"
    __table_args__ = (db.UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),)

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default="member")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    team = db.relationship("Team", backref=db.backref("memberships", lazy=True, cascade="all, delete-orphan"))
    user = db.relationship("User")


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    source_filename = db.Column(db.String(255), nullable=False)
    project_name = db.Column(db.String(160), nullable=True)
    sprint_name = db.Column(db.String(160), nullable=True)
    export_date = db.Column(db.String(32), nullable=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=True, index=True)
    team_name_snapshot = db.Column(db.String(120), nullable=True)
    sprint_duration_days_snapshot = db.Column(db.Integer, nullable=True)
    payload_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", backref=db.backref("reports", lazy=True))
    team = db.relationship("Team", backref=db.backref("reports", lazy=True))


class SavedRoadmap(db.Model):
    __tablename__ = "saved_roadmaps"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    project_date = db.Column(db.String(10), nullable=True, index=True)
    items_json = db.Column(db.Text, nullable=False)
    source_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", backref=db.backref("saved_roadmaps", lazy=True))


class ReportLayout(db.Model):
    __tablename__ = "report_layouts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    archived_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", backref=db.backref("report_layouts", lazy=True, cascade="all, delete-orphan"))
    versions = db.relationship(
        "ReportLayoutVersion", back_populates="layout", cascade="all, delete-orphan",
        order_by="ReportLayoutVersion.version_number.desc()",
    )


class ReportLayoutVersion(db.Model):
    __tablename__ = "report_layout_versions"
    __table_args__ = (db.UniqueConstraint("layout_id", "version_number", name="uq_report_layout_versions_number"),)

    id = db.Column(db.Integer, primary_key=True)
    layout_id = db.Column(db.Integer, db.ForeignKey("report_layouts.id"), nullable=False, index=True)
    version_number = db.Column(db.Integer, nullable=False)
    payload_json = db.Column(db.Text, nullable=False)
    note = db.Column(db.String(255), nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    layout = db.relationship("ReportLayout", back_populates="versions")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])


class CustomChart(db.Model):
    __tablename__ = "custom_charts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    group_name = db.Column(db.String(40), nullable=False, default="Distribuição")
    subtitle = db.Column(db.String(255), nullable=True)
    source_key = db.Column(db.String(40), nullable=False)
    metric_key = db.Column(db.String(40), nullable=False)
    chart_type = db.Column(db.String(20), nullable=False, default="bar_v")
    sort_mode = db.Column(db.String(20), nullable=False, default="metric_desc")
    limit = db.Column(db.Integer, nullable=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    created_by = db.relationship("User", foreign_keys=[created_by_user_id])


class CustomChartTypeOption(db.Model):
    __tablename__ = "custom_chart_type_options"
    __table_args__ = (db.UniqueConstraint("chart_id", "chart_type", name="uq_custom_chart_type_options_chart_type"),)

    id = db.Column(db.Integer, primary_key=True)
    chart_id = db.Column(db.Integer, db.ForeignKey("custom_charts.id"), nullable=False, index=True)
    chart_type = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    chart = db.relationship("CustomChart", backref=db.backref("type_options", lazy="selectin", cascade="all, delete-orphan"))


class ProfileRule(db.Model):
    __tablename__ = "profile_rules"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    labels_contains = db.Column(db.String(500), nullable=True)
    assignee_contains = db.Column(db.String(500), nullable=True)
    bucket_contains = db.Column(db.String(500), nullable=True)
    base_profiles = db.Column(db.String(500), nullable=True)
    priority = db.Column(db.Integer, nullable=False, default=100)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
