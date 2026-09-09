import os
import tempfile
import unittest
import json


_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = "sqlite:///" + _db_path.replace("\\", "/")
os.environ["APP_ENV"] = "testing"
os.environ["APP_SECRET_KEY"] = "test-secret-key"

import app as app_module  # noqa: E402


class SecurityFlowTests(unittest.TestCase):
    def setUp(self):
        self.app = app_module.app
        self.client = self.app.test_client()
        with self.app.app_context():
            app_module.db.drop_all()
            app_module.db.create_all()
        app_module.LOGIN_FAILURES.clear()

    def bootstrap_admin(self, email="admin@example.com", password="SenhaSegura47"):
        response = self.client.post(
            "/api/bootstrap",
            json={
                "email": email,
                "password": password,
                "display_name": "Admin Root",
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        return response.get_json()

    def create_user_as_admin(
        self,
        admin_auth,
        *,
        email="user@example.com",
        password="SenhaSegura47",
        display_name="User One",
        role="user",
    ):
        response = self.client.post(
            "/api/admin/users",
            json={
                "email": email,
                "password": password,
                "display_name": display_name,
                "role": role,
            },
            headers={"X-CSRF-Token": admin_auth["csrf_token"]},
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.get_json()["user"]

    def login_client(self, client, *, email="user@example.com", password="SenhaSegura47"):
        response = client.post(
            "/api/login",
            json={
                "email": email,
                "password": password,
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        return response.get_json()

    def create_report(self, *, user_id: int, title: str = "Sprint X"):
        payload = {
            "meta": {
                "sprint_name": "Sprint X",
                "projeto": "Projeto Y",
                "export_date": "2026-04-03",
                "sprint_start": "2026-04-01",
                "sprint_end": "2026-04-15",
            },
            "kpis": {
                "total": 10,
                "done": 8,
                "pending": 2,
                "backlog_total": 3,
                "sem_hu": 4,
                "storypoints": 21,
                "pct_entrega": 0.8,
                "ct_task": 4.5,
                "lt_task": 6.0,
                "ct_hu": 5.0,
                "lt_hu": 6.5,
                "stakeholders": 3,
            },
            "wip": {
                "dates": ["2026-04-03"],
                "buckets": ["Backlog", "Em produção", "Concluído"],
                "matrix": {
                    "Backlog": [3],
                    "Em produção": [2],
                    "Concluído": [8],
                },
            },
            "hist_31": [0, 1, 4, 0, 0],
            "area_rows": [["UX", 3, 1], ["DEV", 5, 1]],
            "cat_rows": [["Backend", 4, 1], ["Frontend", 2, 1]],
            "collab_rows": [["Alice", 4, 1], ["Bob", 3, 1]],
            "rotulos_rows": [["Backend", 4, 1, 5.2, 4.8]],
            "resp_rows": [["Alice", 4, 1, 5.9, 5.1], ["Bob", 3, 1, 4.0, 3.0]],
            "task_rows": [
                {
                    "title": "Arquitetura API",
                    "labels": ".ARQUITETURA;Backend",
                    "assignee": "Alice",
                    "date_created": "2026-03-20",
                    "date_start": "2026-04-02",
                    "date_done": None,
                },
                {
                    "title": "UX fluxo",
                    "labels": ".UX;Frontend",
                    "assignee": "Bob",
                    "date_created": "2026-03-25",
                    "date_start": "2026-04-03",
                    "date_done": None,
                },
                {
                    "title": "Bug concluido",
                    "labels": ".DEV;Backend",
                    "assignee": "Alice",
                    "date_created": "2026-04-01",
                    "date_start": "2026-04-01",
                    "date_done": "2026-04-04",
                },
            ],
            "warnings": [{"nivel": "aviso", "msg": "40% das tarefas estao fora de HU."}],
        }
        with self.app.app_context():
            report = app_module.Report(
                user_id=user_id,
                title=title,
                source_filename="teste.xlsx",
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
            app_module.db.session.add(report)
            app_module.db.session.commit()
            return report.id

    def create_saved_roadmap(self, *, user_id: int, title: str = "Roadmap CX"):
        items = [
            ["01/12/2024\nGoal: (dez/24)\nMarco: Inicio do Projeto", 10],
            ["15/01/2025\nGoal: (jan/25)\nMarco: Kickoff", -10],
        ]
        with self.app.app_context():
            roadmap = app_module.SavedRoadmap(
                user_id=user_id,
                title=title,
                project_date="2024-12-01",
                items_json=json.dumps(items, ensure_ascii=False),
                source_filename="roadmap.xlsx",
            )
            app_module.db.session.add(roadmap)
            app_module.db.session.commit()
            return roadmap.id

    def test_security_headers_present(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("default-src 'self'", response.headers.get("Content-Security-Policy", ""))
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(
            response.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin"
        )

    def test_sensitive_project_files_are_not_served(self):
        for path in ("/.env", "/.env.dokploy.example", "/instance/reportchart.db", "/docs/analise-projeto.md"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, path)

    def test_saved_roadmaps_are_listed_by_owner(self):
        admin = self.bootstrap_admin()
        roadmap_id = self.create_saved_roadmap(user_id=admin["user"]["id"])

        response = self.client.get("/api/roadmaps")
        self.assertEqual(response.status_code, 200, response.data)
        body = response.get_json()
        self.assertEqual(len(body["roadmaps"]), 1)
        self.assertEqual(body["roadmaps"][0]["id"], roadmap_id)
        self.assertEqual(body["roadmaps"][0]["project_date_label"], "01/12/2024")
        self.assertEqual(body["roadmaps"][0]["item_count"], 2)

        self.create_user_as_admin(
            admin,
            email="user2@example.com",
            display_name="User Two",
        )
        other = self.app.test_client()
        self.login_client(other, email="user2@example.com")

        response = other.get("/api/roadmaps")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.get_json()["roadmaps"], [])

        response = other.get(f"/api/roadmaps/{roadmap_id}")
        self.assertEqual(response.status_code, 404, response.data)

    def test_logout_requires_csrf(self):
        self.bootstrap_admin()
        response = self.client.post("/api/logout", json={})
        self.assertEqual(response.status_code, 403, response.data)

    def test_logout_clears_session_and_expires_cookie(self):
        auth = self.bootstrap_admin()
        response = self.client.post(
            "/api/logout",
            json={},
            headers={"X-CSRF-Token": auth["csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(
            any("reportchart_session=" in cookie for cookie in response.headers.getlist("Set-Cookie"))
        )
        response = self.client.get("/api/me")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.get_json()["authenticated"])

    def test_planner_rules_page_requires_authenticated_session(self):
        response = self.client.get("/regras-planner")
        self.assertEqual(response.status_code, 302, response.data)
        self.assertEqual(response.headers["Location"], "/login?next=/regras-planner")

        self.bootstrap_admin()
        response = self.client.get("/regras-planner")
        self.assertEqual(response.status_code, 200, response.data)

        response = self.client.get("/views/planner-rules.html")
        self.assertEqual(response.status_code, 200, response.data)

        self.client.post("/api/logout", json={}, headers={"X-CSRF-Token": self.client.get("/api/me").get_json()["csrf_token"]})
        response = self.client.get("/biblioteca")
        self.assertEqual(response.status_code, 302, response.data)
        self.assertEqual(response.headers["Location"], "/login?next=/biblioteca")

    def test_team_management_is_authenticated_and_preserves_sprint_policy(self):
        response = self.client.get("/equipes")
        self.assertEqual(response.status_code, 302, response.data)
        self.assertEqual(response.headers["Location"], "/login?next=/equipes")
        self.assertEqual(self.client.get("/api/teams").status_code, 401)

        admin = self.bootstrap_admin()
        create_response = self.client.post(
            "/api/teams",
            json={
                "name": "Produto e Tecnologia",
                "project_name": "ReportChart",
                "sprint_duration_days": 30,
                "sprint_mode": "calendar",
            },
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(create_response.status_code, 201, create_response.data)
        team = create_response.get_json()["team"]
        self.assertEqual(team["sprint_duration_days"], 30)
        self.assertEqual(team["current_user_role"], "owner")

        update_response = self.client.patch(
            f"/api/teams/{team['id']}",
            json={"sprint_duration_days": 15},
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(update_response.status_code, 200, update_response.data)
        self.assertEqual(update_response.get_json()["team"]["sprint_duration_days"], 15)

        report_id = self.create_report(user_id=admin["user"]["id"])
        assign_response = self.client.patch(
            f"/api/reports/{report_id}/team",
            json={"team_id": team["id"]},
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(assign_response.status_code, 200, assign_response.data)
        assigned_report = assign_response.get_json()["report"]
        self.assertEqual(assigned_report["team_id"], team["id"])
        self.assertEqual(assigned_report["sprint_duration_days"], 15)

        created_user = self.create_user_as_admin(
            admin,
            email="team-member@example.com",
            display_name="Team Member",
        )
        member_response = self.client.post(
            f"/api/teams/{team['id']}/members",
            json={"user_id": created_user["id"], "role": "member"},
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(member_response.status_code, 200, member_response.data)
        self.assertEqual(len(member_response.get_json()["team"]["members"]), 2)

    def test_public_registration_is_disabled(self):
        self.bootstrap_admin()
        other = self.app.test_client()
        response = other.post(
            "/api/register",
            json={
                "email": "user@example.com",
                "password": "SenhaSegura47",
                "display_name": "User One",
            },
        )
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(response.get_json()["erro"], "Cadastro publico desativado.")

    def test_password_policy_rejects_weak_password(self):
        response = self.client.post(
            "/api/bootstrap",
            json={
                "email": "admin@example.com",
                "password": "Senha12345",
                "display_name": "Admin Root",
            },
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("12 caracteres", response.get_json()["erro"])

    def test_login_rate_limits_failed_attempts(self):
        self.bootstrap_admin()
        other = self.app.test_client()
        for _ in range(app_module.LOGIN_RATE_LIMIT_MAX - 1):
            response = other.post(
                "/api/login",
                json={"email": "admin@example.com", "password": "SenhaErrada47"},
            )
            self.assertEqual(response.status_code, 401, response.data)

        response = other.post(
            "/api/login",
            json={"email": "admin@example.com", "password": "SenhaErrada47"},
        )
        self.assertEqual(response.status_code, 429, response.data)
        self.assertIn("Retry-After", response.headers)

        response = other.post(
            "/api/login",
            json={"email": "admin@example.com", "password": "SenhaSegura47"},
        )
        self.assertEqual(response.status_code, 429, response.data)

    def test_admin_route_requires_admin(self):
        admin = self.bootstrap_admin()
        self.create_user_as_admin(admin)
        other = self.app.test_client()
        self.login_client(other)

        response = other.get("/api/admin/users")
        self.assertEqual(response.status_code, 403, response.data)

    def test_successful_login_updates_last_login_at(self):
        admin = self.bootstrap_admin()
        created_user = self.create_user_as_admin(admin)
        self.assertIsNone(created_user["last_login_at"])

        other = self.app.test_client()
        login_body = self.login_client(other)
        self.assertIsNotNone(login_body["user"]["last_login_at"])

        response = self.client.get("/api/admin/users")
        self.assertEqual(response.status_code, 200, response.data)
        users = response.get_json()["users"]
        user = next(item for item in users if item["email"] == "user@example.com")
        self.assertEqual(user["id"], created_user["id"])
        self.assertEqual(user["last_login_at"], login_body["user"]["last_login_at"])

    def test_admin_can_revoke_user_session(self):
        admin = self.bootstrap_admin()
        user = self.create_user_as_admin(admin)

        other = self.app.test_client()
        self.login_client(other)

        response = self.client.post(
            f"/api/admin/users/{user['id']}/sessions/revoke",
            json={},
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNotNone(response.get_json()["user"]["session_revoked_at"])

        response = other.get("/api/me")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.get_json()["authenticated"])
        self.assertTrue(
            any("reportchart_session=" in cookie for cookie in response.headers.getlist("Set-Cookie"))
        )

        response = self.client.post(
            f"/api/admin/users/{admin['user']['id']}/sessions/revoke",
            json={},
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(response.status_code, 400, response.data)

    def test_disabled_user_session_is_revoked_on_next_request(self):
        admin = self.bootstrap_admin()

        user = self.create_user_as_admin(admin)
        other = self.app.test_client()
        self.login_client(other)
        user_id = user["id"]

        response = self.client.patch(
            f"/api/admin/users/{user_id}",
            json={
                "email": "user@example.com",
                "display_name": "User One",
                "role": "disabled",
            },
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.data)

        response = other.get("/api/me")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.get_json()["authenticated"])
        self.assertTrue(
            any("reportchart_session=" in cookie for cookie in response.headers.getlist("Set-Cookie"))
        )

    def test_admin_can_create_and_list_custom_chart(self):
        admin = self.bootstrap_admin()

        response = self.client.post(
            "/api/admin/custom-charts",
            json={
                "name": "Categorias concluidas",
                "group": "Distribuição",
                "subtitle": "Top categorias concluidas",
                "source_key": "categoria",
                "metric_key": "done",
                "chart_type": "bar_v",
                "chart_types": ["bar_v", "pie", "donut"],
                "sort_mode": "metric_desc",
                "limit": 10,
                "sort_order": 5,
                "enabled": True,
            },
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(response.status_code, 201, response.data)
        chart = response.get_json()["chart"]
        self.assertEqual(chart["name"], "Categorias concluidas")
        self.assertEqual(chart["chart_id"], f"custom_{chart['id']}")
        self.assertEqual(chart["available_types"], ["bar_v", "pie", "donut"])

        response = self.client.get("/api/admin/custom-charts")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.get_json()["charts"]), 1)
        self.assertEqual(
            response.get_json()["charts"][0]["available_types"],
            ["bar_v", "pie", "donut"],
        )

        response = self.client.get("/api/charts/custom")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.get_json()["charts"]), 1)

    def test_custom_chart_validation_and_public_filtering(self):
        admin = self.bootstrap_admin()

        response = self.client.post(
            "/api/admin/custom-charts",
            json={
                "name": "Grafico invalido",
                "group": "Distribuição",
                "source_key": "categoria",
                "metric_key": "lead_time",
                "chart_type": "bar_v",
                "chart_types": ["bar_v", "pie"],
            },
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(response.status_code, 400, response.data)

        response = self.client.post(
            "/api/admin/custom-charts",
            json={
                "name": "Grafico com tipo inicial invalido",
                "group": "Distribuição",
                "source_key": "categoria",
                "metric_key": "done",
                "chart_type": "donut",
                "chart_types": ["bar_v", "pie"],
            },
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(response.status_code, 400, response.data)

        response = self.client.post(
            "/api/admin/custom-charts",
            json={
                "name": "Grafico inativo",
                "group": "Tempo",
                "source_key": "histograma",
                "metric_key": "count",
                "chart_type": "line",
                "enabled": False,
            },
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(response.status_code, 201, response.data)

        response = self.client.get("/api/admin/custom-charts")
        self.assertEqual(len(response.get_json()["charts"]), 1)
        self.assertFalse(response.get_json()["charts"][0]["enabled"])

        response = self.client.get("/api/charts/custom")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.get_json()["charts"], [])

    def test_profile_rule_admin_crud_and_public_filtering(self):
        admin = self.bootstrap_admin()

        response = self.client.post(
            "/api/admin/profile-rules",
            json={
                "name": "DEV",
                "base_profiles_text": "Devs",
                "labels_contains": ".dev;backend",
                "priority": 10,
                "enabled": True,
            },
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(response.status_code, 201, response.data)
        rule = response.get_json()["rule"]
        self.assertEqual(rule["name"], "DEV")
        self.assertEqual(rule["base_profiles"], ["Devs"])

        response = self.client.get("/api/profile-rules")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.get_json()["rules"]), 1)

        response = self.client.patch(
            f"/api/admin/profile-rules/{rule['id']}",
            json={"enabled": False},
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.get_json()["rule"]["enabled"])

        response = self.client.get("/api/profile-rules")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.get_json()["rules"], [])

    def test_report_summary_returns_heuristic_summary_for_owned_report(self):
        admin = self.bootstrap_admin()
        report_id = self.create_report(user_id=admin["user"]["id"])

        response = self.client.post(
            f"/api/reports/{report_id}/summary",
            json={},
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.data)
        body = response.get_json()
        self.assertEqual(body["provider"], "heuristic")
        self.assertIn("Panorama", body["summary"])
        self.assertEqual(body["scope"]["kind"], "general")
        self.assertEqual(body["facts"]["kpis"]["done"], 8)

    def test_report_section_summary_compares_current_section_with_general(self):
        admin = self.bootstrap_admin()
        report_id = self.create_report(user_id=admin["user"]["id"])

        response = self.client.post(
            f"/api/reports/{report_id}/summary",
            json={"chart_id": "areas"},
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.data)
        body = response.get_json()
        self.assertEqual(body["provider"], "heuristic")
        self.assertEqual(body["scope"]["kind"], "section")
        self.assertEqual(body["scope"]["chart_id"], "areas")
        self.assertEqual(body["facts"]["section"]["kind"], "grouped")
        self.assertIn("DEV", body["summary"])
        self.assertIn("Comparacao geral", body["summary"])

    def test_report_section_summary_accepts_aging_scope_and_filter(self):
        admin = self.bootstrap_admin()
        report_id = self.create_report(user_id=admin["user"]["id"])

        response = self.client.post(
            f"/api/reports/{report_id}/summary",
            json={
                "chart_id": "aging",
                "filters": {
                    "aging_view": "colaborador",
                },
            },
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.data)
        body = response.get_json()
        self.assertEqual(body["provider"], "heuristic")
        self.assertEqual(body["scope"]["kind"], "section")
        self.assertEqual(body["scope"]["chart_id"], "aging")
        self.assertEqual(body["scope"]["label"], "Aging")
        self.assertEqual(body["facts"]["scope"]["filters"]["aging_view"], "colaborador")
        self.assertEqual(body["facts"]["section"]["kind"], "metric_rows")
        self.assertIn("Aging", body["summary"])

    def test_report_section_summary_accepts_aging_by_task_label_filter(self):
        admin = self.bootstrap_admin()
        report_id = self.create_report(user_id=admin["user"]["id"])

        response = self.client.post(
            f"/api/reports/{report_id}/summary",
            json={
                "chart_id": "aging_tasks",
                "filters": {
                    "aging_task_labels": [".ARQUITETURA", "Backend"],
                },
            },
            headers={"X-CSRF-Token": admin["csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.data)
        body = response.get_json()
        self.assertEqual(body["provider"], "heuristic")
        self.assertEqual(body["scope"]["kind"], "section")
        self.assertEqual(body["scope"]["chart_id"], "aging_tasks")
        self.assertEqual(body["scope"]["label"], "Aging por Tarefa")
        self.assertEqual(body["facts"]["scope"]["filters"]["aging_task_labels"], [".ARQUITETURA", "Backend"])
        self.assertEqual(body["facts"]["section"]["kind"], "metric_rows")
        self.assertIn("Arquitetura API", body["summary"])

    def test_report_summary_respects_report_ownership(self):
        admin = self.bootstrap_admin()
        report_id = self.create_report(user_id=admin["user"]["id"])

        self.create_user_as_admin(
            admin,
            email="user2@example.com",
            display_name="User Two",
        )
        other = self.app.test_client()
        other_auth = self.login_client(other, email="user2@example.com")

        response = other.post(
            f"/api/reports/{report_id}/summary",
            json={},
            headers={"X-CSRF-Token": other_auth["csrf_token"]},
        )
        self.assertEqual(response.status_code, 404, response.data)


if __name__ == "__main__":
    unittest.main()
