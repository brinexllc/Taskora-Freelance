from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase
from rest_framework.exceptions import ValidationError

from .escrow import distribute, fund_contract
from .models import Category, Contract, PlatformFee, Profile, Project, Proposal, WalletEntry


@skipUnless(connection.vendor == 'postgresql', 'Row-lock concurrency requires PostgreSQL; set TEST_DATABASE_URL.')
class CommissionConcurrencyTests(TransactionTestCase):
    def test_parallel_final_distribution_pays_once(self):
        users=[]
        for name in ['concurrent_customer','concurrent_worker']:
            user=get_user_model().objects.create_user(username=name)
            Profile.objects.create(user=user,full_name=name,birth_date=date(2000,1,1),balance=1000000 if not users else 0)
            users.append(user)
        category=Category.objects.create(slug='concurrent',name='Concurrency')
        project=Project.objects.create(owner=users[0],category=category,title='Concurrency',description='Scope',budget_min=1000000,budget_max=1000000)
        offer=Proposal.objects.create(project=project,freelancer=users[1],amount=1000000,delivery_days=1,freelancer_name='Worker',freelancer_email='worker@example.com',cover_letter='Scope')
        contract=Contract.objects.create(project=project,proposal=offer,customer=users[0],freelancer=users[1],amount=1000000,delivery_days=1,terms='Terms',fee_percent=5,fee_amount=50000,status='awaiting_funding')
        with transaction.atomic():
            fund_contract(contract,users[0])
        barrier=Barrier(2)
        def settle():
            close_old_connections()
            try:
                stale=Contract.objects.get(pk=contract.pk)
                barrier.wait(timeout=10)
                try:
                    distribute(stale,users[0],Decimal('1000000'),'Concurrent acceptance')
                    return 'paid'
                except ValidationError:
                    return 'already_settled'
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(lambda _: settle(),range(2)))
        self.assertCountEqual(outcomes,['paid','already_settled'])
        self.assertEqual(PlatformFee.objects.filter(contract=contract).count(),1)
        self.assertEqual(WalletEntry.objects.filter(contract=contract,kind='escrow_release').count(),1)
        self.assertEqual(Profile.objects.get(user=users[1]).balance,Decimal('950000'))
