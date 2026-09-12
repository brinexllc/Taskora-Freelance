import io
import json
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError as ModelValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import override_settings
from rest_framework.exceptions import ValidationError

from .tests import BaseTests
from .fees import check_fee_configuration, current_policy, fee_rate, settlement
from .escrow import distribute, fund_contract, resolve_dispute
from .models import AuditLog, Category, CategorySkill, Contract, Dispute, PlatformFee, Profile, Project, Proposal, Skill, SkillAlias, WalletEntry
from .taxonomy import merge_skills


FAST_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class CommissionTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.customer = self.account('fee_customer', 'client')
        self.worker = self.account('fee_worker', 'freelancer')
        self.admin = self.account('fee_admin', 'client')
        self.admin.is_staff = True
        self.admin.save(update_fields=['is_staff'])

    def offer(self, amount='1000000.00'):
        project = Project.objects.create(category=Category.objects.get(slug='development'), owner=self.customer,
            title='Commission test', description='Agreed scope', client_name='Customer', budget_min=amount, budget_max=amount,
            acceptance_criteria='All documented cases pass', demonstration_method='Private staging demonstration', test_scenario='Run agreed request cases')
        return Proposal.objects.create(project=project, freelancer=self.worker, freelancer_name='Worker', freelancer_email=self.worker.email,
            cover_letter='Agreed scope', amount=amount, delivery_days=5)

    def contract(self, rate='5', amount='1000000.00', funded=True):
        offer = self.offer(amount)
        self.as_user(self.customer)
        with override_settings(PLATFORM_FEE_PERCENT=rate):
            result = self.post(f'proposals/{offer.pk}/accept')
        self.assertEqual(result.status_code, 201, result.data)
        contract = Contract.objects.get(pk=result.data['id'])
        if funded:
            contract.status = 'awaiting_funding'
            contract.save(update_fields=['status'])
            Profile.objects.filter(user=self.customer).update(balance=Decimal(amount))
            with transaction.atomic():
                fund_contract(contract, self.customer)
        return contract

    def command(self, name, *args):
        out = io.StringIO()
        call_command(name, *args, stdout=out)
        return json.loads(out.getvalue())

    @override_settings(PLATFORM_FEE_PERCENT='5')
    def test_approved_five_percent_is_paid_only_by_freelancer(self):
        policy = self.client.get('/api/platform-fees/').data
        self.assertEqual(policy['freelancer_fee_percent'], '5.00')
        self.assertEqual(policy['customer_fee_percent'], '0.00')
        c = self.contract('5', amount='15000000', funded=False)
        self.assertEqual(c.fee_amount, Decimal('750000'))
        self.assertEqual(c.amount - c.fee_amount, Decimal('14250000'))

    def test_contract_search_remains_private_and_filters_participant(self):
        c = self.contract(funded=False)
        self.as_user(self.customer)
        result = self.client.get('/api/contracts/', {'participant_profile': self.worker.profile.pk, 'search': 'Commission'})
        self.assertEqual([item['id'] for item in result.data['results']], [c.pk])
        self.assertEqual(self.client.get('/api/contracts/', {'search': 'Missing title'}).data['count'], 0)
        outsider = self.account('search_outsider', 'freelancer')
        self.assertEqual(self.client.get('/api/contracts/', {'participant_profile': outsider.profile.pk}).data['count'], 0)
        self.as_user(outsider)
        self.assertEqual(self.client.get('/api/contracts/', {'participant_profile': self.worker.profile.pk}).data['count'], 0)

    @override_settings(PLATFORM_FEE_PERCENT='5')
    def test_dashboard_reports_actual_gross_spend_and_net_earnings(self):
        c = self.contract(amount='15000000')
        distribute(c, self.customer, Decimal('15000000'), 'Проверка фактического отчёта')
        self.as_user(self.worker)
        self.assertEqual(Decimal(self.client.get('/api/dashboard/').data['total_earned']), Decimal('14250000'))
        self.as_user(self.customer)
        self.assertEqual(Decimal(self.client.get('/api/dashboard/').data['total_spent']), Decimal('15000000'))

    @override_settings(PLATFORM_FEE_PERCENT='5')
    def test_explicit_fee_revision_preserves_history_and_requires_new_version_consent(self):
        from .contract_revisions import revise_unfunded_fee
        from django.utils import timezone
        c = self.contract('0', amount='15000000', funded=False)
        c.customer_signed_at = c.freelancer_signed_at = timezone.now()
        c.status = Contract.Status.AWAITING_FUNDING
        c.save()
        old_terms = c.terms
        self.admin.is_superuser = True
        self.admin.save(update_fields=['is_superuser'])
        c = revise_unfunded_fee(c.pk, self.admin, reason='Исправление ошибочного нулевого тарифа',
                               expected_version=1, expected_policy=current_policy()['policy_version'], request=self.operator_request(self.admin))
        self.assertEqual(c.version, 2)
        self.assertIsNone(c.customer_signed_at)
        self.assertIsNone(c.freelancer_signed_at)
        self.assertEqual(c.status, 'draft')
        self.assertEqual(c.fee_amount, Decimal('750000'))
        self.assertEqual(c.events.get(kind='fee_revised').data['previous']['terms'], old_terms)
        self.assertEqual(c.events.get(kind='fee_revised').data['previous']['fee_percent'], '0.00')
        self.assertFalse(c.transactions.exists())
        self.assertFalse(PlatformFee.objects.filter(contract=c).exists())
        self.as_user(self.customer)
        for body in [{'accepted': True}, {'accepted': True, 'expected_version': 1}]:
            self.assertEqual(self.post(f'contracts/{c.pk}/sign', body).status_code, 400)
        self.assertEqual(self.post(f'contracts/{c.pk}/sign', {'accepted': True, 'expected_version': 2}).status_code, 200)
        self.as_user(self.worker)
        self.assertEqual(self.post(f'contracts/{c.pk}/sign', {'accepted': True, 'expected_version': 2}).status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.status, Contract.Status.AWAITING_FUNDING)

    @override_settings(PLATFORM_FEE_PERCENT='5')
    def test_fee_revision_rejects_unauthorized_and_funded_contracts(self):
        from .contract_revisions import revise_unfunded_fee
        from rest_framework.exceptions import PermissionDenied
        c = self.contract('0', funded=True)
        args = dict(reason='Исправление ошибочного нулевого тарифа', expected_version=1,
                    expected_policy=current_policy()['policy_version'])
        with self.assertRaises(PermissionDenied):
            revise_unfunded_fee(c.pk, self.customer, **args)
        self.admin.is_superuser = True
        self.admin.save(update_fields=['is_superuser'])
        with self.assertRaises(ValidationError):
            revise_unfunded_fee(c.pk, self.admin, **args, request=self.operator_request(self.admin))
        self.as_operator(self.admin)
        result = self.client.get(f'/admin/marketplace/contract/{c.pk}/revise-fee/')
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, 'Комиссию можно исправить только до резервирования')
        self.assertNotContains(result, 'value="Исправить комиссию и запросить подтверждения"')

    @override_settings(PLATFORM_FEE_PERCENT='5')
    def test_admin_fee_revision_requires_confirmation_and_rejects_repeat(self):
        c = self.contract('0', amount='15000000', funded=False)
        self.admin.is_superuser = True
        self.admin.save(update_fields=['is_superuser'])
        self.as_operator(self.admin)
        url = f'/admin/marketplace/contract/{c.pk}/revise-fee/'
        preview = self.client.get(url)
        self.assertContains(preview, '750000')
        payload = {'version':1,'policy':current_policy()['policy_version'],'reason':'Исправление ошибочного нулевого тарифа'}
        self.assertEqual(self.client.post(url, payload).status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.version, 1)
        payload['confirmed'] = 'on'
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        c.refresh_from_db()
        self.assertEqual(c.version, 2)
        self.assertEqual(c.fee_amount, Decimal('750000'))
        self.assertEqual(self.client.post(url, payload).status_code, 200)
        self.assertEqual(c.events.filter(kind='fee_revised').count(), 1)

    def test_rate_snapshots_zero_five_eight_and_no_automatic_signing(self):
        for rate, fee in [('0','0.00'),('5','50000.00'),('8','80000.00')]:
            c = self.contract(rate, funded=False)
            self.assertEqual(str(c.fee_amount), fee)
            self.assertIsNone(c.customer_signed_at)
            self.assertIsNone(c.freelancer_signed_at)
            with override_settings(PLATFORM_FEE_PERCENT='99'):
                c.refresh_from_db()
                self.assertEqual(c.fee_percent, Decimal(rate))
                self.assertEqual(c.fee_policy_snapshot['freelancer_fee_percent'], f'{Decimal(rate):.2f}')

    def test_changed_policy_and_client_amount_tampering(self):
        offer = self.offer()
        self.as_user(self.customer)
        with override_settings(PLATFORM_FEE_PERCENT='8'):
            result = self.post(f'proposals/{offer.pk}/accept', {'expected_fee_policy_version':'commission-v1:5.00'})
            self.assertEqual(result.status_code,409)
            self.assertEqual(result.data['code'],'FEE_POLICY_CHANGED')
            self.assertFalse(Contract.objects.exists())
            offer.refresh_from_db()
            self.assertEqual(offer.status,'pending')
            result = self.post(f'proposals/{offer.pk}/accept', {'expected_fee_policy_version':'commission-v1:8.00','fee_percent':'0','fee_amount':'0','amount':'1'})
            self.assertEqual(result.status_code,201,result.data)
            self.assertEqual(result.data['fee_amount'],'80000.00')
            self.assertEqual(result.data['amount'],'1000000.00')

    def test_decimal_boundaries_and_half_up(self):
        for rate in ['NaN','Infinity','-1','100.01','5.001','0.000',0.05,True,'5%']:
            with self.subTest(rate=rate), self.assertRaises(ValidationError):
                fee_rate(rate)
        self.assertEqual(settlement('0.10','0.10','5')['fee'],Decimal('0.01'))
        for gross in ['-1','1000000.01','NaN','Infinity','0.001',0.1]:
            with self.subTest(gross=gross), self.assertRaises(ValidationError):
                settlement('1000000',gross,'5')
        for rate in ['0','5','8','100']:
            self.assertEqual(fee_rate(rate),Decimal(rate))
        with override_settings(PLATFORM_FEE_PERCENT='5.001'):
            self.assertEqual(check_fee_configuration(None)[0].id,'marketplace.E001')

    def test_final_distribution_examples_and_immutable_plan(self):
        for rate,gross,fee,net,refund in [
            ('5','1000000','50000','950000','0'),('8','1000000','80000','920000','0'),
            ('5','500000','25000','475000','500000'),('8','500000','40000','460000','500000'),
            ('5','0','0','0','1000000'),('0','1000000','0','1000000','0')]:
            with self.subTest(rate=rate,gross=gross):
                c=self.contract(rate)
                plan=c.fee_amount; terms=c.terms
                previous=Profile.objects.get(user=self.worker).balance
                with override_settings(PLATFORM_FEE_PERCENT='99'):
                    distribute(c,self.admin,Decimal(gross),'Final award')
                self.assertEqual(c.fee_amount,plan)
                self.assertEqual(c.terms,terms)
                self.assertEqual(c.actual_fee_amount,Decimal(fee))
                ledger=PlatformFee.objects.get(contract=c)
                self.assertEqual(ledger.fee_amount,Decimal(fee))
                self.assertEqual(ledger.gross_amount,Decimal(gross))
                self.assertEqual(Profile.objects.get(user=self.worker).balance-previous,Decimal(net))
                self.assertEqual(Profile.objects.get(user=self.customer).balance,Decimal(refund))
                result=self.client.get(f'/api/contracts/{c.pk}/').data
                self.assertEqual(Decimal(result['actual_net_amount']),Decimal(net))
                self.assertEqual(c.amount,c.refunded_amount+Decimal(result['actual_net_amount'])+c.actual_fee_amount)
                with self.assertRaises(ValidationError):
                    distribute(c,self.admin,Decimal(gross),'Repeat')
                self.assertEqual(PlatformFee.objects.filter(contract=c).count(),1)
                with transaction.atomic(), self.assertRaises(IntegrityError):
                    PlatformFee.objects.create(contract=c,gross_amount=0,fee_percent=5,fee_amount=0)

    def test_mid_settlement_exception_rolls_back_everything(self):
        c=self.contract()
        with patch('marketplace.escrow.PlatformFee.objects.create',side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                distribute(c,self.admin,Decimal('500000'),'Final award')
        c.refresh_from_db()
        self.assertEqual(c.escrow_amount,c.amount)
        self.assertIsNone(c.actual_fee_amount)
        self.assertEqual(Profile.objects.get(user=self.worker).balance,0)
        self.assertEqual(Profile.objects.get(user=self.customer).balance,0)
        self.assertEqual(WalletEntry.objects.filter(contract=c).count(),1)
        self.assertFalse(c.events.filter(kind='settled').exists())

    def test_dispute_and_cancel_do_not_earn_fees_before_final_resolution(self):
        c=self.contract()
        c.status='disputed';c.save(update_fields=['status'])
        dispute=Dispute.objects.create(contract=c,opened_by=self.customer,reason='Work needs review')
        self.assertFalse(PlatformFee.objects.exists())
        resolve_dispute(dispute.pk,self.admin,Decimal('500000'),'Award for usable work',request=self.operator_request(self.admin))
        c.refresh_from_db()
        self.assertEqual(c.actual_fee_amount,Decimal('25000'))
        with self.assertRaises(ValidationError):
            resolve_dispute(dispute.pk,self.admin,Decimal('500000'),'Repeat resolution',request=self.operator_request(self.admin))
        unfunded=self.contract(funded=False)
        self.assertEqual(self.post(f'contracts/{unfunded.pk}/cancel',{'confirmed':True}).status_code,200)
        self.assertFalse(PlatformFee.objects.filter(contract=unfunded).exists())

    def test_admin_requires_confirmation_of_the_exact_dispute_preview(self):
        from django.forms import modelform_factory
        from .admin import DisputeForm
        c=self.contract();c.status='disputed';c.save(update_fields=['status'])
        dispute=Dispute.objects.create(contract=c,opened_by=self.customer,reason='Review the delivery')
        Form=modelform_factory(Dispute,form=DisputeForm,fields=['status','resolution','freelancer_amount','settlement_preview','confirm_settlement'])
        data={'status':'resolved','resolution':'Award for completed half','freelancer_amount':'500000'}
        preview=Form(data=data,instance=dispute)
        self.assertFalse(preview.is_valid())
        self.assertIn('25000.00',str(preview.errors))
        self.assertIn('475000.00',str(preview.errors))
        confirmed={**data,'confirm_settlement':True,'settlement_preview':preview.data['settlement_preview']}
        self.assertTrue(Form(data=confirmed,instance=dispute).is_valid())
        self.assertFalse(Form(data={**confirmed,'freelancer_amount':'600000'},instance=dispute).is_valid())
        self.assertFalse(PlatformFee.objects.exists())

    def test_backfill_requires_evidence_is_idempotent_and_never_changes_balance(self):
        c=self.contract();distribute(c,self.admin,Decimal('500000'),'Legacy award')
        PlatformFee.objects.filter(contract=c).delete()
        Contract.objects.filter(pk=c.pk).update(actual_fee_amount=None)
        balances=list(Profile.objects.order_by('pk').values_list('balance',flat=True))
        self.assertEqual(self.command('backfill_platform_fees','--dry-run')['restored'],[c.pk])
        self.assertFalse(PlatformFee.objects.exists())
        self.assertEqual(self.command('backfill_platform_fees','--apply')['restored'],[c.pk])
        self.assertEqual(self.command('backfill_platform_fees','--apply')['restored'],[])
        self.assertEqual(PlatformFee.objects.get(contract=c).source,'backfill')
        self.assertEqual(list(Profile.objects.order_by('pk').values_list('balance',flat=True)),balances)
        bad=self.contract();distribute(bad,self.admin,Decimal('1000000'),'Legacy award')
        PlatformFee.objects.filter(contract=bad).delete()
        Contract.objects.filter(pk=bad.pk).update(actual_fee_amount=None)
        WalletEntry.objects.filter(contract=bad,kind='platform_fee').delete()
        report=self.command('backfill_platform_fees','--apply')
        self.assertEqual(report['review'][0]['contract'],bad.pk)
        bad.refresh_from_db();self.assertIsNone(bad.actual_fee_amount)


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class CatalogTests(BaseTests):
    def seed(self,*args):
        out=io.StringIO();call_command('seed_catalog',*args,stdout=out);return json.loads(out.getvalue())

    def test_seed_exact_counts_and_preserves_manual_changes(self):
        before=Skill.objects.count()
        self.seed('--dry-run');self.assertEqual(Skill.objects.count(),before)
        self.seed('--apply')
        self.assertEqual(Category.objects.filter(active=True).count(),8)
        self.assertEqual(Skill.objects.filter(merged_into__isnull=True).count(),89)
        skill=Skill.objects.get(name='React');skill.active=False;skill.labels={'ru':'Реакт вручную'};skill.save()
        category=Category.objects.get(slug='development');category.name='Мой каталог';category.active=False;category.save()
        self.seed('--apply');skill.refresh_from_db();category.refresh_from_db()
        self.assertFalse(skill.active);self.assertEqual(skill.labels,{'ru':'Реакт вручную'})
        self.assertFalse(category.active);self.assertEqual(category.name,'Мой каталог')
        self.assertEqual(Profile.objects.count(),0)

    def test_explicit_alias_merge_preserves_relations_ids_and_verified_history(self):
        source=Skill.objects.create(name='ReactJS');native=Skill.objects.create(name='React Native')
        user=self.account('merge_worker','freelancer');user.profile.skills.add(source,native)
        user.profile.verified_skills=['ReactJS'];user.profile.save(update_fields=['verified_skills'])
        self.seed('--apply')
        target=Skill.objects.get(name='React');source.refresh_from_db()
        self.assertFalse(source.active);self.assertEqual(source.merged_into_id,target.pk)
        self.assertCountEqual(user.profile.skills.values_list('name',flat=True),['React','React Native'])
        user.profile.refresh_from_db();self.assertEqual(user.profile.verified_skills,['ReactJS'])
        self.assertEqual(SkillAlias.objects.get(key='reactjs').skill_id,target.pk)
        self.as_user(user)
        response=self.client.patch('/api/auth/me/',{'skill_ids':[target.pk,native.pk]},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['profile']['verified_skills'],['ReactJS'])

    def test_normalized_alias_collisions_and_stable_slug(self):
        self.seed('--apply');react=Skill.objects.get(name='React');node=Skill.objects.get(name='Node.js')
        with self.assertRaises(ModelValidationError): Skill.objects.create(name='  ＲＥＡＣＴ  ')
        with self.assertRaises(ModelValidationError): SkillAlias.objects.create(skill=node,key='  ReactJS ')
        with self.assertRaises(ModelValidationError): SkillAlias.objects.create(skill=node,key='React')
        old_slug=react.slug;react.name='React renamed';react.save();self.assertEqual(react.slug,old_slug)
        react.slug='new-slug'
        with self.assertRaises(ModelValidationError): react.save()
        self.assertEqual(Skill.objects.get(name='C#').slug,'csharp')
        cyrillic=Skill.objects.create(name='Настройка серверов')
        cyrillic.labels={'ru':'Настройка серверов'};cyrillic.save()
        self.assertEqual(cyrillic.slug,'настройка-серверов')

    def test_structured_search_languages_aliases_pagination_and_legacy(self):
        self.seed('--apply')
        self.assertIsInstance(self.client.get('/api/directory/').data['skills'][0],str)
        catalog=self.client.get('/api/catalog/',{'lang':'en'}).data
        self.assertEqual(catalog['categories'][-1]['slug'],'other')
        for query,name in [('  ＲＥＡＣＴＪＳ ','React'),('CSharp','C#'),('ручное тестирование','Manual Testing'),('Qo‘lda sinash','Manual Testing')]:
            response=self.client.get('/api/skills/',{'search':query})
            self.assertEqual(response.status_code,200,response.data)
            self.assertEqual(response.data['results'][0]['name'],name)
        for lang in ['ru','uz','uz-cyrl','en']:
            self.assertEqual(self.client.get('/api/skills/',{'lang':lang,'page_size':7}).data['count'],89)
        self.assertEqual(self.client.get('/api/skills/',{'search':'not found xyz'}).data['count'],0)
        self.assertEqual(self.client.get('/api/skills/',{'category':'missing'}).status_code,400)
        self.assertEqual(self.client.get('/api/skills/',{'lang':'xx'}).status_code,400)
        self.assertEqual(self.client.post('/api/skills/',{'name':'Fake'}).status_code,405)
        python=Skill.objects.get(name='Python')
        self.assertCountEqual(python.categories.values_list('slug',flat=True),['development','automation','qa-support'])

    def test_drafts_publication_patch_names_ids_inactive_and_filter_semantics(self):
        self.seed('--apply');user=self.account('catalog_customer','client');self.as_user(user)
        react=Skill.objects.get(name='React');django=Skill.objects.get(name='Django')
        payload={'title':'Catalog project','description':'Work','category':'automation','budget_min':'100','budget_max':'200','deadline':'2099-01-01'}
        draft=self.post('projects',payload);self.assertEqual(draft.status_code,201,draft.data)
        pk=draft.data['id'];url=f'/api/projects/{pk}/'
        self.assertEqual(self.post(f'projects/{pk}/publish').status_code,400)
        self.assertEqual(self.client.patch(url,{'skills_unspecified':True},format='json').status_code,200)
        self.assertEqual(self.post(f'projects/{pk}/publish').status_code,200)
        self.assertEqual(self.client.patch(url,{'title':'Only title'},format='json').data['skills_unspecified'],True)
        self.assertEqual(self.client.patch(url,{'skill_ids':[react.pk]},format='json').status_code,400)
        selected=self.client.patch(url,{'skills_unspecified':False,'skill_ids':[react.pk],'skills':['ReactJS']},format='json')
        self.assertEqual(selected.status_code,200,selected.data)
        self.assertEqual(selected.data['skills'],['React'])
        self.assertEqual(self.client.patch(url,{'skill_ids':[react.pk],'skills':['Django']},format='json').status_code,400)
        react.active=False;react.save()
        self.assertEqual(self.client.patch(url,{'title':'Preserve inactive'},format='json').status_code,200)
        self.assertEqual(self.client.patch(url,{'skill_ids':[react.pk]},format='json').status_code,200)
        self.assertEqual(self.post('projects',{**payload,'skill_ids':[react.pk]}).status_code,400)
        self.assertEqual(self.client.get(f'/api/projects/?skill_id={react.pk}&skill_id={django.pk}').data['count'],0)
        self.assertEqual(self.client.get(f'/api/projects/?skill_id={react.pk}&skill_id={django.pk}&skill_match=any').data['count'],1)
        self.assertEqual(self.client.get('/api/projects/?skill_id=9999999').status_code,400)
        self.assertEqual(self.client.get('/api/projects/?skill=ReactJS').data['count'],1)
        self.assertEqual(self.client.get('/api/projects/?skill_match=invalid').status_code,400)
