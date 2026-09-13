"""Acceptance at the HTML boundary: real models, page routes and form constraints."""
import uuid
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from .security_test_helpers import authenticate_client
from .models import Profile, Category, Project, Contract, Dispute, Skill, Proposal, Review, WalletEntry
from .admin_control.query import RESOURCES, NAV, filtered_queryset


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AdminPanelUITests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user('panel-owner','owner@example.test','Testing-Password!52',is_staff=True,is_superuser=True)
        self.customer=get_user_model().objects.create_user('panel-customer','customer@example.test','Testing-Password!52')
        self.worker=get_user_model().objects.create_user('panel-worker','worker@example.test','Testing-Password!52')
        for user in (self.owner,self.customer,self.worker):Profile.objects.get_or_create(user=user,defaults={'full_name':user.username,'enabled_roles':['client','freelancer']})
        self.category=Category.objects.create(name='Проверка интерфейса',slug='ui-tests')
        self.project=Project.objects.create(owner=self.customer,title='Реальный тестовый заказ',description='Описание заказа',category=self.category,budget_min=100,budget_max=500,client_name='Заказчик')
        self.proposal=Proposal.objects.create(project=self.project,freelancer=self.worker,freelancer_name='Исполнитель',freelancer_email=self.worker.email,cover_letter='Готов выполнить',amount=500,delivery_days=7)
        self.contract=Contract.objects.create(project=self.project,proposal=self.proposal,customer=self.customer,freelancer=self.worker,amount=500,delivery_days=7,terms='Условия тестового договора',status='active')
        self.client=APIClient();authenticate_client(self.client,self.owner,operator_confirmed=True)

    def test_all_navigation_and_resource_lists_render(self):
        for _,_,_,url in NAV:
            with self.subTest(url=url):
                response=self.client.get(url)
                self.assertEqual(response.status_code,200,response.content[:1000])
        for resource in RESOURCES:
            with self.subTest(resource=resource):
                response=self.client.get(f'/admin/control/{resource}/')
                self.assertEqual(response.status_code,200,response.content[:1000])

    def test_real_cards_and_allowed_action_forms_render(self):
        routes=[f'users/{self.customer.pk}',f'projects/{self.project.pk}',f'contracts/{self.contract.pk}',f'wallets/{self.customer.profile.pk}',f'categories/{self.category.pk}',f'conversations/{self.contract.pk}']
        routes += [f'users/{self.customer.pk}/action/{action}' for action in ['user.edit','user.block','user.revoke_sessions']]
        routes += [f'projects/{self.project.pk}/action/{action}' for action in ['project.edit','project.moderate']]
        routes += [f'contracts/{self.contract.pk}/action/contract.amend']
        for route in routes:
            with self.subTest(route=route):
                response=self.client.get('/admin/control/'+route+'/')
                self.assertEqual(response.status_code,200,response.content[:1000])

    def test_all_create_forms_and_search_render(self):
        for kind in ['content','setting','announcement','job','export','category','skill','alias','categoryskill']:
            with self.subTest(kind=kind):
                response=self.client.get(f'/admin/control/new/{kind}/')
                self.assertEqual(response.status_code,200,response.content[:1000])
        response=self.client.get('/admin/control/search/',{'q':'panel-customer'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'panel-customer')

    def test_linked_project_filters_and_retained_role(self):
        other=Project.objects.create(owner=self.worker,title='Другой заказ',description='Описание',category=self.category,budget_min=100,budget_max=200,client_name='Другой')
        proposal=Proposal.objects.create(project=other,freelancer=self.customer,freelancer_name='Исполнитель',freelancer_email=self.customer.email,cover_letter='Отклик',amount=100,delivery_days=7)
        other_contract=Contract.objects.create(project=other,proposal=proposal,customer=self.worker,freelancer=self.customer,amount=100,delivery_days=7,terms='Условия')
        self.assertEqual(list(filtered_queryset('contracts',{'project':str(self.project.pk)}).values_list('pk',flat=True)),[self.contract.pk])
        self.assertTrue(filtered_queryset('users',{'role':'freelancer'}).filter(pk=self.customer.pk).exists())

    def test_guest_login_has_no_panel_data(self):
        self.client.logout()
        response=self.client.get('/admin/login/')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Вход администратора')
        self.assertNotContains(response,'Реальный тестовый заказ')

    def test_invalid_dates_and_action_mismatch_are_safe(self):
        response=self.client.get('/admin/',{'start':'2026-02-31'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.get(f'/admin/control/users/{self.customer.pk}/action/dispute.preview/').status_code,404)
        self.assertEqual(self.client.get('/admin/control/users/invalid-id/').status_code,404)
        self.assertEqual(self.client.get('/admin/control/jobs/invalid-uuid/').status_code,404)

    def test_masked_contacts_and_disclosure_gate(self):
        response=self.client.get('/admin/control/users/')
        self.assertNotContains(response,'customer@example.test')
        from .models import Message
        message=Message.objects.create(contract=self.contract,sender=self.customer,text='PRIVATE-MATERIAL-TEST')
        response=self.client.get(f'/admin/control/conversations/{self.contract.pk}/')
        self.assertNotContains(response,message.text)
        self.assertContains(response,'Просмотреть для модерации')

    def test_csrf_required_for_admin_mutations(self):
        client=APIClient(enforce_csrf_checks=True);authenticate_client(client,self.owner,operator_confirmed=True)
        response=client.post(f'/admin/control/users/{self.customer.pk}/action/user.block/',{'reason':'Обоснование проверки','confirmed':'on','idempotency_key':str(uuid.uuid4())})
        self.assertEqual(response.status_code,403)
        self.customer.refresh_from_db();self.assertTrue(self.customer.is_active)

    def test_counts_and_completion_period_are_based_on_the_matching_objects(self):
        from django.utils import timezone
        from datetime import timedelta
        from .admin_control.query import base_queryset
        Dispute.objects.create(contract=self.contract,opened_by=self.customer,reason='Проверка счётчиков',status='opened')
        row=base_queryset('users').get(pk=self.customer.pk)
        self.assertEqual((row.active_contracts,row.open_disputes),(1,1))
        Contract.objects.filter(pk=self.contract.pk).update(status='completed',created_at=timezone.now()-timedelta(days=90),completed_at=timezone.now())
        params={'status':'completed','date_basis':'completed_at','start':timezone.localdate().isoformat()}
        self.assertEqual(list(filtered_queryset('contracts',params).values_list('pk',flat=True)),[self.contract.pk])

    def test_delivery_demo_link_is_private_and_list_return_is_preserved(self):
        from .models import Deliverable
        row=Deliverable.objects.create(contract=self.contract,filename='test.zip',preview_text='PRIVATE-RESULT',demo_url='https://example.test/private-material')
        response=self.client.get(f'/admin/control/deliverables/{row.pk}/')
        self.assertNotContains(response,row.demo_url)
        self.assertNotContains(response,row.preview_text)
        response=self.client.get(f'/admin/control/users/{self.customer.pk}/',{'return':'/admin/control/users/?q=panel&page=2&size=25'})
        self.assertContains(response,'/admin/control/users/?q=panel&amp;page=2&amp;size=25')
        response=self.client.get('/admin/control/projects/',{'budget_min':'NaN'})
        self.assertEqual(response.status_code,400)
