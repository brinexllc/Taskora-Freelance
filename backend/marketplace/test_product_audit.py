import json
import statistics
import time
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import (Category, Contract, Deliverable, Profile, Project, Proposal,
                     ProposalConversation, ProposalMessage, Review, WalletEntry, Skill)
from .auth_serializers import PublicProfileListSerializer
from .profile_metrics import with_profile_metrics


class ProductAuditTests(APITestCase):
    def setUp(self):
        self.customer = get_user_model().objects.create_user(username='audit_customer', email='audit_customer@example.com')
        self.worker = get_user_model().objects.create_user(username='audit_worker', email='audit_worker@example.com')
        self.stranger = get_user_model().objects.create_user(username='audit_stranger')
        for user, role in [(self.customer, 'client'), (self.worker, 'freelancer'), (self.stranger, 'client')]:
            Profile.objects.create(user=user, full_name=user.username, role=role, balance=1000000 if role == 'client' else 0)
        self.category = Category.objects.first()
        self.project = Project.objects.create(owner=self.customer, category=self.category, title='Private API project', description='Implement the specified API',
            budget_min=1000000, budget_max=1000000, status='published', skills_unspecified=True, deadline=timezone.localdate()+timedelta(days=10))
        self.proposal = Proposal.objects.create(project=self.project, freelancer=self.worker, freelancer_name='Worker', freelancer_email=self.worker.email,
            amount=1000000, delivery_days=5, cover_letter='I can implement the documented API')
        self.client.force_authenticate(self.customer)

    def contract(self, **kwargs):
        return Contract.objects.create(project=self.project, proposal=self.proposal, customer=self.customer, freelancer=self.worker,
            amount=1000000, fee_percent=5, fee_amount=50000, delivery_days=5, terms='Terms', **kwargs)

    def post(self, path, data=None):
        return self.client.post('/api/'+path+'/', data or {}, format='json')

    def test_clone_preserves_history_finances_and_revalidates_deadline(self):
        import uuid
        contract = self.contract(status='cancelled')
        self.project.status = 'cancelled'; self.project.save()
        body = {'idempotency_key': str(uuid.uuid4()), 'deadline': (timezone.localdate()+timedelta(days=20)).isoformat()}
        response = self.post(f'projects/{self.project.pk}/clone', body)
        self.assertEqual(response.status_code, 201, response.data)
        clone = Project.objects.get(pk=response.data['id'])
        self.assertEqual(clone.source_project, self.project)
        self.assertEqual(clone.status, 'draft')
        self.assertFalse(clone.proposals.exists())
        self.assertFalse(hasattr(clone, 'contract'))
        self.assertFalse(WalletEntry.objects.exists())
        self.assertEqual(self.post(f'projects/{self.project.pk}/clone', body).data['id'], clone.pk)
        self.assertEqual(Project.objects.count(), 2)
        contract.refresh_from_db(); self.assertEqual(contract.status, 'cancelled')
        body['deadline'] = (timezone.localdate()+timedelta(days=30)).isoformat()
        self.assertEqual(self.post(f'projects/{self.project.pk}/clone', body).status_code, 400)
        body['idempotency_key'] = str(uuid.uuid4()); body['deadline'] = '2001-01-01'
        self.assertEqual(self.post(f'projects/{self.project.pk}/clone', body).status_code, 400)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.post(f'projects/{self.project.pk}/clone', body).status_code, 404)

    def test_conversation_private_paginated_immutable_and_unread(self):
        response = self.post(f'proposals/{self.proposal.pk}/conversation')
        self.assertEqual(response.status_code, 200)
        pk = response.data['id']
        sent = self.post(f'proposal-conversations/{pk}/messages', {'text': 'Discuss the acceptance test before signing'})
        self.assertEqual(sent.status_code, 201, sent.data)
        self.assertFalse(Contract.objects.exists()); self.assertFalse(WalletEntry.objects.exists())
        self.client.force_authenticate(self.worker)
        listing = self.client.get('/api/proposal-conversations/').data['results'][0]
        self.assertEqual(listing['unread_count'], 1)
        self.assertEqual(self.post(f'proposal-conversations/{pk}/read', {'through_id': sent.data['id']}).status_code, 200)
        self.assertIsNotNone(ProposalMessage.objects.get(pk=sent.data['id']).read_at)
        self.assertEqual(self.post(f'proposal-conversations/{pk}/report', {'reason': 'Please review this message for spam'}).status_code, 201)
        self.assertEqual(self.client.patch(f'/api/proposal-conversations/{pk}/', {'text': 'tamper'}, format='json').status_code, 405)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(f'/api/proposal-conversations/{pk}/messages/').status_code, 404)
        self.assertEqual(self.post(f'proposal-conversations/{pk}/messages', {'text': 'intrusion'}).status_code, 404)

    def test_timeliness_uses_accepted_submission_and_excludes_ambiguous(self):
        now = timezone.now()
        contract = self.contract(status='completed', deadline=now-timedelta(days=3), completed_at=now)
        work = Deliverable.objects.create(contract=contract, file='missing/test', filename='result.zip', preview_text='Demo', deadline_snapshot=now-timedelta(days=3), contract_version=1)
        Deliverable.objects.filter(pk=work.pk).update(created_at=now-timedelta(days=4))
        contract.accepted_deliverable=work; contract.save()
        Review.objects.create(contract=contract, author=self.customer, target=self.worker, rating=4, text='Agreed result delivered')
        Review.objects.create(contract=contract, author=self.stranger, target=self.worker, rating=1, text='Hidden fixture', published=False)
        profile = with_profile_metrics(Profile.objects.filter(user=self.worker)).get()
        self.assertEqual(profile.metric_timely_total, 1); self.assertEqual(profile.metric_timely_count, 1)
        self.assertEqual(profile.average_rating, 4)
        self.assertEqual(profile.metric_review_count, 1)
        self.assertEqual(profile.metric_completed_count, 1)
        Deliverable.objects.filter(pk=work.pk).update(created_at=now-timedelta(days=2))
        self.assertEqual(with_profile_metrics(Profile.objects.filter(user=self.worker)).get().metric_timely_count, 0)
        Deliverable.objects.filter(pk=work.pk).update(deadline_snapshot=None)
        self.assertEqual(with_profile_metrics(Profile.objects.filter(user=self.worker)).get().metric_timely_total, 0)

    def test_terms_amendment_requires_both_parties_preserves_submission_snapshot(self):
        now = timezone.now()
        contract = self.contract(status='active', deadline=now+timedelta(days=2), funded_at=now, escrow_amount=1000000)
        work = Deliverable.objects.create(contract=contract, file='missing/test', filename='result.zip', preview_text='Demo', deadline_snapshot=contract.deadline, contract_version=1)
        response = self.post(f'contracts/{contract.pk}/amend', {'expected_version': 1, 'deadline': (now+timedelta(days=10)).isoformat(), 'scope': 'Additional agreed scenario'})
        self.assertEqual(response.status_code, 201, response.data)
        contract.refresh_from_db(); self.assertEqual(contract.version, 1)
        self.client.force_authenticate(self.worker)
        response = self.post(f'contracts/{contract.pk}/amendments/{response.data["id"]}/accept', {'accepted': True})
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db(); work.refresh_from_db()
        self.assertEqual(contract.version, 2); self.assertEqual(work.contract_version, 1)
        self.assertNotEqual(contract.deadline, work.deadline_snapshot)
        self.assertEqual(contract.escrow_amount, Decimal('1000000'))

    def test_expired_review_notifies_once_without_payment(self):
        contract = self.contract(status=Contract.Status.REVIEW, funded_at=timezone.now(), escrow_amount=1000000)
        Deliverable.objects.create(contract=contract, file='missing/test', filename='result.zip', preview_text='Demo', review_due_at=timezone.now()-timedelta(days=1))
        call_command('escalate_reviews', stdout=StringIO()); call_command('escalate_reviews', stdout=StringIO())
        contract.refresh_from_db()
        self.assertEqual(contract.escrow_amount, Decimal('1000000'))
        self.assertEqual(contract.events.filter(kind='review_overdue').count(), 1)
        self.assertFalse(WalletEntry.objects.exists())

    def test_profile_queries_do_not_grow_with_page_size(self):
        skill = Skill.objects.get(name='React')
        for i in range(48):
            user = get_user_model().objects.create_user(username=f'profile_benchmark_{i}')
            profile = Profile.objects.create(user=user, full_name=user.username, role='freelancer', portfolio=[{'image': 'A'*10000}])
            profile.skills.add(skill)
        measurements = []
        for size in (12, 48):
            durations=[]; query_count=None; payload=None
            for _ in range(6):
                queryset = with_profile_metrics(Profile.objects.select_related('user').prefetch_related('skills__categories').defer('portfolio', 'services'))[:size]
                started=time.perf_counter()
                with CaptureQueriesContext(connection) as queries:
                    payload = PublicProfileListSerializer(queryset, many=True).data
                durations.append((time.perf_counter()-started)*1000)
                query_count = len(queries)
            measurements.append({'profiles': size, 'queries': query_count, 'p50_ms': round(statistics.median(durations), 2),
                'p95_ms': round(sorted(durations)[-1], 2), 'bytes': len(json.dumps(payload).encode())})
            self.assertTrue(all('portfolio' not in item for item in payload))
        self.assertEqual(measurements[0]['queries'], measurements[1]['queries'])
        self.assertLessEqual(measurements[1]['queries'], 4)
        print('PROFILE_BENCHMARK '+json.dumps({'database': connection.vendor, 'runs': 6, 'measurements': measurements}))
        print('PROFILE_QUERY_PLAN '+queryset.explain())

    def test_new_acceptance_requires_the_inspected_submission_id(self):
        contract = self.contract(status=Contract.Status.REVIEW, funded_at=timezone.now(), escrow_amount=1000000, acceptance_workflow_version=1)
        work = Deliverable.objects.create(contract=contract, file='missing/test', filename='result.zip', preview_text='Agreed demo')
        self.assertEqual(self.post(f'contracts/{contract.pk}/accept', {'confirmed': True}).status_code, 400)
        self.assertEqual(self.post(f'contracts/{contract.pk}/accept', {'confirmed': True, 'deliverable_id': work.pk+1}).status_code, 400)
        self.assertFalse(WalletEntry.objects.exists())
        contract.refresh_from_db(); self.assertEqual(contract.escrow_amount, 1000000)

    def test_review_window_is_validated_even_before_criteria_are_filled(self):
        for value in (0, 31, 'bad'):
            with self.subTest(value=value):
                response = self.post(f'proposals/{self.proposal.pk}/accept', {'review_days': value})
                self.assertEqual(response.status_code, 400, response.data)
                self.assertFalse(Contract.objects.exists())
