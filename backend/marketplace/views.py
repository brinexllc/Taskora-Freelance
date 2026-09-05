from datetime import timedelta
from pathlib import Path

from django.db import connection, transaction
from django.db.models import Count, Q
from django.http import FileResponse
from django.utils import timezone
from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import Contract, Deliverable, Profile, Project, Proposal
from .serializers import ContractSerializer, DeliverableUploadSerializer, ProjectSerializer, ProposalSerializer


def require_role(user, role):
    if not user.is_authenticated or not hasattr(user, "profile") or user.profile.role != role:
        raise PermissionDenied("Выберите подходящую роль в настройках: " + ("Заказчик" if role == "client" else "Фрилансер"))


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "description", "skills", "client_name", "client_company"]
    ordering_fields = ["created_at", "budget_min", "budget_max"]
    ordering = ["-featured", "-created_at"]

    def get_queryset(self):
        qs = Project.objects.select_related("contract").annotate(proposal_count=Count("proposals"))
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
        return qs

    def perform_create(self, serializer):
        require_role(self.request.user, "client")
        serializer.save(owner=self.request.user, client_name=self.request.user.profile.full_name, status=Project.Status.ACTIVE)

    @transaction.atomic
    def perform_update(self, serializer):
        project = Project.objects.select_for_update().get(pk=serializer.instance.pk)
        if project.owner_id != self.request.user.id:
            raise PermissionDenied("Изменять заказ может только его владелец.")
        if project.status != Project.Status.ACTIVE or project.proposals.exists():
            raise ValidationError("Заказ с откликами или договором уже нельзя изменять.")
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        project = Project.objects.select_for_update().get(pk=instance.pk)
        if project.owner_id != self.request.user.id:
            raise PermissionDenied("Удалять заказ может только его владелец.")
        if project.status != Project.Status.ACTIVE or project.proposals.exists():
            raise ValidationError("Заказ с откликами или договором нельзя удалить.")
        project.delete()


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
            f"Стоимость: {proposal.amount} UZS. Срок: {proposal.delivery_days} дней с момента подтверждения обеими сторонами.\n\n"
            "Исполнитель передаёт файл результата и отдельные материалы для предварительного просмотра. "
            "Заказчик проверяет результат и может запросить доработку. Исходный файл доступен заказчику после подтверждённой оплаты. "
            "После оплаты договор и заказ закрываются и сохраняются в личной истории сторон.\n\n"
            "Нажимая «Подписать», стороны подтверждают эти условия в своём аккаунте Taskora. "
            "Подтверждение в аккаунте не является электронной цифровой подписью ONEID или E-IMZO."
        )
        contract = Contract.objects.create(project=project, proposal=proposal, customer=request.user, freelancer=proposal.freelancer, amount=proposal.amount, delivery_days=proposal.delivery_days, terms=terms)
        Proposal.objects.filter(project=project).exclude(pk=proposal.pk).update(status=Proposal.Status.REJECTED)
        proposal.status = Proposal.Status.ACCEPTED
        proposal.save(update_fields=["status"])
        project.status = Project.Status.IN_PROGRESS
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
        return Response(self.get_serializer(proposal).data)


class ContractViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ContractSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Contract.objects.filter(Q(customer=self.request.user) | Q(freelancer=self.request.user)).select_related("project", "customer__profile", "freelancer__profile").prefetch_related("deliverables")
        if self.action == "list":
            selected_status = self.request.query_params.get("status")
            if selected_status == "active":
                qs = qs.exclude(status=Contract.Status.COMPLETED)
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
        if contract.status != Contract.Status.SIGNING:
            raise ValidationError("Договор уже подписан.")
        field = "customer_signed_at" if request.user.id == contract.customer_id else "freelancer_signed_at"
        if not getattr(contract, field):
            setattr(contract, field, timezone.now())
        if contract.customer_signed_at and contract.freelancer_signed_at:
            contract.status = Contract.Status.ACTIVE
        contract.save()
        return Response(self.get_serializer(contract).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def submit(self, request, pk=None):
        contract = self.locked()
        if request.user.id != contract.freelancer_id:
            raise PermissionDenied("Результат загружает исполнитель.")
        if contract.status != Contract.Status.ACTIVE:
            raise ValidationError("Сдача доступна после двух подписей или запроса доработки.")
        serializer = DeliverableUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        filename = Path(data["file"].name.replace("\\", "/")).name[:255]
        Deliverable.objects.create(contract=contract, filename=filename, **data)
        contract.status = Contract.Status.REVIEW
        contract.save(update_fields=["status"])
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


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def dashboard(request):
    user = request.user
    contracts = Contract.objects.filter(Q(customer=user) | Q(freelancer=user))
    return Response({"active_orders": user.projects.exclude(status=Project.Status.COMPLETED).count(), "active_contracts": contracts.exclude(status=Contract.Status.COMPLETED).count(), "completed_orders": contracts.filter(status=Contract.Status.COMPLETED).count(), "completed_contracts": contracts.filter(status=Contract.Status.COMPLETED).count(), "proposals": user.proposals.count(), "balance": str(user.profile.balance)})


@api_view(["GET"])
def api_root(request):
    return Response({"name": "Taskora API", "version": "1.0", "projects": request.build_absolute_uri("projects/"), "profiles": request.build_absolute_uri("profiles/"), "health": request.build_absolute_uri("health/")})


@api_view(["GET"])
def overview(request):
    return Response({"active_projects": Project.objects.filter(status="active").count(), "freelancers": Profile.objects.filter(role="freelancer", user__is_active=True).count(), "completed_projects": Project.objects.filter(status="completed").count(), "proposals_this_week": Proposal.objects.filter(created_at__gte=timezone.now() - timedelta(days=7)).count()})


@api_view(["GET"])
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return Response({"status": "error", "database": "unavailable"}, status=503)
    return Response({"status": "ok", "database": "connected"})
