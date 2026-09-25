from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditAction, AuditLog
from apps.engine.models import Assignment
from apps.organizations.models import Membership, Role
from conftest import ExperimentFactory, OrganizationFactory, ProjectFactory, UserFactory

RESULTS = {
    "control": {"exposures": 70000, "unique_users": 60000, "conversions": 6000, "conversion_rate": 0.10},
    "treatment": {"exposures": 70000, "unique_users": 60000, "conversions": 7200, "conversion_rate": 0.12},
}


@pytest.fixture(autouse=True)
def results():
    with patch("apps.decisions.context.query_experiment_results", return_value=RESULTS):
        yield


@pytest.fixture
def outsider():
    client = APIClient()
    client.force_authenticate(user=UserFactory())
    return client


@pytest.mark.django_db
class TestOrganizationIsolation:
    def test_non_member_gets_404(self, outsider, running_experiment):
        base = f"/api/v1/experiments/{running_experiment.id}"
        for path in ("/", "/results/", "/health/", "/timeline/", "/decision/", "/rollout/", "/explain/"):
            assert outsider.get(base + path).status_code == 404, path
        assert outsider.post(base + "/rollback/", {}, format="json").status_code == 404

    def test_list_only_shows_own_organizations(self, authenticated_client, running_experiment):
        ExperimentFactory()  # another organization
        response = authenticated_client.get("/api/v1/experiments/")
        assert [e["key"] for e in response.data["results"]] == [running_experiment.key]

    def test_cannot_create_experiment_in_foreign_project(self, authenticated_client):
        foreign = ProjectFactory()
        response = authenticated_client.post(
            "/api/v1/experiments/", {"project_id": str(foreign.id), "key": "x", "name": "X"}, format="json",
        )
        assert response.status_code == 404

    def test_organizations_and_projects_filtered(self, authenticated_client, project):
        OrganizationFactory()
        ProjectFactory()
        orgs = authenticated_client.get("/api/v1/organizations/").data["results"]
        projects = authenticated_client.get("/api/v1/projects/").data["results"]
        assert [o["id"] for o in orgs] == [str(project.organization_id)]
        assert [p["id"] for p in projects] == [str(project.id)]

    def test_audit_logs_filtered(self, authenticated_client, running_experiment, outsider):
        other = ExperimentFactory()
        from apps.audit.service import record_audit

        record_audit(AuditAction.CONFIG_CHANGED, experiment=other)
        record_audit(AuditAction.CONFIG_CHANGED, experiment=running_experiment)
        response = authenticated_client.get("/api/v1/audit-logs/")
        assert {str(r["experiment"]) for r in response.data["results"]} == {str(running_experiment.id)}
        assert outsider.get("/api/v1/audit-logs/").data["count"] == 0

    def test_portfolio_query_scoped(self, outsider, running_experiment):
        response = outsider.post("/api/v1/ai/query/", {"question": "what is running?"}, format="json")
        assert response.data["experiments"] == []

    def test_superuser_sees_everything(self, running_experiment):
        client = APIClient()
        client.force_authenticate(user=UserFactory(is_superuser=True))
        assert client.get(f"/api/v1/experiments/{running_experiment.id}/").status_code == 200


@pytest.mark.django_db
class TestRoles:
    def test_viewer_is_read_only(self, make_member, running_experiment):
        viewer = make_member(Role.VIEWER)
        base = f"/api/v1/experiments/{running_experiment.id}"
        assert viewer.get(base + "/").status_code == 200
        assert viewer.post(base + "/pause/").status_code == 403
        assert viewer.post(base + "/rollout/", {"percentage": 10, "reason": "x"}, format="json").status_code == 403
        assert viewer.post(base + "/ask/", {"question": "why?"}, format="json").status_code == 403
        assert viewer.patch(base + "/", {"name": "renamed"}, format="json").status_code == 403

    def test_analyst_can_analyze_not_operate(self, make_member, running_experiment):
        analyst = make_member(Role.ANALYST)
        base = f"/api/v1/experiments/{running_experiment.id}"
        assert analyst.post(base + "/ask/", {"question": "why?"}, format="json").status_code == 200
        assert analyst.post(base + "/segments/", {"segments": []}, format="json").status_code == 200
        assert analyst.post(base + "/decision/", {"apply": False}, format="json").status_code == 201
        assert analyst.post(base + "/decision/", {"apply": True}, format="json").status_code == 403
        assert analyst.post(base + "/rollback/", {}, format="json").status_code == 403
        assert analyst.post(base + "/guardrails/", {}, format="json").status_code == 403

    def test_manager_operates_experiments(self, make_member, running_experiment):
        manager = make_member(Role.EXPERIMENT_MANAGER)
        base = f"/api/v1/experiments/{running_experiment.id}"
        assert manager.post(base + "/rollout/", {"percentage": 5000, "reason": "ramp"},
                            format="json").status_code == 200
        assert manager.post(base + "/decision/", {"apply": True}, format="json").status_code == 201
        assert manager.post(base + "/pause/").status_code == 200

    def test_manager_cannot_manage_org(self, make_member, organization):
        manager = make_member(Role.EXPERIMENT_MANAGER)
        response = manager.post(f"/api/v1/organizations/{organization.id}/members/",
                                {"email": "a@b.c", "role": "VIEWER"}, format="json")
        assert response.status_code == 403
        assert manager.patch(f"/api/v1/organizations/{organization.id}/", {"name": "x"},
                             format="json").status_code == 403

    def test_api_key_requires_admin(self, make_member, project):
        manager = make_member(Role.EXPERIMENT_MANAGER)
        response = manager.post("/api/v1/auth/api-keys/", {"name": "k", "project_id": str(project.id)},
                                format="json")
        assert response.status_code == 403

    def test_admin_creates_api_key_audited(self, authenticated_client, project):
        response = authenticated_client.post("/api/v1/auth/api-keys/",
                                             {"name": "k", "project_id": str(project.id)}, format="json")
        assert response.status_code == 201
        assert AuditLog.objects.filter(action=AuditAction.API_KEY_CREATED,
                                       organization=project.organization).exists()


