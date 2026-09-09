"""Persistence gateways used by application and HTTP orchestration code."""

from __future__ import annotations

from .extensions import db
from .models import CustomChart, ProfileRule, Report, SavedRoadmap, Team, TeamMember, User


class UserRepository:
    """Queries and writes related to application users."""

    @staticmethod
    def by_id(user_id: int) -> User | None:
        return db.session.get(User, user_id)

    @staticmethod
    def by_email(email: str) -> User | None:
        return User.query.filter_by(email=email).first()

    @staticmethod
    def all_active() -> list[User]:
        return User.query.filter(User.role != "disabled").order_by(
            User.display_name.asc(), User.email.asc()
        ).all()

    @staticmethod
    def all() -> list[User]:
        return User.query.order_by(User.created_at.asc(), User.id.asc()).all()


class TeamRepository:
    """Queries for teams and their memberships."""

    @staticmethod
    def by_id(team_id: int) -> Team | None:
        return db.session.get(Team, team_id)

    @staticmethod
    def all() -> list[Team]:
        return Team.query.order_by(Team.active.desc(), Team.name.asc(), Team.id.asc()).all()

    @staticmethod
    def membership(team_id: int, user_id: int) -> TeamMember | None:
        return TeamMember.query.filter_by(team_id=team_id, user_id=user_id).first()

    @staticmethod
    def can_manage_any(user_id: int, management_roles: set[str]) -> bool:
        return (
            TeamMember.query.filter(
                TeamMember.user_id == user_id,
                TeamMember.role.in_(management_roles),
            ).first()
            is not None
        )


class ReportRepository:
    """Queries for reports scoped to their owner."""

    @staticmethod
    def by_id_for_user(report_id: int, user_id: int) -> Report | None:
        return Report.query.filter_by(id=report_id, user_id=user_id).first()

    @staticmethod
    def all_for_user(user_id: int) -> list[Report]:
        return Report.query.filter_by(user_id=user_id).order_by(Report.updated_at.desc()).all()

    @staticmethod
    def delete_all_for_user(user_id: int) -> int:
        return Report.query.filter_by(user_id=user_id).delete(synchronize_session=False)


class RoadmapRepository:
    """Queries for saved Planner roadmaps scoped to their owner."""

    @staticmethod
    def by_id_for_user(roadmap_id: int, user_id: int) -> SavedRoadmap | None:
        return SavedRoadmap.query.filter_by(id=roadmap_id, user_id=user_id).first()

    @staticmethod
    def all_for_user(user_id: int) -> list[SavedRoadmap]:
        return SavedRoadmap.query.filter_by(user_id=user_id).order_by(
            SavedRoadmap.project_date.desc(), SavedRoadmap.updated_at.desc()
        ).all()

    @staticmethod
    def duplicate_for_user(user_id: int, project_date: str | None, items_json: str) -> SavedRoadmap | None:
        return SavedRoadmap.query.filter_by(
            user_id=user_id,
            project_date=project_date,
            items_json=items_json,
        ).first()


class CustomChartRepository:
    """Queries for custom chart definitions."""

    @staticmethod
    def enabled() -> list[CustomChart]:
        return CustomChart.query.filter_by(enabled=True).order_by(
            CustomChart.group_name.asc(), CustomChart.sort_order.asc(), CustomChart.name.asc()
        ).all()

    @staticmethod
    def all() -> list[CustomChart]:
        return CustomChart.query.order_by(
            CustomChart.enabled.desc(), CustomChart.group_name.asc(),
            CustomChart.sort_order.asc(), CustomChart.name.asc()
        ).all()

    @staticmethod
    def by_id(chart_id: int) -> CustomChart | None:
        return db.session.get(CustomChart, chart_id)


class ProfileRuleRepository:
    """Queries for configurable task profile rules."""

    @staticmethod
    def enabled() -> list[ProfileRule]:
        return ProfileRule.query.filter_by(enabled=True).order_by(
            ProfileRule.priority.asc(), ProfileRule.name.asc()
        ).all()

    @staticmethod
    def all() -> list[ProfileRule]:
        return ProfileRule.query.order_by(
            ProfileRule.enabled.desc(), ProfileRule.priority.asc(), ProfileRule.name.asc()
        ).all()

    @staticmethod
    def by_id(rule_id: int) -> ProfileRule | None:
        return db.session.get(ProfileRule, rule_id)
