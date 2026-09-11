"""Acceptance and adversarial tests for the revised MVP, using isolated wallets/files."""
from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Sum
from django.test import override_settings
from django.utils import timezone
from .tests import MarketplaceTests
from .models import Contract, Dispute, Message, Notification, Profile, Project, Review, WalletEntry


class EscrowTests(MarketplaceTests):
    def test_conversation_preview_and_unread_are_participant_scoped(self):
        pk = self.signed_contract()
        Message.objects.create(contract_id=pk, sender=self.customer, text='First question')
        Message.objects.create(contract_id=pk, sender=self.customer, text='Second question')
        Message.objects.create(contract_id=pk, sender=self.freelancer, text='Reply')
        Message.objects.create(contract_id=pk, system=True, text='System event')
        Message.objects.create(contract_id=pk, sender=self.freelancer, filename='preview.png', read_at=timezone.now())
        self.as_user(self.customer)
        data = self.client.get('/api/contracts/?conversation=1&conversation_filter=unread').data['results'][0]
        self.assertEqual(data['unread_count'], 1)
        self.assertEqual(data['last_message_filename'], 'preview.png')
        self.assertEqual(data['last_message_text'], '')
        self.assertIsNotNone(data['last_message_at'])
        self.assertEqual(self.post(f'contracts/{pk}/messages/read').status_code, 200)
        self.assertEqual(self.client.get('/api/contracts/?conversation_filter=unread').data['count'], 0)
        self.as_user(self.freelancer)
        self.assertEqual(self.client.get(f'/api/contracts/{pk}/').data['unread_count'], 2)
        self.assertEqual(self.client.get('/api/contracts/?conversation_filter=clients').data['count'], 1)
        self.assertEqual(self.client.get('/api/projects/?assigned=1').data['count'], 1)
        self.assertEqual(self.client.get('/api/projects/?assigned=1&status=completed').data['count'], 0)
        self.as_user(self.other)
        self.assertEqual(self.client.get('/api/contracts/?conversation=1').data['count'], 0)
        self.assertEqual(self.client.get(f'/api/contracts/{pk}/').status_code, 404)
        self.assertEqual(self.client.get('/api/projects/?assigned=1').data['count'], 0)

    def signed_contract(self):
        pk = self.contract()
        for user in [self.customer, self.freelancer]:
            self.as_user(user)
            self.assertEqual(self.post(f'contracts/{pk}/sign', {'accepted': True}).status_code, 200)
        return pk

    def test_draft_publication_filters_and_archive(self):
        self.as_user(self.customer)
        data = dict(title='Draft mobile app', description='Build mobile app', category='development', skills=['React'],
                    budget_type='hourly', budget_min=1000, budget_max=2000, deadline='2099-01-01')
        result = self.post('projects', data)
        self.assertEqual(result.status_code, 201, result.data)
        pk = result.data['id']
        self.assertEqual(result.data['status'], 'draft')
        self.as_user(self.other)
        self.assertEqual(self.client.get(f'/api/projects/{pk}/').status_code, 404)
        self.assertEqual(self.post('proposals', {'project':pk,'cover_letter':'Ready','amount':1200,'delivery_days':2}).status_code,400)
        self.as_user(self.customer)
        self.assertEqual(self.post(f'projects/{pk}/publish').data['status'], 'published')
        self.assertEqual(self.client.get('/api/projects/?budget_type=hourly&min_budget=1500&skill=React').data['count'], 1)
        self.assertEqual(self.client.get('/api/projects/?min_budget=bad').status_code,400)
        self.assertEqual(self.client.delete(f'/api/projects/{pk}/').status_code, 204)
        self.assertEqual(Project.objects.get(pk=pk).status, 'cancelled')

    def test_funding_is_required_authorized_atomic_and_idempotent(self):
        pk = self.signed_contract()
        contract = Contract.objects.get(pk=pk)
        self.assertEqual(contract.status, 'awaiting_funding')
        self.assertEqual(self.post(f'contracts/{pk}/submit').status_code,400)
        self.assertEqual(self.post(f'contracts/{pk}/fund',{'confirmed':True}).status_code,403)
        self.as_user(self.customer)
        self.assertEqual(self.post(f'contracts/{pk}/fund',{'confirmed':True}).status_code,400)
        self.assertFalse(WalletEntry.objects.filter(contract=contract).exists())
        Profile.objects.filter(user=self.customer).update(balance=50000)
        for _ in range(2): self.assertEqual(self.post(f'contracts/{pk}/fund',{'confirmed':True}).status_code,200)
        contract.refresh_from_db()
        self.assertEqual(contract.escrow_amount,25000)
        self.assertEqual(contract.status,'active')
        self.assertIsNotNone(contract.deadline)
        self.assertEqual(WalletEntry.objects.filter(contract=contract,kind='escrow_hold').count(),1)
        self.assertEqual(Profile.objects.get(user=self.customer).balance,25000)
        self.assertEqual(Decimal(self.client.get('/api/wallet/').data['frozen_balance']),Decimal('25000'))

    @override_settings(PLATFORM_FEE_PERCENT='7.50')
    def test_acceptance_fee_snapshot_and_balanced_ledger(self):
        pk = self.work()
        self.as_user(self.customer)
        with override_settings(PLATFORM_FEE_PERCENT='99'):
            response = self.post(f'contracts/{pk}/accept',{'confirmed':True})
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(Profile.objects.get(user=self.freelancer).balance,Decimal('23125'))
        self.assertEqual(WalletEntry.objects.filter(contract_id=pk,kind='platform_fee').get().amount,Decimal('-1875'))
        self.assertEqual(Contract.objects.get(pk=pk).escrow_amount,0)
        self.assertEqual(self.post(f'contracts/{pk}/accept',{'confirmed':True}).status_code,200)
        self.assertEqual(WalletEntry.objects.filter(contract_id=pk,kind='escrow_release').count(),1)

    @override_settings(PLATFORM_FEE_PERCENT='5')
    def test_dispute_freezes_funds_and_admin_splits_once(self):
        pk = self.work()
        self.as_user(self.customer)
        self.assertEqual(self.post(f'contracts/{pk}/dispute',{'confirmed':True,'reason':'The result does not meet the scope'}).status_code,201)
        self.assertEqual(self.post(f'contracts/{pk}/accept',{'confirmed':True}).status_code,400)
        self.assertEqual(self.post(f'contracts/{pk}/revision',{'note':'Changes'}).status_code,400)
        dispute = Dispute.objects.get(contract_id=pk)
        self.assertEqual(self.post(f'disputes/{dispute.pk}/resolve',{'freelancer_amount':10000,'reason':'Partial work is usable'}).status_code,403)
        self.as_user(self.other)
        self.assertEqual(self.client.get(f'/api/disputes/{dispute.pk}/').status_code,404)
        self.other.is_staff=True;self.other.save(update_fields=['is_staff'])
        for amount in [-1,25001]: self.assertEqual(self.post(f'disputes/{dispute.pk}/resolve',{'freelancer_amount':amount,'reason':'Partial work is usable'}).status_code,400)
        result=self.post(f'disputes/{dispute.pk}/resolve',{'freelancer_amount':10000,'reason':'Partial work is usable'})
        self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(Profile.objects.get(user=self.customer).balance,40000)
        self.assertEqual(Profile.objects.get(user=self.freelancer).balance,9500)
        self.assertEqual(WalletEntry.objects.get(contract_id=pk,kind='platform_fee').amount,Decimal('-500'))
        self.assertEqual(self.post(f'disputes/{dispute.pk}/resolve',{'freelancer_amount':10000,'reason':'Partial work is usable'}).status_code,400)
        self.assertEqual(Contract.objects.get(pk=pk).escrow_amount,0)

    def test_full_refund_keeps_deliverable_locked(self):
        pk=self.work();self.as_user(self.freelancer)
        self.post(f'contracts/{pk}/dispute',{'confirmed':True,'reason':'Unable to complete the agreed scope'})
        dispute=Dispute.objects.get(contract_id=pk)
        self.other.is_staff=True;self.other.save(update_fields=['is_staff']);self.as_user(self.other)
        self.assertEqual(self.post(f'disputes/{dispute.pk}/resolve',{'freelancer_amount':0,'reason':'Full refund agreed after evidence review'}).status_code,200)
        self.as_user(self.customer)
        self.assertEqual(self.client.get(f'/api/contracts/{pk}/download/').status_code,403)
        self.assertEqual(Profile.objects.get(user=self.customer).balance,50000)

    def test_chat_attachment_and_notifications_are_private_and_immutable(self):
        pk=self.signed_contract()
        self.as_user(self.freelancer)
        result=self.client.post(f'/api/contracts/{pk}/messages/',{'text':'Question about scope','file':SimpleUploadedFile('notes.txt',b'private notes')},format='multipart')
        self.assertEqual(result.status_code,201,result.data)
        mid=result.data['id']
        self.assertEqual(self.client.patch(f'/api/contracts/{pk}/messages/',{'text':'rewrite'},format='json').status_code,405)
        self.as_user(self.other)
        self.assertEqual(self.client.get(f'/api/contracts/{pk}/messages/').status_code,404)
        self.assertEqual(self.client.get(f'/api/contracts/{pk}/messages/{mid}/download/').status_code,404)
        self.assertEqual(self.client.get('/api/notifications/').data['count'],0)
        self.as_user(self.customer)
        self.assertEqual(self.client.get('/api/dashboard/').data['unread_messages'],1)
        self.assertEqual(self.post(f'contracts/{pk}/messages/read').status_code,200)
        self.assertEqual(self.client.get('/api/dashboard/').data['unread_messages'],0)
        response=self.client.get(f'/api/contracts/{pk}/messages/{mid}/download/')
        self.assertEqual(b''.join(response.streaming_content),b'private notes')
        notification=self.client.get('/api/notifications/?unread=1').data['results'][0]
        self.assertEqual(self.post(f'notifications/{notification["id"]}/read').status_code,200)
        self.assertEqual(self.post('notifications/read-all').status_code,200)
        self.assertEqual(self.client.get('/api/notifications/?unread=1').data['count'],0)

    def test_reviews_only_after_completion_and_one_per_author(self):
        pk=self.work()
        self.assertEqual(self.post(f'contracts/{pk}/review',{'rating':5,'text':'Excellent work'}).status_code,400)
        self.as_user(self.customer);self.post(f'contracts/{pk}/accept',{'confirmed':True})
        self.assertEqual(self.post(f'contracts/{pk}/review',{'rating':6,'text':'Excellent work'}).status_code,400)
        self.assertEqual(self.post(f'contracts/{pk}/review',{'rating':5,'text':'Excellent work'}).status_code,201)
        self.assertEqual(self.post(f'contracts/{pk}/review',{'rating':1,'text':'Second review'}).status_code,400)
        self.as_user(self.freelancer)
        self.assertEqual(self.post(f'contracts/{pk}/review',{'rating':4,'text':'Clear requirements'}).status_code,201)
        self.as_user()
        result=self.client.get(f'/api/profiles/{self.freelancer.profile.pk}/')
        self.assertEqual(result.data['rating'],5)
        Review.objects.filter(target=self.freelancer).update(published=False,moderation_reason='Test moderation')
        self.assertIsNone(self.client.get(f'/api/profiles/{self.freelancer.profile.pk}/').data['rating'])

    def test_role_switch_retains_directory_and_obligations(self):
        pk=self.signed_contract();self.as_user(self.freelancer)
        self.post('auth/role',{'role':'freelancer'});self.post('auth/role',{'role':'client'})
        self.assertEqual(self.client.get(f'/api/contracts/{pk}/').status_code,200)
        self.assertEqual(self.client.get(f'/api/profiles/{self.freelancer.profile.pk}/').status_code,200)
        self.assertEqual(set(Profile.objects.get(user=self.freelancer).enabled_roles),{'client','freelancer'})

    def test_cancel_before_funding_and_withdraw_proposal(self):
        pid=self.proposal();self.as_user(self.freelancer)
        self.assertEqual(self.post(f'proposals/{pid}/withdraw').data['status'],'withdrawn')
        self.as_user(self.customer);self.assertEqual(self.post(f'proposals/{pid}/accept').status_code,400)
        from .models import Proposal
        Proposal.objects.filter(pk=pid).update(status='pending')
        response=self.post(f'proposals/{pid}/accept');pk=response.data['id']
        self.assertEqual(self.post(f'contracts/{pk}/cancel',{'confirmed':True}).data['status'],'cancelled')
        self.assertEqual(Contract.objects.count(),1)

    def test_change_password_and_uppercase_only_rejected(self):
        self.as_user(self.freelancer)
        data={'current_password':'Secure-2026-pass','password':'UPPERCASE123!','password_confirm':'UPPERCASE123!'}
        self.assertEqual(self.post('auth/change-password',data).status_code,400)
        data.update(password='New-Secure-2028',password_confirm='New-Secure-2028')
        result=self.post('auth/change-password',data)
        self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(self.client.get('/api/auth/me/').status_code,401)
