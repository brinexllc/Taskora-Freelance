import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import (AdminCommand, AdminObligation, BrowserSession, Category, ContactVerification,
    Contract, Dispute, ModerationDecision, PlatformFee, Profile, Project, Proposal, Review,
    Skill, SkillVerification, SupportTicket, WalletEntry, Withdrawal)
from .security_test_helpers import authenticate_client, operator_request
from .tests import BaseTests
from .admin_control.workflows import (Conflict, block_user, unblock_user, edit_user,
    moderate_project, moderate_review, preview_dispute, execute_dispute, transition_dispute,
    add_dispute_note, decide_verification, verified_skill_names, merge_catalogue_skill,
    execute_command, cancel_unfunded_contract, propose_admin_amendment, moderate_message)


class AdminWorkflowTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.owner = self.account("workflow_owner", "client")
        self.worker = self.account("workflow_worker", "freelancer")
        self.admin = self.account("workflow_admin", "client")
        self.admin.is_staff = self.admin.is_superuser = True
        self.admin.save(update_fields=["is_staff", "is_superuser"])
        self.request = operator_request(self.admin)
        self.category = Category.objects.get(slug="development")
        self.project = Project.objects.create(owner=self.owner, title="Реальный заказ", description="Требования заказа", category=self.category,
            budget_min=1000000, budget_max=1000000, deadline=timezone.localdate() + timedelta(days=30), client_name="Клиент", status="published", skills_unspecified=True)
        self.proposal = Proposal.objects.create(project=self.project, freelancer=self.worker, freelancer_name="Исполнитель", freelancer_email=self.worker.email,
            cover_letter="Готов выполнить", amount=1000000, delivery_days=7)

    def contract(self):
        return Contract.objects.create(project=self.project, proposal=self.proposal, customer=self.owner, freelancer=self.worker,
            amount=1000000, delivery_days=7, terms="Согласованные условия", status="disputed", funded_at=timezone.now(), escrow_amount=1000000, fee_percent=5)

    def test_block_preserves_finances_revokes_session_and_queues_obligations(self):
        contract = self.contract()
        Withdrawal.objects.create(user=self.worker, amount=2000, destination="****1234")
        authenticate_client(self.client, self.worker)
        block_user(self.worker.pk, self.admin, "Подтверждённое нарушение правил", self.request)
        self.worker.refresh_from_db(); contract.refresh_from_db()
        self.assertFalse(self.worker.is_active)
        self.assertEqual(contract.escrow_amount, Decimal("1000000"))
        self.assertEqual(contract.status, "disputed")
        self.assertEqual(AdminObligation.objects.filter(user=self.worker).count(), 2)
        self.assertFalse(BrowserSession.objects.filter(user=self.worker, revoked_at__isnull=True).exists())
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        unblock_user(self.worker.pk, self.admin, "Проверка завершена успешно", self.request)
        self.worker.profile.refresh_from_db()
        self.assertTrue(self.worker.profile.public_hidden)

    def test_last_administrator_cannot_be_blocked_and_staff_cannot_mutate(self):
        with self.assertRaises(ValidationError):
            block_user(self.admin.pk, self.admin, "Проверка последнего администратора", self.request)
        self.worker.is_staff = True; self.worker.save(update_fields=["is_staff"])
        with self.assertRaises(PermissionDenied):
            block_user(self.owner.pk, self.worker, "Неавторизованный запрос", operator_request(self.worker))

    def test_contact_correction_invalidates_contact_evidence_and_is_audited(self):
        ContactVerification.objects.create(user=self.owner, channel="email", contact=self.owner.email, code_hash="not-a-secret", expires_at=timezone.now() + timedelta(minutes=10))
        edit_user(self.owner.pk, {"email": "corrected@example.com", "full_name": "Исправленное имя"}, self.admin, "Исправление по обращению владельца", self.request)
        self.owner.refresh_from_db(); self.owner.profile.refresh_from_db()
        self.assertEqual(self.owner.email, "corrected@example.com")
        self.assertEqual(self.owner.profile.full_name, "Исправленное имя")
        self.assertIsNone(self.owner.profile.email_verified_at)
        self.assertEqual(self.owner.profile.verified_email, "")
        self.assertFalse(ContactVerification.objects.filter(user=self.owner, used_at__isnull=True).exists())
        with self.assertRaises(ValidationError):
            edit_user(self.owner.pk, {"balance": "999999"}, self.admin, "Запрещённое изменение", self.request)

    def test_project_moderation_hides_public_content_preserving_contract_and_draft(self):
        contract = self.contract()
        moderate_project(self.project.pk, "hidden", self.admin, "Контент нарушает правила", self.request)
        contract.refresh_from_db()
        self.assertEqual(contract.escrow_amount, Decimal("1000000"))
        self.assertEqual(self.client.get(f"/api/projects/{self.project.pk}/").status_code, 404)
        self.as_user(self.worker)
        self.assertEqual(self.client.get(f"/api/projects/{self.project.pk}/").status_code, 200)
        self.project.status = "draft"; self.project.save(update_fields=["status"])
        moderate_project(self.project.pk, "approved", self.admin, "Содержание проверено", self.request)
        self.as_user()
        self.assertEqual(self.client.get(f"/api/projects/{self.project.pk}/").status_code, 404)

    def test_post_and_premoderation_control_public_visibility(self):
        self.assertEqual(self.client.get(f"/api/projects/{self.project.pk}/").status_code, 200)
        with patch("marketplace.admin_control.content_services.get_setting", return_value="pre"):
            self.assertEqual(self.client.get(f"/api/projects/{self.project.pk}/").status_code, 404)
        moderate_project(self.project.pk, "approved", self.admin, "Проверено администратором", self.request)
        with patch("marketplace.admin_control.content_services.get_setting", return_value="pre"):
            self.assertEqual(self.client.get(f"/api/projects/{self.project.pk}/").status_code, 200)

    def test_dispute_preview_settlement_idempotency_and_immutable_reason(self):
        contract = self.contract()
        dispute = Dispute.objects.create(contract=contract, opened_by=self.owner, reason="Результат не соответствует заданию", status="admin_review")
        preview = preview_dispute(dispute.pk, "600000", "Часть работы подтверждена доказательствами", self.admin, self.request)
        self.assertEqual(preview.snapshot["net"], "570000.00")
        self.assertEqual(preview.snapshot["fee"], "30000.00")
        self.assertEqual(preview.snapshot["refund"], "400000.00")
        key = uuid.uuid4()
        result = execute_dispute(preview.pk, key, self.admin, self.request, True)
        self.assertEqual(result, execute_dispute(preview.pk, key, self.admin, self.request, True))
        contract.refresh_from_db()
        self.assertEqual(contract.escrow_amount, 0)
        self.assertEqual(PlatformFee.objects.filter(contract=contract).count(), 1)
        self.assertEqual(AdminCommand.objects.count(), 1)
        with self.assertRaises(Conflict):
            execute_dispute(preview.pk, uuid.uuid4(), self.admin, self.request, True)

    def test_dispute_rejects_stale_preview_and_internal_note_is_not_participant_message(self):
        contract = self.contract()
        dispute = Dispute.objects.create(contract=contract, opened_by=self.owner, reason="Требуется проверка", status="admin_review")
        preview = preview_dispute(dispute.pk, "1000000", "Полное выполнение подтверждено", self.admin, self.request)
        count = contract.messages.count()
        add_dispute_note(dispute.pk, self.admin, "Служебная заметка администратора", request=self.request)
        self.assertEqual(contract.messages.count(), count)
        with self.assertRaises(Conflict):
            execute_dispute(preview.pk, uuid.uuid4(), self.admin, self.request, True)
        self.assertFalse(PlatformFee.objects.exists())

    def test_review_hiding_preserves_original_and_changes_derived_rating(self):
        contract = self.contract(); contract.status = "completed"; contract.save(update_fields=["status"])
        review = Review.objects.create(contract=contract, author=self.owner, target=self.worker, rating=5, text="Исходный отзыв")
        moderate_review(review.pk, False, self.admin, "Текст нарушает правила", self.request)
        review.refresh_from_db()
        self.assertEqual(review.text, "Исходный отзыв"); self.assertEqual(review.rating, 5)
        self.assertEqual(self.client.get(f"/api/profiles/{self.worker.profile.pk}/reviews/").data["count"], 0)

    def test_verification_requires_evidence_and_merge_removes_trust(self):
        source = Skill.objects.create(name="Workflow source skill")
        target = Skill.objects.create(name="Workflow target skill")
        self.worker.profile.skills.add(source)
        application = SkillVerification.objects.create(user=self.worker, skill=source, evidence_type="certificate", evidence_url="https://example.com/certificate.pdf")
        decide_verification(application.pk, "approved", self.admin, "Сертификат проверен вручную", request=self.request)
        self.assertEqual(verified_skill_names(self.worker.pk), [source.name])
        merge_catalogue_skill(source.pk, target.pk, self.admin, "Это один и тот же навык", self.request)
        self.assertEqual(verified_skill_names(self.worker.pk), [])
        application.refresh_from_db()
        self.assertEqual(application.status, "in_review")
        self.assertEqual(application.skill_id, source.pk)

    def test_support_and_reports_are_participant_scoped_and_repeat_reports_link(self):
        self.as_user(self.owner)
        response = self.post("support-tickets", {"subject": "Проверка оплаты", "text": "Прошу проверить оплату заказа"})
        self.assertEqual(response.status_code, 201, response.data)
        ticket_id = response.data["id"]
        report = self.post("reports", {"object_type": "project", "object_id": self.project.pk, "reason": "Нарушение правил платформы"})
        repeated = self.post("reports", {"object_type": "project", "object_id": self.project.pk, "reason": "Дополнительные доказательства"})
        self.assertEqual(repeated.status_code, 201, repeated.data)
        self.assertEqual(repeated.data["previous"], report.data["id"])
        self.as_user(self.worker)
        self.assertEqual(self.client.get(f"/api/support-tickets/{ticket_id}/").status_code, 404)

    def test_nonfinancial_uuid_repeat_keeps_one_audit_and_different_payload_conflicts(self):
        data = {"idempotency_key": str(uuid.uuid4()), "reason": "Проверено нарушение правил", "published": False}
        contract = self.contract()
        review = Review.objects.create(contract=contract, author=self.owner, target=self.worker, rating=5, text="Исторический текст")
        first = execute_command(self.request, "review.moderate", review.pk, data)
        self.assertEqual(first, execute_command(self.request, "review.moderate", review.pk, data))
        self.assertEqual(ModerationDecision.objects.filter(object_type="review", object_id=review.pk).count(), 1)
        with self.assertRaises(Conflict):
            execute_command(self.request, "review.moderate", review.pk, {**data, "published": True})

    def test_admin_cancellation_never_distributes_funded_escrow(self):
        contract = self.contract()
        with self.assertRaises(ValidationError):
            cancel_unfunded_contract(contract.pk, self.admin, "Отмена по заявлению участника", self.request)
        contract.funded_at = None; contract.escrow_amount = 0; contract.status = "draft"
        contract.save(update_fields=["funded_at", "escrow_amount", "status"])
        cancel_unfunded_contract(contract.pk, self.admin, "Отмена по заявлению участника", self.request)
        contract.refresh_from_db()
        self.assertEqual(contract.status, "cancelled")
        self.assertFalse(WalletEntry.objects.exists())

    def test_admin_amendment_never_signs_for_a_party(self):
        contract = self.contract(); contract.status = "active"; contract.save(update_fields=["status"])
        amendment = propose_admin_amendment(contract.pk, {"scope": "Уточнённый объём"}, self.admin, "Исправление согласовано к обсуждению", self.request)
        self.assertIsNone(amendment.customer_accepted_at)
        self.assertIsNone(amendment.freelancer_accepted_at)
        contract.refresh_from_db()
        self.assertEqual(contract.scope, "")
        self.assertEqual(contract.version, 1)

    def test_message_moderation_preserves_original_and_participant_read_state(self):
        from .models import Message
        contract = self.contract()
        original = Message.objects.create(contract=contract, sender=self.worker, text="Нарушающий правила исходный текст")
        moderate_message(contract.pk, original.pk, False, True, self.admin, "Нарушение подтверждено модерацией", self.request)
        original.refresh_from_db()
        self.assertEqual(original.text, "Нарушающий правила исходный текст")
        self.assertIsNone(original.read_at)
        self.as_user(self.owner)
        response = self.client.get(f"/api/contracts/{contract.pk}/messages/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["results"][0]["text"], "Сообщение скрыто администрацией Taskora.")
        preview = self.client.get(f"/api/contracts/{contract.pk}/")
        self.assertEqual(preview.data["last_message_text"], "Сообщение скрыто администрацией Taskora.")

    def test_typed_user_editor_requires_signed_preview_before_mutation(self):
        import json
        from .admin_control.views import command_form
        self.as_operator(self.admin)
        path = f"/admin/control/users/{self.owner.pk}/action/user.edit/"
        form = command_form("user.edit", self.owner)
        data = {key: field.value() for key, field in ((name, form[name]) for name in form.fields)}
        data.update(full_name="Имя после предварительного просмотра", reason="Исправление по запросу владельца", confirmed="on")
        for key in ("portfolio", "services"):
            data[key] = json.dumps(data[key] or []) if not isinstance(data[key], str) else data[key]
        data = {key: value if value is not None else "" for key, value in data.items()}
        response = self.client.post(path, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context_data.get("edit_preview"), response.context_data.get("form"))
        self.owner.profile.refresh_from_db()
        self.assertNotEqual(self.owner.profile.full_name, data["full_name"])
        token = response.context_data["edit_preview"]
        result = self.client.post(path, {"edit_preview": token, "execute": "yes", "confirmed": "on"})
        self.assertEqual(result.status_code, 302)
        self.owner.profile.refresh_from_db()
        self.assertEqual(self.owner.profile.full_name, data["full_name"])

    @patch('marketplace.auth_views.send_security_code')
    @patch('marketplace.auth_views.delivery_configured', return_value=True)
    def test_recovery_requests_standard_code_and_keeps_mfa(self, delivery, send):
        from .admin_control.workflows import initiate_account_recovery
        from .models import PasswordResetCode, MultiFactorCredential
        credential = MultiFactorCredential.objects.get(user=self.admin)
        original_secret = credential.encrypted_secret
        initiate_account_recovery(self.admin.pk, self.admin, "Подтверждённое обращение владельца", self.request)
        credential.refresh_from_db()
        self.assertEqual(credential.encrypted_secret, original_secret)
        self.assertTrue(credential.enabled_at)
        self.assertTrue(PasswordResetCode.objects.filter(user=self.admin).exists())
        send.assert_called_once()
