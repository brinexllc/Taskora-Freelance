from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Project, Proposal


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
