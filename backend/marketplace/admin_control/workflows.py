"""Audited state transitions. Money is delegated to the existing escrow service."""
import hashlib
import json
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from ..models import (AccountRestriction, AdminCommand, AdminObligation, AuditLog,
    BrowserSession, Category, ContactVerification, ContentReport, Contract, ContractAmendment,
    Dispute, DisputeNote, DisputePreview, ModerationDecision, Profile, Project, ProposalReport,
    Review, ScopedApiToken, Skill, SkillVerification, SupportMessage, SupportTicket, Withdrawal)
from ..escrow import event, notify
from ..fees import decimal_value, settlement


class Conflict(APIException):
    status_code = 409
    default_detail = "Данные изменились. Обновите карточку и повторите действие."


def reason_required(reason, minimum=3):
    reason = str(reason or "").strip()
    if not minimum <= len(reason) <= 5000:
        raise ValidationError(f"Основание должно содержать от {minimum} до 5000 символов.")
    return reason


def guard(actor, request=None, sensitive=False):
    from ..security import is_platform_admin, require_platform_admin_session
    if not is_platform_admin(actor):
        raise PermissionDenied("Действие доступно только администратору платформы.")
    if request is None:
        raise PermissionDenied("Требуется действующая административная сессия.")
    require_platform_admin_session(request, sensitive=sensitive)
    if request.user.pk != actor.pk:
        raise PermissionDenied("Автор действия не соответствует сессии.")


def audit(actor, action, obj, reason, before=None, after=None, request=None, operation_id=None):
    request_id = str(getattr(request, "request_id", "") or getattr(request, "headers", {}).get("X-Request-ID", ""))[:80] or str(uuid.uuid4())
    before, after = before or {}, after or {}
    return AuditLog.objects.create(actor=actor, action=action, object_type=obj._meta.model_name,
        object_id=str(obj.pk), reason=reason, before=before, after=after, request_id=request_id,
        operation_id=operation_id, outcome="success", detail={"reason": reason, "before": before, "after": after, "request_id": request_id, "result": "success"})


def decision(obj, actor, action, reason, before, after, request=None):
    ModerationDecision.objects.create(object_type=obj._meta.model_name, object_id=obj.pk,
        actor=actor, action=action, reason=reason, before=before, after=after)
    audit(actor, action, obj, reason, before, after, request)


def obligations_for(user_id):
    contracts = Contract.objects.filter(Q(customer_id=user_id) | Q(freelancer_id=user_id)).exclude(status__in=["completed", "cancelled"])
    withdrawals = Withdrawal.objects.filter(user_id=user_id, status__in=["pending", "processing", "reconciliation_required"])
    return {"contracts": contracts.count(), "escrow": str(contracts.aggregate(total=Sum("escrow_amount"))["total"] or 0), "withdrawals": withdrawals.count()}


def state_fingerprint(obj):
    """Optimistic version for models without a business version column."""
    names = {"status", "version", "moderation_status", "moderation_version", "updated_at", "is_active",
        "name", "labels", "slug", "active", "featured", "published", "moderation_reason", "merged_into_id",
        "email", "first_name", "last_name", "amount", "escrow_amount", "fee_percent", "resolution", "decision"}
    snapshot = {key: getattr(obj, key) for key in names if hasattr(obj, key)}
    if obj._meta.model_name == "user" and hasattr(obj, "profile"):
        profile = obj.profile
        snapshot["profile"] = {key: getattr(profile, key) for key in ("full_name", "phone", "about", "avatar", "portfolio", "services", "available", "public_hidden", "professional_title", "professional_experience", "location")}
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()


@transaction.atomic
def block_user(user_id, actor, reason, request=None):
    guard(actor, request, sensitive=True)
    reason = reason_required(reason)
    User = get_user_model()
    # Serialize last-admin checks across every active administrator.
    admins = list(User.objects.select_for_update().filter(is_active=True, is_staff=True, is_superuser=True).order_by("pk"))
    user = User.objects.select_for_update().get(pk=user_id)
    if user.is_staff and user.is_superuser and len(admins) <= 1:
        raise ValidationError("Нельзя заблокировать последнего администратора.")
    if not user.is_active:
        raise Conflict("Пользователь уже заблокирован.")
    snapshot = obligations_for(user.pk)
    restriction = AccountRestriction.objects.create(user=user, actor=actor, reason=reason, obligations=snapshot)
    user.is_active = False
    user.save(update_fields=["is_active"])
    Profile.objects.filter(user=user).update(public_hidden=True)
    from ..security import revoke_user_sessions
    revoke_user_sessions(user)
    from rest_framework.authtoken.models import Token
    Token.objects.filter(user=user).delete()
    ScopedApiToken.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=timezone.now())
    for project in Project.objects.select_for_update().filter(owner=user).exclude(moderation_status="hidden"):
        before = {"moderation_status": project.moderation_status, "status": project.status}
        project.moderation_status = "hidden"
        project.moderation_version += 1
        project.save(update_fields=["moderation_status", "moderation_version", "updated_at"])
        decision(project, actor, "account_block_content", reason, before, {"moderation_status": "hidden", "status": project.status}, request)
    contracts = Contract.objects.filter(Q(customer=user) | Q(freelancer=user)).exclude(status__in=["completed", "cancelled"])
    for contract in contracts.iterator():
        AdminObligation.objects.create(user=user, restriction=restriction, object_type="contract", object_id=contract.pk, description=f"Проверить обязательства по договору №{contract.pk} после блокировки.")
    for withdrawal in Withdrawal.objects.filter(user=user, status__in=["pending", "processing", "reconciliation_required"]).iterator():
        AdminObligation.objects.create(user=user, restriction=restriction, object_type="withdrawal", object_id=withdrawal.pk, description=f"Проверить фактический исход вывода №{withdrawal.pk}; не начинать новый перевод.")
    audit(actor, "user_block", user, reason, {"is_active": True}, {"is_active": False, "obligations": snapshot}, request)
    notify(user.pk, "account_blocked", "Доступ к аккаунту ограничен администрацией: " + reason, link="/dashboard?view=support")
    return restriction


