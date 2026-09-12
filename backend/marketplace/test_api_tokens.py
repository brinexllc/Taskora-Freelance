from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .models import Category, Contract, Profile, Project, Proposal
from .security_models import ScopedApiToken
from .security_test_helpers import authenticate_client

User = get_user_model()
PASSWORD = "Secure-2026-password"


class ScopedApiTokenTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("api_owner", email="api@example.com", password=PASSWORD)
        Profile.objects.create(user=self.user, full_name="API owner")
        authenticate_client(self.client, self.user)

    def mint(self, **changes):
        response = self.client.post("/api/auth/api-tokens/", {"name": "Read integration", "password": PASSWORD,
            "scopes": ["profile:read"], "expires_in": 600, **changes}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + response.data["token"])
        return response, client

    def test_secret_shown_once_read_scope_and_individual_revocation(self):
        response, machine = self.mint()
        token = ScopedApiToken.objects.get(pk=response.data["id"])
        self.assertNotEqual(token.secret_hash, response.data["token"])
        self.assertEqual(len(token.secret_hash), 64)
        listed = self.client.get("/api/auth/api-tokens/").data[0]
        self.assertNotIn("token", listed)
        self.assertNotIn("secret_hash", listed)
        self.assertEqual(machine.get("/api/auth/me/").status_code, 200)
        self.assertEqual(machine.get("/api/projects/").status_code, 403)
        self.assertEqual(machine.get("/api/wallet/").status_code, 403)
        self.assertEqual(machine.post("/api/auth/change-password/", {}, format="json").status_code, 403)
        self.assertEqual(machine.post("/api/auth/api-tokens/", {}, format="json").status_code, 401)
        self.assertEqual(self.client.delete(f"/api/auth/api-tokens/{token.pk}/").status_code, 204)
        self.assertEqual(machine.get("/api/auth/me/").status_code, 401)

    def test_expiry_bounds_invalid_scope_and_operator_prohibition(self):
        payload = {"name": "Integration", "password": PASSWORD, "scopes": ["profile:read"], "expires_in": 86401}
        self.assertEqual(self.client.post("/api/auth/api-tokens/", payload, format="json").status_code, 400)
        payload.update(expires_in=600, scopes=["payments:write"])
        self.assertEqual(self.client.post("/api/auth/api-tokens/", payload, format="json").status_code, 400)
        response, machine = self.mint()
        ScopedApiToken.objects.filter(pk=response.data["id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(machine.get("/api/auth/me/").status_code, 401)
        response, machine = self.mint()
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.assertEqual(machine.get("/api/auth/me/").status_code, 401)
        authenticate_client(self.client, self.user, operator_confirmed=True)
        payload.update(scopes=["profile:read"])
        self.assertEqual(self.client.post("/api/auth/api-tokens/", payload, format="json").status_code, 403)

    def test_creation_needs_browser_csrf_and_password_and_password_change_revokes(self):
        client = APIClient(enforce_csrf_checks=True)
        authenticate_client(client, self.user)
        payload = {"name": "Integration", "password": PASSWORD, "scopes": ["profile:read"]}
        self.assertEqual(client.post("/api/auth/api-tokens/", payload, format="json").status_code, 403)
        csrf = client.get("/api/auth/csrf/").data["csrf_token"]
        client.credentials(HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(client.post("/api/auth/api-tokens/", {**payload, "password": "wrong"}, format="json").status_code, 403)
        self.assertEqual(client.post("/api/auth/api-tokens/", payload, format="json").status_code, 201)
        _, machine = self.mint()
        changed = self.client.post("/api/auth/change-password/", {"current_password": PASSWORD, "password": "Changed-2028-pass", "password_confirm": "Changed-2028-pass"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertFalse(ScopedApiToken.objects.filter(user=self.user, revoked_at__isnull=True).exists())
        self.assertEqual(machine.get("/api/auth/me/").status_code, 401)

    def test_read_scopes_preserve_private_project_contract_and_token_ownership(self):
        other = User.objects.create_user("other_owner", password=PASSWORD)
        Profile.objects.create(user=other, full_name="Other owner")
        freelancer = User.objects.create_user("other_freelancer", password=PASSWORD)
        Profile.objects.create(user=freelancer, full_name="Other freelancer")
        project = Project.objects.create(owner=other, title="Private project", description="Private brief", category=Category.objects.get(slug="other"), budget_min=1000, budget_max=1000, status=Project.Status.DRAFT)
        proposal = Proposal.objects.create(project=project, freelancer=freelancer, freelancer_name="Other", freelancer_email="other@example.com", cover_letter="Private", amount=1000, delivery_days=2)
        contract = Contract.objects.create(project=project, proposal=proposal, customer=other, freelancer=freelancer, amount=1000, delivery_days=2, terms="Private terms")
        response, machine = self.mint(scopes=["projects:read", "contracts:read"])
        self.assertEqual(machine.get(f"/api/projects/{project.pk}/").status_code, 404)
        self.assertEqual(machine.get(f"/api/contracts/{contract.pk}/").status_code, 404)
        self.assertEqual(machine.post(f"/api/contracts/{contract.pk}/accept/", {}, format="json").status_code, 403)
        foreign_client = APIClient()
        authenticate_client(foreign_client, other)
        self.assertEqual(foreign_client.delete(f"/api/auth/api-tokens/{response.data['id']}/").status_code, 404)
