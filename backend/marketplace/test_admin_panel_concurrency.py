"""Actual PostgreSQL races for administrative account restrictions."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from rest_framework.exceptions import APIException

from .admin_control import workflows
from .models import AccountRestriction, AuditLog, Profile
from .security_models import BrowserSession
from .security_test_helpers import operator_request


User = get_user_model()


@skipUnlessDBFeature("has_select_for_update")
class AdminPanelRestrictionConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.admins = [User.objects.create_user(
            f"race_admin_{index}", is_staff=True, is_superuser=True
        ) for index in range(2)]
        for actor in self.admins:
            Profile.objects.create(user=actor, full_name=actor.username)
        self.requests = [operator_request(actor) for actor in self.admins]

    def race(self, target_ids):
        """Both requests pass real authorization before either acquires row locks."""
        ready = Barrier(2, timeout=10)
        real_guard = workflows.guard

        def synchronized_guard(*args, **kwargs):
            real_guard(*args, **kwargs)
            ready.wait()

        def execute(index):
            try:
                with connections["default"].cursor() as cursor:
                    cursor.execute("SET statement_timeout TO 15000")
                workflows.block_user(target_ids[index], self.admins[index],
                    "Concurrent restriction acceptance test", self.requests[index])
                return "success"
            except APIException as exc:
                return exc.status_code
            finally:
                connections.close_all()

        with patch.object(workflows, "guard", side_effect=synchronized_guard):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(execute, range(2)))
        return results

    def test_two_admins_cannot_concurrently_block_the_last_active_admin(self):
        results = self.race([self.admins[1].pk, self.admins[0].pk])
        self.assertCountEqual(results, ["success", 400])
        self.assertEqual(User.objects.filter(is_active=True, is_staff=True, is_superuser=True).count(), 1)
        self.assertEqual(AccountRestriction.objects.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action="user_block").count(), 1)
        blocked = User.objects.get(is_active=False)
        self.assertFalse(BrowserSession.objects.filter(user=blocked, revoked_at__isnull=True).exists())

    def test_concurrent_block_creates_one_restriction_and_one_audit(self):
        target = User.objects.create_user("race_target")
        Profile.objects.create(user=target, full_name="Restriction target")
        results = self.race([target.pk, target.pk])
        self.assertCountEqual(results, ["success", 409])
        self.assertEqual(AccountRestriction.objects.filter(user=target).count(), 1)
        self.assertEqual(AuditLog.objects.filter(action="user_block", object_id=str(target.pk)).count(), 1)
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertTrue(target.profile.public_hidden)