@transaction.atomic
def unblock_user(user_id, actor, reason, request=None):
    guard(actor, request, sensitive=True)
    reason = reason_required(reason)
    user = get_user_model().objects.select_for_update().get(pk=user_id)
    if user.is_active:
        raise Conflict("Пользователь уже активен.")
    user.is_active = True
    user.save(update_fields=["is_active"])
    AccountRestriction.objects.filter(user=user, lifted_at__isnull=True).update(lifted_at=timezone.now(), lifted_by=actor)
    audit(actor, "user_unblock", user, reason, {"is_active": False}, {"is_active": True, "public_restoration_required": True}, request)
    notify(user.pk, "account_unblocked", "Доступ к аккаунту восстановлен. Войдите снова; публикации проходят отдельную проверку. " + reason, link="/dashboard?view=support")
    return user


@transaction.atomic
def edit_user(user_id, changes, actor, reason, request=None):
    guard(actor, request)
    reason = reason_required(reason)
    from ..auth_serializers import ProfileUpdateSerializer
    from ..validation import phone_number
    user = get_user_model().objects.select_for_update().get(pk=user_id)
    profile = Profile.objects.select_for_update().get(user=user)
    allowed = {"first_name", "last_name", "full_name", "about", "avatar", "portfolio", "services", "available", "professional_title", "professional_experience", "location", "email", "phone"}
    if not changes or set(changes) - allowed:
        raise ValidationError("Разрешены только публичные данные профиля и контактные данные.")
    before = {key: getattr(user if key in {"first_name", "last_name", "email"} else profile, key) for key in changes}
    profile_changes = {k: v for k, v in changes.items() if k not in {"first_name", "last_name", "email", "phone"}}
    serializer = ProfileUpdateSerializer(profile, data=profile_changes, partial=True)
    serializer.is_valid(raise_exception=True)
    for key, value in serializer.validated_data.items():
        setattr(profile, key, value)
    if "full_name" in changes:
        profile.full_name = serializers.CharField(max_length=160).run_validation(changes["full_name"])
    for key in {"first_name", "last_name"} & changes.keys():
        setattr(user, key, serializers.CharField(max_length=150, allow_blank=True).run_validation(changes[key]))
    if "email" in changes:
        email = serializers.EmailField().run_validation(changes["email"]).lower()
        if get_user_model().objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
            raise ValidationError("Этот email уже используется.")
        if email != user.email:
            user.email = email
            profile.email_verified_at, profile.verified_email = None, ""
            ContactVerification.objects.filter(user=user, channel="email", used_at__isnull=True).update(used_at=timezone.now())
    if "phone" in changes:
        phone = phone_number(changes["phone"])
        if Profile.objects.filter(phone=phone).exclude(pk=profile.pk).exists():
            raise ValidationError("Этот телефон уже используется.")
        if phone != profile.phone:
            profile.phone = phone
            profile.phone_verified_at, profile.verified_phone = None, ""
            ContactVerification.objects.filter(user=user, channel="phone", used_at__isnull=True).update(used_at=timezone.now())
    user.save(update_fields=["first_name", "last_name", "email"])
    profile.save()
    after = {key: getattr(user if key in {"first_name", "last_name", "email"} else profile, key) for key in changes}
    audit(actor, "user_edit", user, reason, before, after, request)
    return user


