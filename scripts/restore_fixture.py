"""Subprocess fixture for check_isolated_restore.py, never a production command."""
import hashlib
import json
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from django.conf import settings
from django.db import connection, transaction
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone
from marketplace.models import Category, Contract, Deliverable, PlatformFee, Profile, Project, Proposal, WalletEntry, WalletOpeningBalance
from marketplace.escrow import fund_contract, distribute
from marketplace.operations import private_file_manifest, pending_migrations

if settings.TASKORA_ENV != 'test' or str(connection.settings_dict['PORT']) != '55442' or connection.settings_dict['HOST'] != '127.0.0.1' or not connection.settings_dict['NAME'].startswith('taskora_restore_'):
    raise SystemExit('Fixture restricted to isolated loopback restore databases.')
if os.environ.get('RESTORE_FIXTURE_ACTION') == 'seed':
    admin = get_user_model().objects.create_user(username='restore_owner', is_staff=True, is_superuser=True)
    customer = get_user_model().objects.create_user(username='restore_customer')
    worker = get_user_model().objects.create_user(username='restore_worker')
    for user, amount in [(admin, 0), (customer, 1000000), (worker, 0)]:
        Profile.objects.create(user=user, full_name=user.username, balance=amount)
        WalletOpeningBalance.objects.create(user=user, amount=amount, evidence='Synthetic isolated restore fixture', confirmed_by=admin, confirmed_at=timezone.now())
    project = Project.objects.create(owner=customer, category=Category.objects.first(), title='Restore fixture', description='Restore evidence', budget_min=1000000, budget_max=1000000)
    proposal = Proposal.objects.create(project=project, freelancer=worker, freelancer_name='Restore worker', freelancer_email='restore@example.test', amount=1000000, delivery_days=3, cover_letter='Restore')
    contract = Contract.objects.create(project=project, proposal=proposal, customer=customer, freelancer=worker, amount=1000000, fee_percent=5, fee_amount=50000, delivery_days=3, terms='Synthetic fixture', status='awaiting_funding')
    with transaction.atomic():
        locked = Contract.objects.select_for_update().get(pk=contract.pk)
        fund_contract(locked, customer)
        distribute(locked, customer, 400000, 'Synthetic restore: partial distribution')
    work = Deliverable(contract=contract, filename='restored-result.txt', preview_text='Restore fixture private file')
    work.file.save('restored-result.txt', ContentFile(b'Taskora isolated private restore fixture\n'), save=True)

money = {'profiles': list(Profile.objects.order_by('pk').values('pk', 'balance')),
         'ledger': list(WalletEntry.objects.order_by('pk').values('pk', 'user_id', 'contract_id', 'amount', 'kind', 'reference')),
         'fees': list(PlatformFee.objects.order_by('pk').values('pk', 'contract_id', 'gross_amount', 'fee_amount')),
         'contracts': list(Contract.objects.order_by('pk').values('pk', 'amount', 'released_amount', 'refunded_amount', 'escrow_amount', 'fee_percent'))}
encoded = json.dumps(money, default=str, sort_keys=True).encode()
result = {'money_sha256': hashlib.sha256(encoded).hexdigest(), 'money': money,
          'files': private_file_manifest(), 'pending_migrations': pending_migrations()}
from marketplace.reconciliation import reconcile
result['reconciliation'] = reconcile([])  # Synthetic fixture contains no external provider operations.
from rest_framework.test import APIClient
client = APIClient()
contract = Contract.objects.first()
client.force_authenticate(contract.customer)
download = client.get(f'/api/contracts/{contract.pk}/download/')
result['participant_download_status'] = download.status_code
if download.status_code == 200:
    result['participant_download_sha256'] = hashlib.sha256(b''.join(download.streaming_content)).hexdigest()
    download.close()
client.force_authenticate(get_user_model().objects.get(username='restore_owner'))
result['outsider_download_status'] = client.get(f'/api/contracts/{contract.pk}/download/').status_code
client.force_authenticate(user=None)
result['public_file_status'] = client.get('/media/' + Deliverable.objects.first().file.name).status_code
Path(os.environ['RESTORE_FIXTURE_REPORT']).write_text(json.dumps(result, default=str, ensure_ascii=False, indent=2), encoding='utf-8')
