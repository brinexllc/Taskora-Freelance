from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from pathlib import Path

from django.db import connection, transaction
from django.db.models import Count, Q, Sum
from django.http import FileResponse
from django.utils import timezone
from rest_framework import filters, permissions, viewsets, serializers
from rest_framework.decorators import action, api_view, permission_classes, authentication_classes
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import Contract, Deliverable, Profile, Project, Proposal, Message, Dispute, Review, Notification, Category, Skill, ProjectAttachment, WalletEntry
from .serializers import ContractSerializer, DeliverableUploadSerializer, ProjectSerializer, ProposalSerializer, MessageSerializer, MessageUploadSerializer, DisputeSerializer, ReviewSerializer, NotificationSerializer, AttachmentSerializer
from .escrow import event, notify, fund_contract, distribute, project_status, resolve_dispute
from .validation import uploaded_file


def require_role(user, role):
    if not user.is_authenticated or not hasattr(user, "profile") or user.profile.role != role:
        raise PermissionDenied("Выберите подходящую роль в настройках: " + ("Заказчик" if role == "client" else "Фрилансер"))


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "description", "skills__name", "client_name", "client_company"]
    ordering_fields = ["created_at", "budget_min", "budget_max"]
    ordering = ["-featured", "-created_at"]

    def get_queryset(self):
        qs = Project.objects.select_related("contract").prefetch_related("attachments", "skills").annotate(proposal_count=Count("proposals", distinct=True))
        user = self.request.user
        public = Q(status=Project.Status.ACTIVE)
        if user.is_authenticated:
            public |= Q(owner=user) | Q(contract__freelancer=user)
        qs = qs.filter(public)
        if self.action == "list":
            if self.request.query_params.get("mine") == "1":
                qs = qs.filter(owner=user) if user.is_authenticated else qs.none()
            else:
                qs = qs.filter(status=Project.Status.ACTIVE)
            if self.request.query_params.get("category"):
                qs = qs.filter(category=self.request.query_params["category"])
            params = self.request.query_params
            for key, lookup in [("min_budget", "budget_max__gte"), ("max_budget", "budget_min__lte")]:
                if params.get(key):
                    qs = qs.filter(**{lookup: serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0).run_validation(params[key])})
            if params.get("skill"):
                qs = qs.filter(skills__name__iexact=params["skill"])
            if params.get("budget_type"):
                qs = qs.filter(budget_type=params["budget_type"])
            if params.get("deadline"):
                qs = qs.filter(deadline__lte=serializers.DateField().run_validation(params["deadline"]))
            if params.get("status") and params.get("mine") == "1":
                qs = qs.filter(status=params["status"])
        return qs.distinct()

    @transaction.atomic
    def perform_create(self, serializer):
        require_role(self.request.user, "client")
        serializer.save(owner=self.request.user, client_name=self.request.user.profile.full_name, status=Project.Status.DRAFT)

    @transaction.atomic
    def perform_update(self, serializer):
        project = Project.objects.select_for_update().get(pk=serializer.instance.pk)
        if project.owner_id != self.request.user.id:
            raise PermissionDenied("Изменять заказ может только его владелец.")
        if project.status not in {Project.Status.ACTIVE, Project.Status.DRAFT} or project.proposals.exists():
            raise ValidationError("Заказ с откликами или договором уже нельзя изменять.")
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        project = Project.objects.select_for_update().get(pk=instance.pk)
        if project.owner_id != self.request.user.id:
            raise PermissionDenied("Удалять заказ может только его владелец.")
        if project.status not in {Project.Status.ACTIVE, Project.Status.DRAFT} or project.proposals.exists():
            raise ValidationError("Заказ с откликами или договором нельзя удалить.")
        project.status = Project.Status.CANCELLED
        project.save(update_fields=["status", "updated_at"])

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def publish(self, request, pk=None):
        project = Project.objects.select_for_update().get(pk=self.get_object().pk)
        if project.owner_id != request.user.id:
            raise PermissionDenied("Публикует только заказчик.")
        if project.status != Project.Status.DRAFT:
            raise ValidationError("Публиковать можно только черновик.")
        if not project.deadline or project.deadline < timezone.localdate() or not project.skills.exists():
            raise ValidationError("Заполните срок и навыки перед публикацией.")
        project.status = Project.Status.ACTIVE
        project.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(project).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def attachments(self, request, pk=None):
        project = Project.objects.select_for_update().get(pk=self.get_object().pk)
        if project.owner_id != request.user.id:
            raise PermissionDenied("Вложения добавляет заказчик.")
        if project.status != Project.Status.DRAFT or project.attachments.count() >= 5:
            raise ValidationError("До 5 файлов можно добавить в черновик.")
        file = serializers.FileField().run_validation(request.data.get("file"))
        uploaded_file(file)
        attachment = ProjectAttachment.objects.create(project=project, file=file, filename=Path(file.name.replace("\\", "/")).name[:255])
        return Response(AttachmentSerializer(attachment).data, status=201)

    @action(detail=True, methods=["get"], url_path="attachments/(?P<attachment_id>[0-9]+)/download")
    def attachment_download(self, request, pk=None, attachment_id=None):
        project = self.get_object()
        attachment = project.attachments.filter(pk=attachment_id).first()
        if not attachment:
            return Response(status=404)
        return private_response(attachment.file, attachment.filename)