@transaction.atomic
def moderate_project(project_id, status, actor, reason, request=None, expected_version=None):
    guard(actor, request)
    reason = reason_required(reason)
    if status not in {"approved", "rejected", "hidden", "pending"}:
        raise ValidationError("Недопустимый статус модерации.")
    project = Project.objects.select_for_update(of=("self",)).select_related("owner").get(pk=project_id)
    if expected_version is not None and int(expected_version) != project.moderation_version:
        raise Conflict()
    if status == "approved" and project.owner_id and not project.owner.is_active:
        raise ValidationError("Нельзя публиковать контент заблокированного пользователя.")
    before = {"moderation_status": project.moderation_status, "title": project.title, "description": project.description, "version": project.moderation_version}
    project.moderation_status = status
    project.moderation_version += 1
    project.save(update_fields=["moderation_status", "moderation_version", "updated_at"])
    decision(project, actor, "project_moderate", reason, before, {"moderation_status": status, "version": project.moderation_version}, request)
    if project.owner_id:
        notify(project.owner_id, "project_moderated", f"Заказ №{project.pk}: {project.get_moderation_status_display()}. {reason}", link=f"/projects/{project.pk}")
    return project


@transaction.atomic
def edit_project(project_id, changes, actor, reason, request=None):
    guard(actor, request)
    reason = reason_required(reason)
    project = Project.objects.select_for_update().get(pk=project_id)
    if not changes or set(changes) - {"title", "description", "category_id", "featured"}:
        raise ValidationError("Допустимы название, некритичный текст, категория и рекомендуемый признак.")
    if "description" in changes and Contract.objects.filter(project=project).exists():
        raise ValidationError("Описание заказа с договором изменяется через согласование условий.")
    if "category_id" in changes and not Category.objects.filter(pk=changes["category_id"], active=True).exists():
        raise ValidationError("Выберите активную категорию.")
    before = {k: getattr(project, k) for k in changes}
    if "featured" in changes:
        changes["featured"] = serializers.BooleanField().run_validation(changes["featured"])
    for key, value in changes.items():
        setattr(project, key, value)
    project.full_clean()
    project.moderation_version += 1
    project.save()
    decision(project, actor, "project_edit", reason, before, {k: getattr(project, k) for k in changes}, request)
    return project


@transaction.atomic
def moderate_review(review_id, published, actor, reason, request=None):
    guard(actor, request)
    reason = reason_required(reason)
    review = Review.objects.select_for_update().get(pk=review_id)
    before = {"published": review.published}
    review.published = serializers.BooleanField().run_validation(published)
    review.moderation_reason = reason
    review.save(update_fields=["published", "moderation_reason"])
    decision(review, actor, "review_moderate", reason, before, {"published": review.published}, request)
    return review


def annotate_message_moderation(queryset):
    from django.db.models import OuterRef, Subquery
    return queryset.annotate(_moderation_action=Subquery(ModerationDecision.objects.filter(
        object_type=queryset.model._meta.model_name, object_id=OuterRef("pk"),
        action__in=["message_hide", "message_restore"]).order_by("-pk").values("action")[:1]))


def message_is_hidden(message):
    action = getattr(message, "_moderation_action", None)
    if not hasattr(message, "_moderation_action"):
        action = ModerationDecision.objects.filter(object_type=message._meta.model_name,
            object_id=message.pk, action__in=["message_hide", "message_restore"]).order_by("-pk").values_list("action", flat=True).first()
    return action == "message_hide"


@transaction.atomic
def moderate_message(conversation_id, message_id, proposal, hidden, actor, reason, request=None):
    guard(actor, request, sensitive=True)
    reason = reason_required(reason, 10)
    from ..models import Message, ProposalMessage
    model = ProposalMessage if proposal else Message
    link = "conversation_id" if proposal else "contract_id"
    message = model.objects.select_for_update().filter(pk=message_id, **{link: conversation_id}).first()
    if not message or getattr(message, "system", False):
        raise ValidationError("Выберите пользовательское сообщение из этого обсуждения.")
    hidden = serializers.BooleanField().run_validation(hidden)
    decision(message, actor, "message_hide" if hidden else "message_restore", reason,
        {"hidden": message_is_hidden(message)}, {"hidden": hidden}, request)
    return message


@transaction.atomic
def transition_dispute(dispute_id, status, actor, reason, request=None):
    guard(actor, request)
    reason = reason_required(reason)
    original = Dispute.objects.get(pk=dispute_id)
    contract = Contract.objects.select_for_update().get(pk=original.contract_id)
    dispute = Dispute.objects.select_for_update().get(pk=dispute_id)
    if status not in {"opened": {"evidence_collection"}, "evidence_collection": {"admin_review"}, "admin_review": {"evidence_collection"}}.get(dispute.status, set()):
        raise ValidationError("Недопустимый переход стадии спора.")
    before = {"status": dispute.status, "version": dispute.version}
    dispute.status, dispute.version, dispute.updated_at = status, dispute.version + 1, timezone.now()
    dispute.save(update_fields=["status", "version", "updated_at"])
    event(contract, actor, "dispute_stage", f"Стадия спора: {dispute.get_status_display()}. {reason}")
    audit(actor, "dispute_transition", dispute, reason, before, {"status": status, "version": dispute.version}, request)
    return dispute


