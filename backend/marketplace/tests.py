from .models import Category
import hashlib
import re
import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import Contract, PasswordResetCode, Payment, Profile, Project, Proposal, WalletEntry, Withdrawal
from .services import process_withdrawal

User = get_user_model()


class BaseTests(APITestCase):
    def setUp(self):
        cache.clear()
    def account(self, username, role):
        user = User.objects.create_user(username=username, email=f'{username}@example.com', password='Secure-2026-pass', first_name=username, last_name='Tester')
        Profile.objects.create(user=user, full_name=f'{username} Tester', role=role, birth_date=date(2000,1,1), has_passport=True)
        return user
    def as_user(self, user=None):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.get_or_create(user=user)[0].key}' if user else '')
    def post(self, path, data=None):
        return self.client.post('/api/' + path + '/', data or {}, format='json')


class AuthenticationTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.form = dict(first_name='Aziz', last_name='Rahimov', username='aziz_01', birth_date='2000-06-01', phone='+998901234567', accept_terms=True, email='aziz@example.com', password='Secure-2026-pass', password_confirm='Secure-2026-pass')
    def test_registration_requires_all_spec_fields(self):
        for field in ['first_name','last_name','username','birth_date','phone','email','accept_terms','password','password_confirm']:
            with self.subTest(field=field):
                data = dict(self.form); del data[field]
                self.assertEqual(self.post('auth/register', data).status_code, 400)
        self.assertEqual(User.objects.count(), 0)
    def test_register_choose_role_three_login_identifiers_logout(self):
        response = self.post('auth/register', self.form)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['user']['role'], '')
        user = User.objects.get(username='aziz_01')
        self.as_user(user)
        self.assertEqual(self.post('projects', dict(title='Test',description='Work',category='development',skills=['React'],deadline='2099-01-01',budget_min=1000,budget_max=2000)).status_code, 403)
        self.assertEqual(self.post('auth/role', {'role':'freelancer'}).data['role'], 'freelancer')
        for identifier in [self.form['phone'],self.form['email'],self.form['username'].upper()]:
            self.as_user()
            result = self.post('auth/login', {'identifier':identifier,'password':self.form['password']})
            self.assertEqual(result.status_code, 200, result.data)
        self.as_user(user)
        self.assertEqual(self.post('auth/logout').status_code,204)
        self.assertEqual(self.client.get('/api/auth/me/').status_code,401)
    def test_rejects_invalid_details_and_duplicate_identity(self):
        for changes in [{'phone':'+79012345678'},{'phone':'+9981234567890'},{'accept_terms':False},{'username':'two users'},{'password':'weakpass','password_confirm':'weakpass'},{'password':'lowercase1!','password_confirm':'lowercase1!'},{'password':'NoDigitHere!','password_confirm':'NoDigitHere!'},{'password':'NoSymbol123','password_confirm':'NoSymbol123'}]:
            self.assertEqual(self.post('auth/register',{**self.form,**changes}).status_code,400)
        self.assertEqual(self.post('auth/register', self.form).status_code,201)
        duplicate = {**self.form,'username':'AZIZ_01','email':'other@example.com','phone':'+998991234567'}
        self.assertEqual(self.post('auth/register',duplicate).status_code,400)
    @patch('marketplace.validation.timezone.localdate', return_value=date(2026,9,6))
    def test_age_boundaries(self, _):
        from .validation import birth_date
        from rest_framework.exceptions import ValidationError
        for value in [date(2010,9,6),date(1960,9,7),date(1961,9,6)]:
            self.assertEqual(birth_date(value),value)
        for value in [date(2010,9,7),date(1960,9,6),date(2030,1,1)]:
            with self.assertRaises(ValidationError): birth_date(value)
    def test_reset_single_use_and_revokes_old_token(self):
        self.post('auth/register',self.form)
        user = User.objects.get(username=self.form['username'])
        old_token = Token.objects.get(user=user).key
        response = self.post('auth/password-reset/request', {'identifier':self.form['email']})
        self.assertEqual(response.status_code,200,response.data)
        code = re.search(r'\b(\d{6})\b',mail.outbox[0].body).group(1)
        verify = self.post('auth/password-reset/verify',{'identifier':self.form['email'],'code':code})
        self.assertEqual(verify.status_code,200,verify.data)
        payload = {'identifier':self.form['email'],'reset_token':verify.data['reset_token'],'password':'New-Secure-2027','password_confirm':'New-Secure-2027'}
        self.assertEqual(self.post('auth/password-reset/confirm',payload).status_code,200)
        self.assertFalse(Token.objects.filter(key=old_token).exists())
        self.assertEqual(self.post('auth/password-reset/confirm',payload).status_code,400)
    def test_reset_attempts_expiry_and_unconfigured_sms(self):
        self.post('auth/register',self.form)
        self.assertEqual(self.post('auth/password-reset/request',{'identifier':self.form['phone']}).status_code,503)
        self.post('auth/password-reset/request',{'identifier':self.form['email']})
        reset = PasswordResetCode.objects.first()
        code = re.search(r'\b(\d{6})\b',mail.outbox[0].body).group(1)
        wrong = '111111' if code != '111111' else '222222'
        for _ in range(5): self.assertEqual(self.post('auth/password-reset/verify',{'identifier':self.form['email'],'code':wrong}).status_code,400)
        self.assertEqual(self.post('auth/password-reset/verify',{'identifier':self.form['email'],'code':code}).status_code,400)
        reset.refresh_from_db(); self.assertEqual(reset.attempts,5)
        reset.attempts=0; reset.expires_at=timezone.now()-timedelta(seconds=1); reset.save()
        self.assertEqual(self.post('auth/password-reset/verify',{'identifier':self.form['email'],'code':code}).status_code,400)


class MarketplaceTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.customer=self.account('customer','client')
        self.freelancer=self.account('freelancer','freelancer')
        self.other=self.account('other','freelancer')
        self.project=Project.objects.create(category=Category.objects.get(slug='other'),owner=self.customer,title='IT project',description='Build a dashboard',budget_min=10000,budget_max=50000,client_name='Customer')
        from .models import Skill
        self.project.skills.set(Skill.objects.filter(name='React'))
        self.media=tempfile.mkdtemp()
        self.override=override_settings(MEDIA_ROOT=self.media); self.override.enable()
    def tearDown(self):
        self.override.disable(); shutil.rmtree(self.media)
        super().tearDown()
    def proposal(self,user=None):
        self.as_user(user or self.freelancer)
        response=self.post('proposals',{'project':self.project.pk,'cover_letter':'I can build it','amount':'25000.00','delivery_days':5})
        self.assertEqual(response.status_code,201,response.data)
        return response.data['id']
    def contract(self):
        proposal=self.proposal(); self.as_user(self.customer)
        response=self.post(f'proposals/{proposal}/accept')
        self.assertEqual(response.status_code,201,response.data)
        return response.data['id']
    def work(self):
        contract=self.contract()
        for user in [self.customer,self.freelancer]:
            self.as_user(user); self.assertEqual(self.post(f'contracts/{contract}/sign',{'accepted':True}).status_code,200)
        self.as_user(self.customer)
        Profile.objects.filter(user=self.customer).update(balance=50000)
        self.assertEqual(self.post(f'contracts/{contract}/fund', {'confirmed':True}).status_code,200)
        self.as_user(self.freelancer)
        response=self.client.post(f'/api/contracts/{contract}/submit/',{'file':SimpleUploadedFile('project.zip',b'PK\x03\x04private original bytes'),'preview_text':'Dashboard implemented'},format='multipart')
        self.assertEqual(response.status_code,200,response.data)
        return contract
    def test_public_directory_and_ownership(self):
        self.assertEqual(self.client.get('/api/projects/').data['count'],1)
        profiles=self.client.get('/api/profiles/').data
        self.assertEqual(profiles['count'],2)
        self.assertNotIn('email',profiles['results'][0]); self.assertNotIn('phone',profiles['results'][0])
        self.assertEqual(self.post('proposals',{}).status_code,401)
        self.as_user(self.other)
        self.assertEqual(self.client.patch(f'/api/projects/{self.project.pk}/',{'title':'stolen'},format='json').status_code,403)
        self.assertEqual(self.client.delete(f'/api/projects/{self.project.pk}/').status_code,403)
        self.assertEqual(self.post('projects',{'title':'Test','description':'Test','category':'development','skills':['React'],'deadline':'2099-01-01','budget_min':1000,'budget_max':2000}).status_code,403)
    def test_proposal_identity_duplicate_and_visibility(self):
        proposal=self.proposal()
        response=self.post('proposals',{'project':self.project.pk,'cover_letter':'Again','amount':1,'delivery_days':1})
        self.assertEqual(response.status_code,400)
        self.as_user(self.other)
        self.assertEqual(self.client.get('/api/proposals/').data['count'],0)
        self.assertEqual(self.post(f'proposals/{proposal}/accept').status_code,404)
        self.as_user(self.customer)
        self.assertEqual(self.client.get('/api/proposals/').data['count'],1)
    def test_contract_state_and_access(self):
        contract=self.contract()
        self.assertEqual(self.post(f'contracts/{contract}/sign').status_code,400)
        self.assertEqual(self.post(f'contracts/{contract}/sign',{'accepted':True}).status_code,200)
        self.as_user(self.freelancer)
        self.assertEqual(self.client.get(f'/api/projects/{self.project.pk}/').status_code,200)
        self.assertEqual(self.post(f'contracts/{contract}/submit').status_code,400)
        self.assertEqual(self.client.get(f'/api/contracts/{contract}/download/').status_code,403)
        self.as_user(self.other)
        self.assertEqual(self.client.get(f'/api/contracts/{contract}/').status_code,404)
        self.assertEqual(self.client.get(f'/api/projects/{self.project.pk}/').status_code,404)
    def test_review_revisions_wallet_payment_download_archive(self):
        contract=self.work()
        self.as_user(self.customer)
        response=self.client.get(f'/api/contracts/{contract}/')
        self.assertNotIn('file',response.data['deliverables'][0])
        self.assertEqual(self.client.get(f'/api/contracts/{contract}/download/').status_code,403)
        self.assertEqual(self.post(f'contracts/{contract}/revision',{'note':'Please add tests'}).data['status'],'active')
        self.assertEqual(self.post('payments/checkout',{'contract':contract,'provider':'wallet'}).status_code,400)
        self.as_user(self.freelancer)
        response=self.client.post(f'/api/contracts/{contract}/submit/',{'file':SimpleUploadedFile('final.zip',b'PK\x03\x04final bytes'),'preview_text':'Tests added'},format='multipart')
        self.assertEqual(response.status_code,200)
        self.as_user(self.customer)
        self.assertEqual(self.post('payments/checkout',{'contract':contract,'provider':'wallet'}).status_code,400)
        response=self.post(f'contracts/{contract}/accept',{'confirmed':True})
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(Profile.objects.get(user=self.customer).balance,25000)
        self.assertEqual(Profile.objects.get(user=self.freelancer).balance,25000)
        self.assertEqual(self.post(f'contracts/{contract}/accept',{'confirmed':True}).status_code,200)
        result=self.client.get(f'/api/contracts/{contract}/download/')
        self.assertEqual(result.status_code,200)
        self.assertEqual(b''.join(result.streaming_content),b'PK\x03\x04final bytes')
        self.assertEqual(self.client.get('/api/dashboard/').data['completed_contracts'],1)
        self.as_user(); self.assertEqual(self.client.get('/api/projects/').data['count'],0)
        self.assertEqual(Project.objects.count(),1); self.assertEqual(Contract.objects.count(),1)
    def test_profile_settings_and_unverified_skills(self):
        self.as_user(self.freelancer)
        response=self.client.patch('/api/auth/me/',{'about':'Django developer','skills':['Python','Django'],'verified_skills':['Python'],'rate':'50000','rate_unit':'day','language':'uz-cyrl','theme':'dark','balance':'999999'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertCountEqual(response.data['profile']['skills'],['Python','Django'])
        self.assertEqual(response.data['profile']['verified_skills'],[])
        self.assertEqual(Profile.objects.get(user=self.freelancer).balance,0)
        self.assertEqual(self.client.patch('/api/auth/me/',{'avatar':'data:image/svg+xml;base64,abc'},format='json').status_code,400)
    def test_profile_update_preserves_concurrent_payment_balance(self):
        from .auth_serializers import ProfileUpdateSerializer
        stale_profile = Profile.objects.get(user=self.freelancer)
        form = ProfileUpdateSerializer(stale_profile, data={'about':'New bio'}, partial=True)
        self.assertTrue(form.is_valid())
        Profile.objects.filter(user=self.freelancer).update(balance=12345)
        form.save()
        self.assertEqual(Profile.objects.get(user=self.freelancer).balance,12345)
    def test_avatar_is_decodable_and_corrupt_images_rejected(self):
        import base64
        import io
        from PIL import Image
        self.as_user(self.freelancer)
        buffer=io.BytesIO(); Image.new('RGB',(32,32),'teal').save(buffer,format='PNG')
        image='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()
        response=self.client.patch('/api/auth/me/',{'avatar':image},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertTrue(response.data['profile']['avatar'].startswith('data:image/jpeg;base64,'))
        corrupt='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\ninvalid').decode()
        self.assertEqual(self.client.patch('/api/auth/me/',{'avatar':corrupt},format='json').status_code,400)
    def test_withdrawal_reservation_cancel_and_processing(self):
        self.as_user(self.freelancer)
        Profile.objects.filter(user=self.freelancer).update(balance=10000)
        response=self.post('wallet/withdraw',{'amount':'4000','destination':'Bank •••• 1234','confirmed':True})
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(Profile.objects.get(user=self.freelancer).balance,6000)
        self.assertEqual(self.post('wallet/withdraw',{'amount':'7000','destination':'Bank 1234'}).status_code,400)
        pk=response.data['id']
        self.assertEqual(self.post(f'wallet/withdrawals/{pk}/cancel').status_code,200)
        self.assertEqual(self.post(f'wallet/withdrawals/{pk}/cancel').status_code,400)
        self.assertEqual(Profile.objects.get(user=self.freelancer).balance,10000)
        self.assertEqual(self.post('wallet/withdraw',{'amount':'100','destination':'8600 1234 5678 9012'}).status_code,400)
        withdrawal=Withdrawal.objects.create(user=self.freelancer,amount=100,destination='Bank 1234')
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError): process_withdrawal(withdrawal.pk,'paid')


@override_settings(CLICK_SERVICE_ID='123',CLICK_MERCHANT_ID='456',CLICK_SECRET_KEY='test-only-key',CLICK_FISCALIZATION_ENABLED=False)
class ClickTests(MarketplaceTests):
    def callback(self,payment,action='0',error='0',amount=None,trans='123456',signature=True):
        data=dict(click_trans_id=trans,click_paydoc_id='987654',service_id='123',merchant_trans_id=str(payment.reference),amount=amount or str(payment.amount),action=action,sign_time='2026-09-06 12:00:00',error=error)
        parts=[trans,'123','test-only-key',str(payment.reference)]
        if action=='1':
            data['merchant_prepare_id']=str(payment.pk); parts.append(str(payment.pk))
        parts.extend([data['amount'],action,data['sign_time']])
        data['sign_string']=hashlib.md5(''.join(parts).encode()).hexdigest() if signature else 'invalid'
        return self.post('payments/click/'+('prepare' if action=='0' else 'complete'),data)
    def test_click_signature_amount_prepare_complete_replay(self):
        self.as_user(self.customer)
        result=self.post('payments/checkout',{'amount':'25000'})
        self.assertEqual(result.status_code,200,result.data)
        self.assertTrue(result.data['checkout_url'].startswith('https://my.click.uz/'))
        payment=Payment.objects.get(reference=result.data['payment']['reference'])
        self.as_user()
        self.assertEqual(self.callback(payment,signature=False).data['error'],-1)
        self.assertEqual(self.callback(payment,amount='1.00').data['error'],-2)
        self.assertEqual(self.callback(payment,action='1').data['error'],-6)
        self.assertEqual(self.callback(payment).data['error'],0)
        self.assertEqual(self.callback(payment).data['error'],0)
        self.assertEqual(self.callback(payment,action='1').data['error'],0)
        self.assertEqual(self.callback(payment,action='1').data['error'],-4)
        self.assertEqual(Profile.objects.get(user=self.customer).balance,25000)
        self.assertEqual(WalletEntry.objects.filter(kind='topup').count(),1)
    def test_cancelled_payment_cannot_credit_wallet(self):
        payment=Payment.objects.create(user=self.customer,amount=2000)
        self.assertEqual(self.callback(payment).data['error'],0)
        self.assertEqual(self.callback(payment,action='1',error='-1').data['error'],-9)
        self.assertEqual(self.callback(payment,action='1').data['error'],-9)
        self.assertEqual(Profile.objects.get(user=self.customer).balance,0)
    def test_topup_and_prepared_cancellation_guard(self):
        self.as_user(self.customer)
        result=self.post('payments/checkout',{'amount':'5000'})
        payment=Payment.objects.get(reference=result.data['payment']['reference'])
        self.callback(payment)
        self.assertEqual(self.post(f'payments/{payment.reference}/cancel').status_code,400)
        self.assertEqual(self.callback(payment,action='1').data['error'],0)
        self.assertEqual(Profile.objects.get(user=self.customer).balance,5000)

class ProductionCorsTests(APITestCase):
    @override_settings(CORS_ALLOW_ALL_ORIGINS=True)
    def test_preflight(self):
        response=self.client.options('/api/auth/login/',HTTP_ORIGIN='https://taskora-frontend-production.up.railway.app',HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',HTTP_ACCESS_CONTROL_REQUEST_HEADERS='content-type,authorization')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'],'*')
