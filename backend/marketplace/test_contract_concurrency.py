"""Q01/Q02/Q03 exercise real session + CSRF requests on isolated PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Category, Contract, Deliverable, Dispute, PlatformFee, Profile, Project, Proposal, WalletEntry
from .security_test_helpers import authenticate_client


class ContractApiFixture:
    def setUp(self):
        self.customer = get_user_model().objects.create_user(username="api-race-customer")
        self.freelancer = get_user_model().objects.create_user(username="api-race-freelancer")
        Profile.objects.create(user=self.customer, role="client", balance=1000000)
        Profile.objects.create(user=self.freelancer, role="freelancer", balance=0)
        category = Category.objects.create(slug="race-tests", name="Synthetic concurrency")
        project = Project.objects.create(owner=self.customer, category=category, title="Concurrent contract",
            description="Synthetic scope", budget_min=1000000, budget_max=1000000)
        proposal = Proposal.objects.create(project=project, freelancer=self.freelancer, amount=1000000,
            delivery_days=1, freelancer_name="Synthetic worker", freelancer_email="worker@example.test", cover_letter="Synthetic scope")
        self.contract = Contract.objects.create(project=project, proposal=proposal, customer=self.customer,
            freelancer=self.freelancer, amount=1000000, delivery_days=1, terms="Confirmed terms", fee_percent=5,
            fee_amount=50000, status="awaiting_funding", customer_signed_at=timezone.now(), freelancer_signed_at=timezone.now(),
            acceptance_workflow_version=1, acceptance_criteria="All supplied checks pass", demonstration_method="Test server",
            test_scenario="Open demo and run expected interaction")
        self.customer_clients = [self.session_client(self.customer), self.session_client(self.customer)]
        self.freelancer_client = self.session_client(self.freelancer)

    def session_client(self, user):
        client = APIClient(enforce_csrf_checks=True)
        authenticate_client(client, user)
        response = client.get("/api/auth/csrf/")
        self.assertEqual(response.status_code, 200, response.data)
        return client, response.data["csrf_token"]

    def post(self, client_and_csrf, action, body):
        client, csrf = client_and_csrf
        return client.post(f"/api/contracts/{self.contract.pk}/{action}/", body, format="json", HTTP_X_CSRFTOKEN=csrf)

    def race(self, operations):
        barrier = Barrier(len(operations))
        def invoke(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                response = self.post(*operation)
                return response.status_code, response.data
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            return list(pool.map(invoke, operations))

    def funded_result(self):
        response = self.post(self.customer_clients[0], "fund", {"confirmed": True})
        self.assertEqual(response.status_code, 200, response.data)
        self.contract.refresh_from_db()
        work = Deliverable.objects.create(contract=self.contract, file="synthetic/result.zip", filename="result.zip",
            preview_text="Synthetic tested result", deadline_snapshot=self.contract.deadline,
            contract_version=self.contract.version, verification_steps="Run the agreed scenario")
        Contract.objects.filter(pk=self.contract.pk).update(status="submitted")
        return work

    def assert_one_hold(self):
        holds = WalletEntry.objects.filter(contract=self.contract, kind="escrow_hold")
        self.assertEqual(holds.count(), 1)
        self.assertEqual(holds.get().amount, Decimal(-1000000))
        self.assertEqual(Profile.objects.get(user=self.customer).balance, Decimal(0))


@skipUnless(connection.vendor == "postgresql", "Q01/Q02/Q03 require isolated PostgreSQL row locking.")
class ContractApiConcurrencyTests(ContractApiFixture, TransactionTestCase):

    def test_q01_parallel_fund_reserves_once(self):
        results = self.race([(client, "fund", {"confirmed": True}) for client in self.customer_clients])
        self.assertEqual([status for status, _ in results], [200, 200], results)
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.escrow_amount, Decimal(1000000))
        self.assertEqual(self.contract.status, "active")
        self.assert_one_hold()


    def test_q02_parallel_accept_pays_once_and_accepts_one_version(self):
        work = self.funded_result()
        body = {"confirmed": True, "deliverable_id": work.pk}
        results = self.race([(client, "accept", body) for client in self.customer_clients])
        self.assertEqual([status for status, _ in results], [200, 200], results)
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.status, "completed")
        self.assertEqual(self.contract.accepted_deliverable_id, work.pk)
        self.assertEqual(self.contract.events.filter(kind="deliverable_accepted").count(), 1)
        self.assertEqual(WalletEntry.objects.filter(contract=self.contract, kind="escrow_release").count(), 1)
        self.assertEqual(PlatformFee.objects.filter(contract=self.contract).count(), 1)
        self.assertEqual(PlatformFee.objects.get(contract=self.contract).fee_amount, Decimal(50000))
        self.assertEqual(Profile.objects.get(user=self.freelancer).balance, Decimal(950000))
        self.assertEqual(self.contract.escrow_amount, 0)
        self.assert_one_hold()

    def test_q03_dispute_versus_accept_commits_one_allowed_transition(self):
        work = self.funded_result()
        results = self.race([
            (self.customer_clients[0], "accept", {"confirmed": True, "deliverable_id": work.pk}),
            (self.freelancer_client, "dispute", {"confirmed": True, "reason": "Synthetic unresolved acceptance disagreement"}),
        ])
        self.contract.refresh_from_db()
        if self.contract.status == "disputed":
            self.assertEqual([status for status, _ in results], [400, 201], results)
            self.assertEqual(Dispute.objects.filter(contract=self.contract).count(), 1)
            self.assertFalse(PlatformFee.objects.filter(contract=self.contract).exists())
            self.assertFalse(WalletEntry.objects.filter(contract=self.contract, kind="escrow_release").exists())
            self.assertIsNone(self.contract.accepted_deliverable_id)
            self.assertEqual(Profile.objects.get(user=self.freelancer).balance, Decimal(0))
            self.assertEqual(self.contract.escrow_amount, Decimal(1000000))
        else:
            self.assertEqual(self.contract.status, "completed")
            self.assertEqual([status for status, _ in results], [200, 400], results)
            self.assertFalse(Dispute.objects.filter(contract=self.contract).exists())
            self.assertEqual(PlatformFee.objects.filter(contract=self.contract).count(), 1)
            self.assertEqual(WalletEntry.objects.filter(contract=self.contract, kind="escrow_release").count(), 1)
            self.assertEqual(Profile.objects.get(user=self.freelancer).balance, Decimal(950000))
            self.assertEqual(self.contract.escrow_amount, 0)
        self.assert_one_hold()


class ContractAcceptancePermissionTests(ContractApiFixture, TransactionTestCase):
    def test_new_workflow_requires_explicit_reviewed_version(self):
        work = self.funded_result()
        response = self.post(self.customer_clients[0], "accept", {"confirmed": True})
        self.assertEqual(response.status_code, 400, response.data)
        response = self.post(self.customer_clients[0], "accept", {"confirmed": True, "deliverable_id": work.pk + 1000})
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(PlatformFee.objects.filter(contract=self.contract).exists())
        response = self.post(self.customer_clients[0], "accept", {"confirmed": True, "deliverable_id": work.pk})
        self.assertEqual(response.status_code, 200, response.data)
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.accepted_deliverable_id, work.pk)

    def test_accept_without_csrf_or_by_non_customer_never_releases(self):
        work = self.funded_result()
        body = {"confirmed": True, "deliverable_id": work.pk}
        client, _ = self.customer_clients[0]
        response = client.post(f"/api/contracts/{self.contract.pk}/accept/", body, format="json")
        self.assertEqual(response.status_code, 403, response.data)
        response = self.post(self.freelancer_client, "accept", body)
        self.assertEqual(response.status_code, 403, response.data)
        outsider = get_user_model().objects.create_user(username="unrelated-contract-user")
        Profile.objects.create(user=outsider)
        response = self.post(self.session_client(outsider), "accept", body)
        self.assertEqual(response.status_code, 404, response.data)
        self.assertFalse(PlatformFee.objects.filter(contract=self.contract).exists())
        self.assertEqual(Profile.objects.get(user=self.freelancer).balance, Decimal(0))