@transaction.atomic
def add_dispute_note(dispute_id, actor, text, recipient=None, request=None):
    guard(actor, request)
    text = reason_required(text)
    dispute = Dispute.objects.select_for_update().select_related("contract").get(pk=dispute_id)
    if dispute.status == "resolved":
        raise ValidationError("Закрытый спор доступен только для чтения; создайте связанное обращение.")
    recipient = int(recipient) if recipient else None
    if recipient and recipient not in {dispute.contract.customer_id, dispute.contract.freelancer_id}:
        raise ValidationError("Доказательства можно запросить только у стороны договора.")
    note = DisputeNote.objects.create(dispute=dispute, actor=actor, text=text, recipient_id=recipient)
    dispute.version += 1
    dispute.updated_at = timezone.now()
    dispute.save(update_fields=["version", "updated_at"])
    if recipient:
        notify(recipient, "evidence_requested", "Администрация Taskora запрашивает доказательства: " + text, dispute.contract)
    audit(actor, "dispute_evidence_request" if recipient else "dispute_private_note", dispute, text, after={"note_id": note.pk, "recipient": recipient}, request=request)
    return note


def dispute_snapshot(dispute, contract, gross, reason):
    values = settlement(contract.escrow_amount, gross, contract.fee_percent)
    return {"dispute_id": dispute.pk, "dispute_status": dispute.status, "dispute_version": dispute.version,
        "contract_id": contract.pk, "contract_version": contract.version, "contract_status": contract.status,
        "customer_id": contract.customer_id, "freelancer_id": contract.freelancer_id,
        "escrow": str(contract.escrow_amount), "amount": str(contract.amount), "fee_percent": str(contract.fee_percent),
        "reason": reason, **{k: str(v) for k, v in values.items()}}


@transaction.atomic
def preview_dispute(dispute_id, gross, reason, actor, request=None):
    guard(actor, request)
    reason = reason_required(reason, 10)
    original = Dispute.objects.get(pk=dispute_id)
    contract = Contract.objects.select_for_update().get(pk=original.contract_id)
    dispute = Dispute.objects.select_for_update().get(pk=dispute_id)
    if dispute.status != "admin_review" or contract.status != "disputed" or contract.escrow_amount != contract.amount:
        raise ValidationError("Для решения переведите открытый спор на рассмотрение и проверьте полный резерв.")
    gross = decimal_value(gross, maximum=contract.escrow_amount)
    return DisputePreview.objects.create(dispute=dispute, actor=actor, gross=gross, reason=reason,
        snapshot=dispute_snapshot(dispute, contract, gross, reason), expires_at=timezone.now() + timedelta(minutes=15))


@transaction.atomic
def execute_dispute(preview_id, idempotency_key, actor, request=None, confirmed=False):
    guard(actor, request, sensitive=True)
    if confirmed is not True:
        raise ValidationError("Подтвердите согласие с расчётом.")
    try:
        key = uuid.UUID(str(idempotency_key))
        preview = DisputePreview.objects.get(pk=preview_id, actor=actor)
    except (ValueError, TypeError, DisputePreview.DoesNotExist):
        raise ValidationError("Укажите корректный предпросмотр и постоянный UUID операции.")
    payload_hash = hashlib.sha256(json.dumps({"preview_id": str(preview.id), "snapshot": preview.snapshot}, sort_keys=True).encode()).hexdigest()
    # Same contract lock serializes both repeated keys and rival previews.
    contract = Contract.objects.select_for_update().get(pk=preview.dispute.contract_id)
    previous = AdminCommand.objects.filter(pk=key).first()
    if previous:
        if previous.actor_id != actor.pk or previous.request_hash != payload_hash or previous.action != "dispute.resolve":
            raise Conflict("Ключ уже использован для другого действия или расчёта.")
        return previous.result
    dispute = Dispute.objects.select_for_update().get(pk=preview.dispute_id)
    if preview.expires_at <= timezone.now() or dispute.status != "admin_review" or contract.status != "disputed":
        raise Conflict("Предпросмотр истёк или состояние изменилось; рассчитайте решение заново.")
    if dispute_snapshot(dispute, contract, preview.gross, preview.reason) != preview.snapshot:
        raise Conflict("Условия, состояние спора или суммы изменились; нужен новый предпросмотр.")
    from ..escrow import resolve_dispute
    resolved = resolve_dispute(dispute.pk, actor, preview.gross, preview.reason, request=request)
    resolved.version += 1
    resolved.updated_at = timezone.now()
    resolved.save(update_fields=["version", "updated_at"])
    result = {"id": resolved.pk, "status": "resolved", "calculation": preview.snapshot, "idempotency_key": str(key)}
    try:
        with transaction.atomic():
            AdminCommand.objects.create(id=key, actor=actor, action="dispute.resolve", request_hash=payload_hash, result=result)
    except IntegrityError:
        raise Conflict("Ключ уже использован для другого действия; расчёт отменён.")
    audit(actor, "admin_dispute_resolve", resolved, preview.reason, preview.snapshot, result, request, key)
    return result


