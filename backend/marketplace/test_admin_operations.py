from .models import Category
import uuid
from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import PermissionDenied, ValidationError
from .tests import BaseTests
from .models import AuditLog, Profile, Project, ProjectAttachment, WalletEntry
from .admin_operations import adjust_balance


class AdminOperationsTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.owner = self.account('owner', 'client')
        self.admin = self.account('admin', 'client')
        self.admin.is_staff = self.admin.is_superuser = True
        self.admin.save()

    def test_adjustment_permission_reason_ledger_and_replay(self):
        key = uuid.uuid4()
        with self.assertRaises(PermissionDenied):
            adjust_balance(self.owner.pk, Decimal('100'), 'Documented correction', key, self.owner)
        with self.assertRaises(ValidationError):
            adjust_balance(self.owner.pk, Decimal('100'), '', key, self.admin)
        for _ in range(2):
            adjust_balance(self.owner.pk, Decimal('100'), 'Documented correction', key, self.admin)
        self.assertEqual(Profile.objects.get(user=self.owner).balance, 100)
        self.assertEqual(WalletEntry.objects.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action='balance_adjustment', actor=self.admin).count(), 1)
        with self.assertRaises(ValidationError):
            adjust_balance(self.owner.pk, Decimal('-101'), 'Documented correction', uuid.uuid4(), self.admin)
        self.assertEqual(Profile.objects.get(user=self.owner).balance, 100)

    def test_admin_adjustment_screen_requires_superuser(self):
        self.client.force_login(self.admin)
        url = f'/admin/marketplace/profile/{self.owner.profile.pk}/adjust-balance/'
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {'amount':'25.50', 'reason':'Documented correction', 'reference':str(uuid.uuid4()), 'confirmed':'on'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Profile.objects.get(user=self.owner).balance, Decimal('25.50'))
        self.admin.is_superuser = False
        self.admin.save()
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_admin_file_download_requires_permission_and_audits(self):
        import tempfile
        from django.test import override_settings
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            project = Project.objects.create(category=Category.objects.get(slug='other'),owner=self.owner, title='Private draft', description='Brief', budget_min=100, budget_max=1000)
            attachment = ProjectAttachment.objects.create(project=project, file=SimpleUploadedFile('brief.txt', b'private'), filename='brief.txt')
            url = f'/api/admin-files/projectattachment/{attachment.pk}/'
            self.as_user(self.owner)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.as_user(self.admin)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(AuditLog.objects.filter(action='admin_file_download', actor=self.admin).count(), 1)
            self.assertEqual(b''.join(response.streaming_content), b'private')
            response.close()
