import base64
import uuid
from urllib.parse import unquote

from django.test import override_settings
from django.utils import timezone
from .tests import BaseTests
from .models import Payment, Profile, WalletEntry, Withdrawal, PayoutRecipient
from .payme_views import milliseconds, TIMEOUT_MS


@override_settings(PAYME_MERCHANT_ID='merchant-test', PAYME_SECRET_KEY='private-test', PAYME_TEST_MODE=True)
class PaymeTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.user = self.account('customer', 'client')
        Profile.objects.filter(user=self.user).update(phone='+998901234567', verified_phone='+998901234567', phone_verified_at=timezone.now())
        self.recipient = PayoutRecipient.objects.create(user=self.user, provider='testbank', account='account-test',
            provider_recipient_id='recipient-test', destination='Bank •••• 1234', verification_evidence='secure-evidence-test',
            verified_by=self.user, verified_at=timezone.now())
        self.payment = Payment.objects.create(user=self.user, provider='payme', amount=50000)
        self.params = {'id': 'payme-transaction', 'time': milliseconds(), 'amount': 5000000,
                       'account': {'order_id': str(self.payment.reference)}}

    def rpc(self, method, params=None, password='private-test'):
        self.client.credentials()
        auth = base64.b64encode(('Paycom:' + password).encode()).decode()
        response = self.client.post('/api/payments/payme/', {'id': 42, 'method': method, 'params': params or {'id': self.params['id']}},
                                    format='json', HTTP_AUTHORIZATION='Basic ' + auth)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_complete_replay_statement_and_fiscal_data(self):
        self.assertTrue(self.rpc('CheckPerformTransaction', self.params)['result']['allow'])
        created = self.rpc('CreateTransaction', self.params)
        self.assertEqual(created, self.rpc('CreateTransaction', self.params))
        paid = self.rpc('PerformTransaction')
        self.assertEqual(paid['result']['state'], 2)
        self.assertEqual(paid, self.rpc('PerformTransaction'))
        self.assertEqual(Profile.objects.get(user=self.user).balance, 50000)
        self.assertEqual(WalletEntry.objects.filter(payment=self.payment).count(), 1)
        self.assertEqual(self.rpc('CheckTransaction')['result']['state'], 2)
        statement = self.rpc('GetStatement', {'from': self.params['time'], 'to': self.params['time']})['result']['transactions']
        self.assertEqual(len(statement), 1)
        self.assertEqual(statement[0]['amount'], 5000000)
        for kind in ['PERFORM', 'CANCEL']:
            result = self.rpc('SetFiscalData', {'id': self.params['id'], 'type': kind, 'fiscal_data': {'receipt_id': kind}})
            self.assertTrue(result['result']['success'])
        self.payment.refresh_from_db()
        self.assertEqual(len(self.payment.provider_data['fiscal']), 2)

    def test_auth_amount_account_and_provider_id_protection(self):
        self.assertEqual(self.rpc('CreateTransaction', self.params, 'wrong')['error']['code'], -32504)
        for update, code in [({'amount': 5000001}, -31001), ({'amount': True}, -31001),
                             ({'account': {'order_id': str(uuid.uuid4())}}, -31050)]:
            self.assertEqual(self.rpc('CreateTransaction', {**self.params, **update})['error']['code'], code)
        self.rpc('CreateTransaction', self.params)
        other = Payment.objects.create(user=self.user, provider='payme', amount=50000)
        self.assertEqual(self.rpc('CreateTransaction', {**self.params, 'account': {'order_id': str(other.reference)}})['error']['code'], -31008)
        self.assertEqual(self.rpc('Unknown')['error']['code'], -32601)
        self.assertEqual(Profile.objects.get(user=self.user).balance, 0)

    def test_paid_cancellation_reverses_once(self):
        self.rpc('CreateTransaction', self.params)
        self.rpc('PerformTransaction')
        params = {'id': self.params['id'], 'reason': 5}
        cancelled = self.rpc('CancelTransaction', params)
        self.assertEqual(cancelled['result']['state'], -2)
        self.assertEqual(cancelled, self.rpc('CancelTransaction', params))
        self.assertEqual(Profile.objects.get(user=self.user).balance, 0)
        self.assertEqual(WalletEntry.objects.filter(payment=self.payment).count(), 2)
        self.assertEqual(self.rpc('PerformTransaction')['error']['code'], -31008)

    def test_cancellation_does_not_spend_held_funds(self):
        self.rpc('CreateTransaction', self.params)
        self.rpc('PerformTransaction')
        self.as_user(self.user)
        self.assertEqual(self.post('wallet/withdraw', {'amount': 50000, 'recipient': self.recipient.pk,
            'idempotency_key':str(uuid.uuid4()), 'confirmed': True}).status_code, 201)
        self.assertEqual(self.rpc('CancelTransaction', {'id':self.params['id'], 'reason': 5})['error']['code'], -31007)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')
        self.assertEqual(Profile.objects.get(user=self.user).balance, 0)

    def test_timeout_is_persisted_even_when_perform_fails(self):
        self.rpc('CreateTransaction', self.params)
        self.payment.refresh_from_db()
        self.payment.provider_data['time'] = milliseconds() - TIMEOUT_MS
        self.payment.save()
        self.assertEqual(self.rpc('PerformTransaction')['error']['code'], -31008)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'cancelled')
        self.assertEqual(self.payment.provider_data['state'], -1)
        self.assertEqual(self.payment.provider_data['reason'], 4)

    def test_checkout_and_withdrawal_are_idempotent(self):
        self.as_user(self.user)
        key = str(uuid.uuid4())
        body = {'provider':'payme', 'amount':1000, 'idempotency_key':key}
        first = self.post('payments/checkout', body)
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data, self.post('payments/checkout', body).data)
        payload = base64.b64decode(unquote(first.data['checkout_url'].split('/')[-1])).decode()
        self.assertIn('ac.order_id=' + key, payload)
        self.assertIn(';a=100000;', payload)
        self.assertEqual(Payment.objects.filter(reference=key).count(), 1)
        self.assertEqual(self.post('payments/checkout', {**body, 'amount':2000}).status_code, 400)
        Profile.objects.filter(user=self.user).update(balance=5000)
        body = {'amount':1000, 'recipient':self.recipient.pk, 'confirmed':True, 'idempotency_key':str(uuid.uuid4())}
        self.assertEqual(self.post('wallet/withdraw', body).status_code, 201)
        self.assertEqual(self.post('wallet/withdraw', body).status_code, 200)
        self.assertEqual(Withdrawal.objects.count(), 1)
        self.assertEqual(Profile.objects.get(user=self.user).balance, 4000)