@transaction.atomic
def review_report(report_id, status, actor, reason, proposal=False, request=None):
    guard(actor, request)
    reason = reason_required(reason)
    model = ProposalReport if proposal else ContentReport
    report = model.objects.select_for_update().get(pk=report_id)
    transitions = {"new": {"in_review"}, "in_review": {"needs_information", "resolved", "rejected"}, "needs_information": {"in_review", "resolved", "rejected"}}
    if status not in transitions.get(report.status, set()):
        raise ValidationError("Недопустимый переход жалобы.")
    before = {"status": report.status}
    report.status, report.decision = status, reason
    if status in {"resolved", "rejected"}:
        report.resolved_at, report.resolved_by = timezone.now(), actor
    report.save()
    audit(actor, "report_review", report, reason, before, {"status": status}, request)
    notify(report.reporter_id, "report_updated", f"Жалоба №{report.pk}: {report.get_status_display()}. {reason}")
    return report


@transaction.atomic
def reply_support(ticket_id, text, actor, status=None, request=None):
    guard(actor, request)
    text = reason_required(text)
    ticket = SupportTicket.objects.select_for_update().get(pk=ticket_id)
    if status and status not in {"open", "in_review", "waiting_user", "resolved"}:
        raise ValidationError("Недопустимый статус обращения.")
    message = SupportMessage.objects.create(ticket=ticket, author=actor, administration=True, text=text)
    ticket.status = status or "waiting_user"
    ticket.save(update_fields=["status", "updated_at"])
    notify(ticket.author_id, "support_reply", "Администрация Taskora: " + text, ticket.contract, link=f"/dashboard?view=support&ticket={ticket.pk}")
    audit(actor, "support_reply", ticket, "Ответ администрации", after={"message_id": message.pk, "status": ticket.status}, request=request)
    return ticket


@transaction.atomic
def convert_support(ticket_id, actor, reason, request=None):
    guard(actor, request)
    reason = reason_required(reason, 10)
    original = SupportTicket.objects.get(pk=ticket_id)
    if not original.contract_id:
        raise ValidationError("У обращения нет связанного договора.")
    contract = Contract.objects.select_for_update().get(pk=original.contract_id)
    ticket = SupportTicket.objects.select_for_update().get(pk=ticket_id)
    if ticket.dispute_id:
        return ticket
    existing = Dispute.objects.filter(contract=contract).first()
    if existing:
        ticket.dispute = existing
    else:
        if contract.status not in {"active", "submitted"} or not contract.escrow_amount or ticket.author_id not in {contract.customer_id, contract.freelancer_id}:
            raise ValidationError("Договор не допускает открытия спора.")
        ticket.dispute = Dispute.objects.create(contract=contract, opened_by=ticket.author, reason=reason)
        contract.status = "disputed"
        contract.save(update_fields=["status"])
        from ..escrow import project_status
        project_status(contract, "disputed")
        event(contract, actor, "support_dispute", "Обращение передано на рассмотрение спора: " + reason)
    ticket.status = "in_review"
    ticket.save(update_fields=["dispute", "status", "updated_at"])
    audit(actor, "support_convert_dispute", ticket, reason, after={"dispute_id": ticket.dispute_id}, request=request)
    return ticket


def verified_skill_names(user_id):
    return list(SkillVerification.objects.filter(user_id=user_id, status="approved", skill__active=True,
        skill__merged_into__isnull=True, skill__profiles__user_id=user_id).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).values_list("skill__name", flat=True).distinct())


@transaction.atomic
def decide_verification(verification_id, status, actor, reason, expires_at=None, request=None):
    guard(actor, request)
    reason = reason_required(reason)
    application = SkillVerification.objects.select_for_update().select_related("skill").get(pk=verification_id)
    transitions = {"submitted": {"in_review", "approved", "rejected"}, "in_review": {"approved", "rejected"}, "approved": {"revoked", "in_review"}, "rejected": set(), "revoked": set()}
    if status not in transitions.get(application.status, set()):
        raise ValidationError("Недопустимый переход верификации.")
    if status == "approved":
        if not application.skill.active or application.skill.merged_into_id or not (application.evidence_url or application.evidence_file):
            raise ValidationError("Для подтверждения нужны проверенные доказательства и активный навык.")
        if expires_at and expires_at <= timezone.now():
            raise ValidationError("Срок подтверждения должен быть в будущем.")
    before = {"status": application.status}
    application.status, application.reviewer, application.decision = status, actor, reason
    application.decided_at, application.expires_at = timezone.now(), expires_at
    application.save()
    Profile.objects.filter(user_id=application.user_id).update(verified_skills=verified_skill_names(application.user_id))
    decision(application, actor, "skill_verification", reason, before, {"status": status, "reviewer_id": actor.pk}, request)
    notify(application.user_id, "skill_verification", f"Навык {application.skill.name}: {application.get_status_display()}. {reason}", link="/settings")
    return application