@pytest.mark.django_db
class TestMembership:
    def test_creating_org_makes_creator_admin(self, authenticated_client, user):
        response = authenticated_client.post("/api/v1/organizations/", {"name": "Acme"}, format="json")
        assert response.status_code == 201
        assert Membership.objects.get(organization_id=response.data["id"], user=user).role == Role.ADMIN

    def test_member_lifecycle_is_audited(self, authenticated_client, organization):
        invitee = UserFactory(email="new@example.com")
        url = f"/api/v1/organizations/{organization.id}/members/"
        response = authenticated_client.post(url, {"email": "NEW@example.com", "role": "ANALYST"}, format="json")
        assert response.status_code == 201
        mid = response.data["id"]
        assert authenticated_client.patch(f"{url}{mid}/", {"role": "VIEWER"}, format="json").data["role"] == "VIEWER"
        assert authenticated_client.delete(f"{url}{mid}/").status_code == 204
        logs = AuditLog.objects.filter(action=AuditAction.PERMISSION_CHANGED, organization=organization)
        assert logs.count() == 3
        assert not Membership.objects.filter(user=invitee).exists()

    def test_duplicate_and_unknown_user(self, authenticated_client, organization, user):
        url = f"/api/v1/organizations/{organization.id}/members/"
        assert authenticated_client.post(url, {"email": user.email, "role": "VIEWER"},
                                         format="json").status_code == 400
        assert authenticated_client.post(url, {"email": "ghost@example.com", "role": "VIEWER"},
                                         format="json").status_code == 400

    def test_cannot_remove_last_admin(self, authenticated_client, organization, user):
        membership = Membership.objects.get(organization=organization, user=user)
        url = f"/api/v1/organizations/{organization.id}/members/{membership.id}/"
        assert authenticated_client.patch(url, {"role": "VIEWER"}, format="json").status_code == 400
        assert authenticated_client.delete(url).status_code == 400

    def test_me_lists_memberships(self, authenticated_client, organization):
        response = authenticated_client.get("/api/v1/auth/me/")
        assert response.data["memberships"] == [
            {"organization_id": str(organization.id), "organization_name": organization.name, "role": "ADMIN"}
        ]


@pytest.mark.django_db
class TestAuditTrail:
    def test_rollout_change_records_ip_and_org(self, authenticated_client, running_experiment):
        authenticated_client.post(f"/api/v1/experiments/{running_experiment.id}/rollout/",
                                  {"percentage": 5000, "reason": "Manual rollout"}, format="json",
                                  HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1")
        log = AuditLog.objects.get(action=AuditAction.ROLLOUT_CHANGED)
        assert log.ip_address == "203.0.113.7"
        assert log.organization_id == running_experiment.project.organization_id
        assert log.old_value == {"rollout_percentage": 10000}
        assert log.metadata["reason"] == "Manual rollout"

    def test_lifecycle_actions_use_plan_names(self, authenticated_client, running_experiment):
        base = f"/api/v1/experiments/{running_experiment.id}"
        authenticated_client.post(base + "/pause/")
        authenticated_client.post(base + "/start/")
        authenticated_client.patch(base + "/", {"name": "Renamed"}, format="json")
        actions = set(AuditLog.objects.values_list("action", flat=True))
        assert {"EXPERIMENT_PAUSED", "EXPERIMENT_RESUMED", "CONFIG_CHANGED"} <= actions


@pytest.mark.django_db
class TestDebugger:
    def test_debug_does_not_persist(self, authenticated_client, running_experiment, mock_cassandra):
        response = authenticated_client.post("/api/v1/evaluate/debug/",
                                             {"experiment_key": running_experiment.key, "user_id": "u1"},
                                             format="json")
        assert response.status_code == 200
        assert response.data["result"]["assigned"] is True
        assert Assignment.objects.count() == 0
        assert mock_cassandra == {}

    def test_debug_scoped_to_organization(self, outsider, running_experiment):
        response = outsider.post("/api/v1/evaluate/debug/",
                                 {"experiment_key": running_experiment.key, "user_id": "u1"}, format="json")
        assert response.status_code == 404

    def test_ambiguous_key_needs_project(self, authenticated_client, running_experiment, organization):
        other_project = ProjectFactory(organization=organization)
        ExperimentFactory(project=other_project, key=running_experiment.key)
        payload = {"experiment_key": running_experiment.key, "user_id": "u1"}
        assert authenticated_client.post("/api/v1/evaluate/debug/", payload, format="json").status_code == 400
        payload["project_id"] = str(running_experiment.project_id)
        assert authenticated_client.post("/api/v1/evaluate/debug/", payload, format="json").status_code == 200