class ProposalViewSet(viewsets.ModelViewSet):
    serializer_class = ProposalSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = Proposal.objects.select_related("project", "contract").filter(Q(freelancer=self.request.user) | Q(project__owner=self.request.user))
        if self.request.query_params.get("mine") == "1":
            qs = qs.filter(freelancer=self.request.user)
        if self.request.query_params.get("project"):
            qs = qs.filter(project_id=self.request.query_params["project"])
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        require_role(user, "freelancer")
        project = Project.objects.select_for_update().get(pk=serializer.validated_data["project"].pk)
        if project.owner_id == user.id:
            raise ValidationError("Нельзя откликнуться на собственный заказ.")
        if project.status != Project.Status.ACTIVE or not project.owner_id:
            raise ValidationError("Этот заказ не принимает отклики.")
        if Proposal.objects.filter(project=project, freelancer=user).exists():
            raise ValidationError("Вы уже отправили отклик на этот заказ.")
        serializer.save(freelancer=user, freelancer_name=user.profile.full_name, freelancer_email=user.email)
        notify(project.owner_id, "proposal", "Новый отклик: " + project.title, link=f"/projects/{project.pk}")

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def accept(self, request, pk=None):
        proposal = self.get_object()
        project = Project.objects.select_for_update().get(pk=proposal.project_id)
        proposal.refresh_from_db()
        if project.owner_id != request.user.id:
            raise PermissionDenied("Выбирать исполнителя может только заказчик.")
        if project.status != Project.Status.ACTIVE or proposal.status != Proposal.Status.PENDING or not proposal.freelancer_id:
            raise ValidationError("Отклик уже обработан или заказ закрыт.")
        terms = (
            f"Договор Taskora по заказу №{project.pk}: {project.title}\n\n"
            f"Заказчик: {request.user.profile.full_name} (@{request.user.username}).\n"
            f"Исполнитель: {proposal.freelancer_name} (@{proposal.freelancer.username}).\n"
            f"Предмет: {project.description}\n\nПредложение исполнителя: {proposal.cover_letter}\n\n"
            f"Стоимость: {proposal.amount} UZS. Срок: {proposal.delivery_days} дней с момента резервирования средств.\n\n"
            "Исполнитель передаёт файл результата и отдельные материалы для предварительного просмотра. "
            "Заказчик проверяет результат и может запросить доработку. Исходный файл доступен заказчику после приёмки результата и выплаты исполнителю. "
            "Работа начинается после резервирования суммы заказа. При приёмке резерв выплачивается исполнителю за вычетом комиссии. "
            "До резервирования любая сторона может отменить договор; после — возврат и распределение средств возможны по решению администратора в споре. "
            "Договор и заказ сохраняются в истории.\n\n"
            "Нажимая «Подписать», стороны подтверждают эти условия в своём аккаунте Taskora. "
            "Подтверждение в аккаунте не является электронной цифровой подписью ONEID или E-IMZO."
        )
        fee_percent = Decimal(settings.PLATFORM_FEE_PERCENT)
        if not fee_percent.is_finite() or not 0 <= fee_percent <= 100:
            raise ValidationError("Некорректная комиссия платформы.")
        fee = (proposal.amount * fee_percent / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        terms += f"\nВерсия 1. Модель: {project.budget_type}. Согласованная итоговая сумма: {proposal.amount} UZS. Комиссия: {fee_percent}% ({fee} UZS), удерживается из выплаты. Исполнителю: {proposal.amount-fee} UZS."
        contract = Contract.objects.create(project=project, proposal=proposal, customer=request.user, freelancer=proposal.freelancer, amount=proposal.amount, delivery_days=proposal.delivery_days, terms=terms, scope=project.description, budget_type=project.budget_type, fee_percent=fee_percent, fee_amount=fee)
        event(contract, request.user, "created", "Договор создан. Подтвердите условия.", {"version": 1, "terms": terms})
        for other in Proposal.objects.filter(project=project, status="pending").exclude(pk=proposal.pk):
            notify(other.freelancer_id, "proposal_rejected", "Выбран другой исполнитель: " + project.title, link=f"/projects/{project.pk}")
        Proposal.objects.filter(project=project, status="pending").exclude(pk=proposal.pk).update(status=Proposal.Status.REJECTED)
        proposal.status = Proposal.Status.ACCEPTED
        proposal.save(update_fields=["status"])
        project.status = Project.Status.CONTRACTING
        project.save(update_fields=["status", "updated_at"])
        return Response(ContractSerializer(contract, context={"request": request}).data, status=201)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def reject(self, request, pk=None):
        proposal = self.get_object()
        Project.objects.select_for_update().get(pk=proposal.project_id)
        proposal.refresh_from_db()
        if proposal.project.owner_id != request.user.id:
            raise PermissionDenied("Отклонять отклик может только заказчик.")
        if proposal.status != Proposal.Status.PENDING:
            raise ValidationError("Отклик уже обработан.")
        proposal.status = Proposal.Status.REJECTED
        proposal.save(update_fields=["status"])
        notify(proposal.freelancer_id, "proposal_rejected", "Отклик отклонён: " + proposal.project.title, link=f"/projects/{proposal.project_id}")
        return Response(self.get_serializer(proposal).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def withdraw(self, request, pk=None):
        proposal = self.get_object()
        Project.objects.select_for_update().get(pk=proposal.project_id)
        proposal.refresh_from_db()
        if proposal.freelancer_id != request.user.id:
            raise PermissionDenied("Можно отозвать только свой отклик.")
        if proposal.status != Proposal.Status.PENDING:
            raise ValidationError("Отклик уже обработан.")
        proposal.status = Proposal.Status.WITHDRAWN
        proposal.save(update_fields=["status"])
        return Response(self.get_serializer(proposal).data)


class ContractViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ContractSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Contract.objects.filter(Q(customer=self.request.user) | Q(freelancer=self.request.user)).select_related("project", "customer__profile", "freelancer__profile").prefetch_related("deliverables", "events", "reviews__author__profile").select_related("dispute")
        if self.action == "list":
            selected_status = self.request.query_params.get("status")
            if selected_status == "active":
                qs = qs.exclude(status__in=[Contract.Status.COMPLETED, Contract.Status.CANCELLED])
            elif selected_status == "completed":
                qs = qs.filter(status=Contract.Status.COMPLETED)
        return qs

    def locked(self):
        return Contract.objects.select_for_update().get(pk=self.get_object().pk)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def sign(self, request, pk=None):
        contract = self.locked()
        if request.data.get("accepted") is not True:
            raise ValidationError("Подтвердите согласие с условиями договора.")
        if contract.status not in {Contract.Status.SIGNING, Contract.Status.CUSTOMER_ACCEPTED, Contract.Status.FREELANCER_ACCEPTED}:
            raise ValidationError("Договор уже подписан.")
        field = "customer_signed_at" if request.user.id == contract.customer_id else "freelancer_signed_at"
        if not getattr(contract, field):
            setattr(contract, field, timezone.now())
        if contract.customer_signed_at and contract.freelancer_signed_at:
            contract.status = Contract.Status.AWAITING_FUNDING
        else:
            contract.status = Contract.Status.CUSTOMER_ACCEPTED if contract.customer_signed_at else Contract.Status.FREELANCER_ACCEPTED
        contract.save()
        event(contract, request.user, "signed", "Условия подтверждены. " + ("Необходимо зарезервировать средства." if contract.status == Contract.Status.AWAITING_FUNDING else "Ожидается вторая сторона."))
        return Response(self.get_serializer(contract).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def submit(self, request, pk=None):
        contract = self.locked()
        if request.user.id != contract.freelancer_id:
            raise PermissionDenied("Результат загружает исполнитель.")
        if contract.status != Contract.Status.ACTIVE:
            raise ValidationError("Сдача доступна в активном договоре после резервирования средств или запроса доработки.")
        serializer = DeliverableUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        filename = Path(data["file"].name.replace("\\", "/")).name[:255]
        Deliverable.objects.create(contract=contract, filename=filename, **data)
        contract.status = Contract.Status.REVIEW
        contract.save(update_fields=["status"])
        project_status(contract, "review")
        event(contract, request.user, "submitted", "Работа отправлена на проверку.")
        return Response(self.get_serializer(contract).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def revision(self, request, pk=None):
        contract = self.locked()
        if request.user.id != contract.customer_id:
            raise PermissionDenied("Доработку запрашивает заказчик.")
        if contract.status != Contract.Status.REVIEW:
            raise ValidationError("Работа ещё не отправлена на проверку.")
        if contract.payments.filter(status__in=["pending", "prepared"]).exists():
            raise ValidationError("Сначала отмените ожидающий платёж в кошельке.")
        note = str(request.data.get("note", "")).strip()
        if not note or len(note) > 3000:
            raise ValidationError("Опишите необходимые доработки (до 3000 символов).")
        deliverable = contract.deliverables.first()
        deliverable.revision_note = note
        deliverable.save(update_fields=["revision_note"])
        contract.status = Contract.Status.ACTIVE
        contract.save(update_fields=["status"])
        project_status(contract, "in_progress")
        event(contract, request.user, "revision", "Запрошена доработка: " + note)
        return Response(self.get_serializer(contract).data)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        contract = self.get_object()
        if contract.status != Contract.Status.COMPLETED:
            raise PermissionDenied("Скачивание откроется после подтверждённой оплаты.")
        work = contract.deliverables.first()
        if not work:
            raise ValidationError("Файл результата отсутствует.")
        try:
            response = FileResponse(work.file.open("rb"), as_attachment=True, filename=work.filename, content_type="application/octet-stream")
        except FileNotFoundError:
            return Response({"detail": "Файл временно недоступен. Обратитесь в поддержку."}, status=503)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def fund(self, request, pk=None):
        contract = self.locked()
        if request.user.id != contract.customer_id:
            raise PermissionDenied("Средства резервирует заказчик.")
        if request.data.get("confirmed") is not True:
            raise ValidationError("Подтвердите резервирование указанной суммы.")
        fund_contract(contract, request.user)
        return Response(self.get_serializer(contract).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def accept(self, request, pk=None):
        contract = self.locked()
        if request.user.id != contract.customer_id:
            raise PermissionDenied("Работу принимает заказчик.")
        if request.data.get("confirmed") is not True:
            raise ValidationError("Подтвердите приёмку и выплату.")
        if contract.status == Contract.Status.COMPLETED:
            return Response(self.get_serializer(contract).data)
        if contract.status != Contract.Status.REVIEW or not contract.deliverables.exists():
            raise ValidationError("Принять можно работу на проверке без открытого спора.")
        distribute(contract, request.user, contract.amount, "Работа принята. Средства выплачены исполнителю.")
        return Response(self.get_serializer(contract).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def cancel(self, request, pk=None):
        contract = self.locked()
        if request.data.get("confirmed") is not True:
            raise ValidationError("Подтвердите отмену договора.")
        if contract.status not in {"draft", "customer_accepted", "freelancer_accepted", "awaiting_funding"}:
            raise ValidationError("После резервирования средств отмена возможна через спор.")
        if contract.payments.filter(status__in=["pending", "prepared"]).exists():
            raise ValidationError("Сначала дождитесь обработки или отмены платежа.")
        contract.status = Contract.Status.CANCELLED
        contract.save(update_fields=["status"])
        project_status(contract, "cancelled")
        event(contract, request.user, "cancelled", "Договор отменён до резервирования средств.")
        return Response(self.get_serializer(contract).data)

    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        contract = self.get_object()
        if request.method == "POST":
            serializer = MessageUploadSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                contract = self.locked()
                if contract.status in {"completed", "cancelled"}:
                    raise ValidationError("Чат завершённого договора доступен для чтения.")
                data = serializer.validated_data
                filename = Path(data["file"].name.replace("\\", "/")).name[:255] if data.get("file") else ""
                message = Message.objects.create(contract=contract, sender=request.user, filename=filename, **data)
                recipient = contract.freelancer_id if request.user.id == contract.customer_id else contract.customer_id
                notify(recipient, "message", "Новое сообщение по договору №" + str(contract.pk), contract)
            return Response(MessageSerializer(message).data, status=201)
        qs = contract.messages.all()
        if request.query_params.get("after"):
            qs = qs.filter(pk__gt=serializers.IntegerField(min_value=0).run_validation(request.query_params["after"]))
        return self.get_paginated_response(MessageSerializer(self.paginate_queryset(qs), many=True).data)

    @action(detail=True, methods=["post"], url_path="messages/read")
    def messages_read(self, request, pk=None):
        contract = self.get_object()
        contract.messages.filter(read_at__isnull=True, system=False).exclude(sender=request.user).update(read_at=timezone.now())
        return Response({"ok": True})

    @action(detail=True, methods=["get"], url_path="messages/(?P<message_id>[0-9]+)/download")
    def message_download(self, request, pk=None, message_id=None):
        message = self.get_object().messages.filter(pk=message_id).first()
        if not message or not message.file:
            return Response(status=404)
        return private_response(message.file, message.filename)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def dispute(self, request, pk=None):
        contract = self.locked()
        if contract.status not in {Contract.Status.ACTIVE, Contract.Status.REVIEW}:
            raise ValidationError("Спор доступен по работающему договору или работе на проверке.")
        if request.data.get("confirmed") is not True:
            raise ValidationError("Подтвердите открытие спора и блокировку выплаты.")
        reason = serializers.CharField(min_length=10, max_length=5000).run_validation(request.data.get("reason"))
        Dispute.objects.create(contract=contract, opened_by=request.user, reason=reason)
        contract.status = Contract.Status.DISPUTED
        contract.save(update_fields=["status"])
        project_status(contract, "disputed")
        event(contract, request.user, "dispute_opened", "Открыт спор. Средства остаются в резерве. " + reason)
        return Response(self.get_serializer(contract).data, status=201)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def review(self, request, pk=None):
        contract = self.locked()
        if contract.status != Contract.Status.COMPLETED:
            raise ValidationError("Отзывы доступны после завершения договора.")
        if contract.reviews.filter(author=request.user).exists():
            raise ValidationError("Вы уже оставили отзыв.")
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_id = contract.freelancer_id if request.user.id == contract.customer_id else contract.customer_id
        serializer.save(contract=contract, author=request.user, target_id=target_id)
        notify(target_id, "review", "Получен отзыв по договору №" + str(contract.pk), contract)
        return Response(serializer.data, status=201)


def private_response(file, filename):
    try:
        response = FileResponse(file.open("rb"), as_attachment=True, filename=filename, content_type="application/octet-stream")
    except FileNotFoundError:
        return Response({"detail": "Файл временно недоступен."}, status=503)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        return qs.filter(read_at__isnull=True) if self.request.query_params.get("unread") == "1" else qs

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        item = self.get_object()
        item.read_at = timezone.now()
        item.save(update_fields=["read_at"])
        return Response(self.get_serializer(item).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        request.user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({"ok": True})


class DisputeViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DisputeSerializer

    def get_queryset(self):
        qs = Dispute.objects.select_related("contract").order_by("-created_at")
        if not self.request.user.is_staff:
            qs = qs.filter(Q(contract__customer=self.request.user) | Q(contract__freelancer=self.request.user))
        return qs

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        if not request.user.is_staff:
            raise PermissionDenied("Решение принимает администратор.")
        dispute = self.get_object()
        amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0).run_validation(request.data.get("freelancer_amount"))
        reason = serializers.CharField(min_length=10, max_length=5000).run_validation(request.data.get("reason"))
        return Response(self.get_serializer(resolve_dispute(dispute.pk, request.user, amount, reason)).data)


@api_view(["GET"])
def directory(request):
    return Response({"categories": list(Category.objects.filter(active=True).values("slug", "name")), "skills": list(Skill.objects.filter(active=True).order_by("name").values_list("name", flat=True))})


@api_view(["GET"])
def profile_reviews(request, pk):
    from .pagination import ProjectPagination
    qs = Review.objects.filter(target__profile__pk=pk, target__is_active=True, published=True)
    paginator = ProjectPagination()
    return paginator.get_paginated_response(ReviewSerializer(paginator.paginate_queryset(qs, request), many=True).data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def dashboard(request):
    user = request.user
    contracts = Contract.objects.filter(Q(customer=user) | Q(freelancer=user))
    active = contracts.exclude(status__in=["completed", "cancelled"])
    total = lambda qs: str(qs.aggregate(value=Sum("escrow_amount"))["value"] or 0)
    return Response({"active_orders": user.projects.exclude(status__in=["completed", "cancelled"]).count(),
        "active_contracts": active.count(), "completed_orders": contracts.filter(status="completed").count(),
        "completed_contracts": contracts.filter(status="completed").count(), "proposals": user.proposals.count(),
        "new_proposals": Proposal.objects.filter(project__owner=user, status="pending").count(),
        "in_review": contracts.filter(status=Contract.Status.REVIEW).count(),
        "unread_messages": Message.objects.filter(contract__in=contracts, system=False, read_at__isnull=True).exclude(sender=user).count(),
        "unread_notifications": user.notifications.filter(read_at__isnull=True).count(),
        "balance": str(user.profile.balance), "frozen_balance": total(contracts.filter(customer=user)),
        "pending_balance": total(contracts.filter(freelancer=user))})


@api_view(["GET"])
def api_root(request):
    return Response({"name": "Taskora API", "version": "1.0", "projects": request.build_absolute_uri("projects/"), "profiles": request.build_absolute_uri("profiles/"), "health": request.build_absolute_uri("health/")})


@api_view(["GET"])
def overview(request):
    return Response({"active_projects": Project.objects.filter(status=Project.Status.ACTIVE).count(), "freelancers": Profile.objects.filter(role="freelancer", user__is_active=True).count(), "completed_projects": Project.objects.filter(status="completed").count(), "proposals_this_week": Proposal.objects.filter(created_at__gte=timezone.now() - timedelta(days=7)).count()})


@api_view(["GET"])
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return Response({"status": "error", "database": "unavailable"}, status=503)
    return Response({"status": "ok", "database": "connected"})


@api_view(["GET"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([permissions.IsAdminUser])
def admin_file_download(request, model, pk):
    from django.shortcuts import get_object_or_404
    from .models import AuditLog
    types = {"message": Message, "deliverable": Deliverable, "projectattachment": ProjectAttachment}
    if model not in types:
        return Response(status=404)
    if not request.user.has_perm("marketplace.view_" + model):
        raise PermissionDenied("Недостаточно прав для просмотра материалов.")
    obj = get_object_or_404(types[model], pk=pk)
    if not obj.file:
        return Response(status=404)
    AuditLog.objects.create(actor=request.user, action="admin_file_download", object_type=model, object_id=str(pk))
    return private_response(obj.file, obj.filename)