@transaction.atomic
def merge_catalogue_skill(source_id, target_id, actor, reason, request=None):
    guard(actor, request)
    reason = reason_required(reason)
    from ..taxonomy import merge_skills
    affected = list(SkillVerification.objects.select_for_update().filter(skill_id=source_id, status__in=["approved", "submitted", "in_review"]))
    target = merge_skills(int(source_id), int(target_id), actor=actor, reason=reason)
    for application in affected:
        application.status = "in_review"
        application.decision = "Повторная проверка после объединения навыка. " + reason
        application.save(update_fields=["status", "decision", "updated_at"])
        Profile.objects.filter(user_id=application.user_id).update(verified_skills=verified_skill_names(application.user_id))
    return target


@transaction.atomic
def propose_admin_amendment(contract_id, changes, actor, reason, request=None):
    guard(actor, request)
    reason = reason_required(reason)
    from ..product_api import AcceptanceTermsSerializer
    contract = Contract.objects.select_for_update().get(pk=contract_id)
    if contract.status not in {"draft", "customer_accepted", "freelancer_accepted", "awaiting_funding", "active"}:
        raise ValidationError("В этом состоянии договора изменение условий недоступно.")
    serializer = AcceptanceTermsSerializer(data=changes, partial=True)
    serializer.is_valid(raise_exception=True)
    if not serializer.validated_data or set(changes) - set(serializer.fields):
        raise ValidationError("Согласуйте допустимые условия приёмки и сроки.")
    if contract.funded_at and "delivery_days" in changes:
        raise ValidationError("После резервирования согласуйте точный deadline.")
    if not contract.funded_at and "deadline" in changes:
        raise ValidationError("До резервирования согласуйте delivery_days.")
    values = {k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in serializer.validated_data.items()}
    amendment = ContractAmendment.objects.create(contract=contract, proposed_by=actor, base_version=contract.version, changes=values)
    event(contract, actor, "admin_amendment_proposed", "Администрация предложила исправление; нужны подтверждения обеих сторон. " + reason, {"amendment_id": amendment.pk, "changes": values})
    audit(actor, "contract_amendment_propose", amendment, reason, {k: str(getattr(contract, k)) for k in values}, values, request)
    return amendment


@transaction.atomic
def cancel_unfunded_contract(contract_id, actor, reason, request=None):
    guard(actor, request, sensitive=True)
    reason = reason_required(reason, 10)
    contract = Contract.objects.select_for_update().get(pk=contract_id)
    if contract.status not in {"draft", "customer_accepted", "freelancer_accepted", "awaiting_funding"} or contract.funded_at or contract.escrow_amount:
        raise ValidationError("Отмена доступна только до финансирования по отдельному обоснованному сценарию.")
    before = {"status": contract.status, "version": contract.version}
    contract.status = "cancelled"
    contract.save(update_fields=["status"])
    from ..escrow import project_status
    project_status(contract, "cancelled")
    event(contract, actor, "admin_unfunded_cancellation", "Администрация отменила договор до финансирования: " + reason)
    audit(actor, "contract_cancel_unfunded", contract, reason, before, {"status": "cancelled"}, request)
    return contract


@transaction.atomic
def revoke_account_credential(user_id, kind, credential_id, actor, reason, request=None):
    guard(actor, request, sensitive=True)
    reason = reason_required(reason)
    user = get_user_model().objects.select_for_update().get(pk=user_id)
    if kind == "session":
        from django.contrib.sessions.models import Session
        row = BrowserSession.objects.filter(user=user, pk=credential_id).first()
        if not row:
            raise ValidationError("Сессия не принадлежит пользователю.")
        Session.objects.filter(session_key=row.session_key).delete()
        BrowserSession.objects.filter(pk=row.pk, revoked_at__isnull=True).update(revoked_at=timezone.now())
    elif kind == "token":
        if credential_id == "legacy":
            from rest_framework.authtoken.models import Token
            Token.objects.filter(user=user).delete()
        else:
            row = ScopedApiToken.objects.filter(user=user, pk=credential_id).first()
            if not row:
                raise ValidationError("Токен не принадлежит пользователю.")
            ScopedApiToken.objects.filter(pk=row.pk, revoked_at__isnull=True).update(revoked_at=timezone.now())
    else:
        raise ValidationError("Неизвестный способ авторизации.")
    audit(actor, "user_revoke_" + kind, user, reason, after={"credential_id": str(credential_id), "revoked": True}, request=request)
    return user


