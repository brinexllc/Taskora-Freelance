import re

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import PasswordResetCode, Project, Proposal


class ProjectApiTests(APITestCase):
    def setUp(self):
        self.project = Project.objects.create(
            title="React dashboard",
            description="Build a dashboard for a growing SaaS product.",
            category=Project.Category.DEVELOPMENT,
            budget_min=800,
            budget_max=1200,
            skills=["React", "Django"],
            client_name="Taskora Client",
        )

    def test_lists_active_projects(self):
        response = self.client.get(reverse("project-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["proposal_count"], 0)

    def test_creates_proposal(self):
        response = self.client.post(
            reverse("proposal-list"),
            {
                "project": self.project.id,
                "freelancer_name": "Aziza",
                "freelancer_email": "aziza@example.com",
                "cover_letter": "Готова выполнить проект.",
                "amount": "950.00",
                "delivery_days": 7,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Proposal.objects.count(), 1)

    def test_rejects_invalid_budget_range(self):
        response = self.client.post(
            reverse("project-list"),
            {
                "title": "Invalid budget",
                "description": "Budget maximum is lower than minimum.",
                "category": "design",
                "budget_min": "1000.00",
                "budget_max": "500.00",
                "skills": [],
                "client_name": "Client",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AuthenticationApiTests(APITestCase):
    def setUp(self):
        self.password = "Secure-pass-2026"
        self.registration = {
            "full_name": "Aziz Rahimov",
            "email": "aziz@example.com",
            "password": self.password,
            "password_confirm": self.password,
        }

    def register(self):
        return self.client.post("/api/auth/register/", self.registration, format="json")

    def test_register_login_role_and_logout(self):
        response = self.register()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        token = response.data["token"]
        self.assertEqual(response.data["user"]["role"], "")

        response = self.client.get("/api/profiles/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [{"id": 1, "full_name": "Aziz Rahimov", "role": ""}])

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        response = self.client.put("/api/auth/role/", {"role": "freelancer"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "freelancer")

        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.credentials()
        response = self.client.post(
            "/api/auth/login/",
            {"email": self.registration["email"], "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["role"], "freelancer")

    def test_password_reset_flow(self):
        self.register()
        response = self.client.post(
            "/api/auth/password-reset/request/", {"email": self.registration["email"]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        code = re.search(r"\b(\d{6})\b", mail.outbox[0].body).group(1)

        response = self.client.post(
            "/api/auth/password-reset/verify/",
            {"email": self.registration["email"], "code": code},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        new_password = "New-secure-pass-2026"
        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {"email": self.registration["email"], "reset_token": response.data["reset_token"], "password": new_password, "password_confirm": new_password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(PasswordResetCode.objects.filter(used_at__isnull=False).count(), 1)


class ProductionCorsTests(APITestCase):
    @override_settings(CORS_ALLOW_ALL_ORIGINS=True)
    def test_preflight_allows_railway_frontend(self):
        response = self.client.options(
            "/api/auth/login/",
            HTTP_ORIGIN="https://taskora-frontend-production.up.railway.app",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,authorization",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"],
            "*",
        )
        self.assertIn("POST", response.headers["Access-Control-Allow-Methods"])