def initiate_account_recovery(user_id, actor, reason, request=None, channel="email"):
    """Invoke the normal reset flow without revealing codes or altering MFA."""
    guard(actor, request, sensitive=True)
    reason = reason_required(reason, 10)
    user = get_user_model().objects.get(pk=user_id)
    if not user.is_active:
        raise ValidationError("Сначала завершите проверку блокировки и восстановите доступ аккаунта.")
    if channel not in {"email", "phone"}:
        raise ValidationError("Выберите email или телефон.")
    identifier = user.email if channel == "email" else getattr(getattr(user, "profile", None), "phone", "")
    if not identifier:
        raise ValidationError("У пользователя не указан контакт для этого канала.")
    from types import SimpleNamespace
    from ..auth_views import PasswordResetRequestView
    response = PasswordResetRequestView().post(SimpleNamespace(data={"identifier": identifier}))
    if response.status_code != 200:
        raise ValidationError(response.data.get("detail", "Штатное восстановление временно недоступно."))
    audit(actor, "user_recovery_requested", user, reason, after={"channel": channel, "result": "standard_recovery_requested", "mfa_preserved": True}, request=request)
    return user


@transaction.atomic
def resolve_obligation(obligation_id, actor, reason, request=None):
    guard(actor, request)
    reason = reason_required(reason, 10)
    obligation = AdminObligation.objects.select_for_update().get(pk=obligation_id)
    if obligation.status == "resolved":
        return obligation
    model, terminal = {"contract": (Contract, {"completed", "cancelled"}),
                       "withdrawal": (Withdrawal, {"paid", "rejected", "cancelled"})}.get(obligation.object_type, (None, set()))
    if model is None:
        raise ValidationError("Неизвестный вид обязательства; требуется проверка истории.")
    linked = model.objects.filter(pk=obligation.object_id).first()
    if not linked or linked.status not in terminal:
        raise ValidationError("Обязательство ещё не завершено. Сначала проверьте договор или фактический исход вывода.")
    if obligation.object_type == "contract" and linked.escrow_amount:
        raise ValidationError("Договор сохраняет резерв; сначала завершите проверку расчётов.")
    obligation.status, obligation.resolved_at = "resolved", timezone.now()
    obligation.save(update_fields=["status", "resolved_at"])
    audit(actor, "obligation_resolved", obligation, reason, {"status": "open"}, {"status": "resolved", "linked_status": linked.status}, request)
    return obligation


@transaction.atomic
def save_catalogue(kind, object_id, changes, actor, reason, request=None):
    guard(actor, request)
    reason = reason_required(reason)
    from ..models import CategorySkill, SkillAlias
    models = {"category": Category, "skill": Skill, "alias": SkillAlias, "categoryskill": CategorySkill}
    allowed = {"category": {"name", "slug", "labels", "active", "sort_order", "icon_key"},
        "skill": {"name", "slug", "labels", "active"}, "alias": {"key", "skill_id"},
        "categoryskill": {"category_id", "skill_id", "sort_order"}}
    if kind not in models or not changes or set(changes) - allowed[kind]:
        raise ValidationError("Недопустимые данные справочника.")
    obj = models[kind].objects.select_for_update().get(pk=object_id) if object_id else models[kind]()
    before = {k: getattr(obj, k) for k in changes}
    for key, value in changes.items():
        if key == "active":
            value = serializers.BooleanField().run_validation(value)
        setattr(obj, key, value)
    if kind in {"alias", "categoryskill"} and not Skill.objects.filter(pk=obj.skill_id, active=True, merged_into__isnull=True).exists():
        raise ValidationError("Выберите активный канонический навык.")
    if kind == "skill" and not obj.slug:
        from ..taxonomy import skill_slug
        obj.slug = skill_slug(obj.name)
    obj.full_clean(exclude=["normalized_name"] if kind == "skill" else None)
    try:
        with transaction.atomic():
            obj.save()
    except IntegrityError:
        raise Conflict("Запись каталога с таким именем, адресом или связью уже создана. Обновите список.")
    audit(actor, "catalogue_save", obj, reason, before, {k: getattr(obj, k) for k in changes}, request)
    return obj


def _execute_command(request, action, object_id, data):
    """Single entry point for the HTML panel; public APIs never invoke it."""
    actor, reason = request.user, data.get("reason", "")
    common = {"actor": actor, "request": request}
    if data.get("expected_state"):
        model = {"user": get_user_model(), "project": Project, "review": Review, "dispute": Dispute,
            "support": SupportTicket, "verification": SkillVerification, "report": ContentReport,
            "proposal_report": ProposalReport, "skill": Skill, "contract": Contract}.get(action.split(".")[0])
        if action == "catalogue.save":
            model = Category if data.get("kind") == "category" else Skill
        if model:
            obj = model.objects.select_for_update().get(pk=object_id)
            if state_fingerprint(obj) != data["expected_state"]:
                raise Conflict("Карточка изменилась после открытия формы. Обновите её и сравните изменения заново.")
    if action == "user.block":
        result = block_user(object_id, reason=reason, **common)
    elif action == "user.unblock":
        result = unblock_user(object_id, reason=reason, **common)
    elif action == "user.edit":
        result = edit_user(object_id, data.get("changes", {}), reason=reason, **common)
    elif action == "user.restore":
        guard(actor, request)
        reason = reason_required(reason)
        profile = Profile.objects.get(user_id=object_id, user__is_active=True)
        before = {"public_hidden": profile.public_hidden}
        profile.public_hidden = False
        profile.save(update_fields=["public_hidden"])
        decision(profile, actor, "profile_restore", reason, before, {"public_hidden": False}, request)
        result = profile
    elif action == "user.revoke_sessions":
        guard(actor, request, sensitive=True)
        reason = reason_required(reason)
        from ..security import revoke_user_sessions
        result = get_user_model().objects.get(pk=object_id)
        revoke_user_sessions(result)
        ScopedApiToken.objects.filter(user=result, revoked_at__isnull=True).update(revoked_at=timezone.now())
        from rest_framework.authtoken.models import Token
        Token.objects.filter(user=result).delete()
        audit(actor, "user_revoke_sessions", result, reason, request=request)
    elif action in {"user.revoke_session", "user.revoke_token"}:
        result = revoke_account_credential(object_id, "session" if action.endswith("session") else "token", data.get("credential_id"), reason=reason, **common)
    elif action == "user.recovery":
        result = initiate_account_recovery(object_id, reason=reason, channel=data.get("channel", "email"), **common)
    elif action == "project.moderate":
        result = moderate_project(object_id, data.get("status"), reason=reason, expected_version=data.get("expected_version"), **common)
    elif action == "project.edit":
        result = edit_project(object_id, data.get("changes", {}), reason=reason, **common)
    elif action == "review.moderate":
        result = moderate_review(object_id, data.get("published"), reason=reason, **common)
    elif action == "message.moderate":
        result = moderate_message(object_id, data.get("message_id"), data.get("proposal") is True, data.get("hidden"), reason=reason, **common)
    elif action == "dispute.transition":
        result = transition_dispute(object_id, data.get("status"), reason=reason, **common)
    elif action == "dispute.note":
        result = add_dispute_note(object_id, text=data.get("text", reason), recipient=data.get("recipient"), **common)
    elif action == "dispute.preview":
        result = preview_dispute(object_id, data.get("gross"), reason=reason, **common)
        return {"id": str(result.pk), "snapshot": result.snapshot, "expires_at": result.expires_at.isoformat()}
    elif action == "dispute.resolve":
        return execute_dispute(data.get("preview_id"), data.get("idempotency_key"), confirmed=data.get("confirmed") is True, **common)
    elif action in {"report.review", "proposal_report.review"}:
        result = review_report(object_id, data.get("status"), reason=reason, proposal=action.startswith("proposal"), **common)
    elif action == "support.reply":
        result = reply_support(object_id, data.get("text"), status=data.get("status"), **common)
    elif action == "support.convert":
        result = convert_support(object_id, reason=reason, **common)
    elif action == "verification.decide":
        expiry = serializers.DateTimeField().run_validation(data["expires_at"]) if data.get("expires_at") else None
        result = decide_verification(object_id, data.get("status"), reason=reason, expires_at=expiry, **common)
    elif action == "skill.merge":
        result = merge_catalogue_skill(object_id, data.get("target_id"), reason=reason, **common)
    elif action == "contract.amend":
        result = propose_admin_amendment(object_id, data.get("changes", {}), reason=reason, **common)
    elif action == "contract.cancel":
        result = cancel_unfunded_contract(object_id, reason=reason, **common)
    elif action == "obligation.resolve":
        result = resolve_obligation(object_id, reason=reason, **common)
    elif action == "catalogue.save":
        result = save_catalogue(data.get("kind"), object_id, data.get("changes", {}), reason=reason, **common)
    else:
        raise ValidationError("Неизвестное административное действие.")
    return {"id": str(result.pk), "status": str(getattr(result, "status", "success"))}


@transaction.atomic
def execute_command(request, action, object_id, data):
    """Repeat a submitted UUID safely, including after the original response is lost."""
    guard(request.user, request, sensitive=action in {"user.block", "user.unblock", "user.revoke_sessions", "dispute.resolve"})
    if action in {"dispute.resolve", "dispute.preview"} or not data.get("idempotency_key"):
        return _execute_command(request, action, object_id, data)
    try:
        operation_key = uuid.UUID(str(data["idempotency_key"]))
    except (TypeError, ValueError):
        raise ValidationError("Укажите постоянный UUID операции.")
    payload_hash = hashlib.sha256(json.dumps({"action": action, "id": str(object_id), "data": data}, sort_keys=True, default=str).encode()).hexdigest()
    operation, created = AdminCommand.objects.get_or_create(id=operation_key, defaults={"actor": request.user, "action": action, "request_hash": payload_hash})
    if not created:
        if operation.actor_id != request.user.pk or operation.action != action or operation.request_hash != payload_hash:
            raise Conflict("Ключ уже использован для другого действия.")
        return operation.result
    result = _execute_command(request, action, object_id, data)
    operation.result = result
    operation.save(update_fields=["result"])
    return result
