import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Project(models.Model):
    class Category(models.TextChoices):
        DEVELOPMENT = "development", "Разработка"
        DESIGN = "design", "Дизайн"
        MARKETING = "marketing", "Маркетинг"
        WRITING = "writing", "Тексты"
        OTHER = "other", "Другое"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        ACTIVE = "active", "Активен"
        IN_PROGRESS = "in_progress", "В работе"
        COMPLETED = "completed", "Завершён"

    title = models.CharField("Название", max_length=180)
    description = models.TextField("Описание")
    category = models.CharField(
        "Категория", max_length=24, choices=Category.choices, default=Category.OTHER
    )
    budget_min = models.DecimalField(
        "Минимальный бюджет",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    budget_max = models.DecimalField(
        "Максимальный бюджет",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    skills = models.JSONField("Навыки", default=list, blank=True)
    client_name = models.CharField("Имя заказчика", max_length=120)
    client_company = models.CharField("Компания", max_length=120, blank=True)
    status = models.CharField(
        "Статус", max_length=24, choices=Status.choices, default=Status.ACTIVE
    )
    featured = models.BooleanField("Рекомендуемый", default=False)
    deadline = models.DateField("Срок выполнения", null=True, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        ordering = ["-featured", "-created_at"]
        verbose_name = "Проект"
        verbose_name_plural = "Проекты"
        indexes = [
            models.Index(fields=["status", "category"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return self.title


class Proposal(models.Model):
    project = models.ForeignKey(
        Project,
        related_name="proposals",
        on_delete=models.CASCADE,
        verbose_name="Проект",
    )
    freelancer_name = models.CharField("Имя исполнителя", max_length=120)
    freelancer_email = models.EmailField("Email")
    cover_letter = models.TextField("Сопроводительное письмо")
    amount = models.DecimalField(
        "Стоимость",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    delivery_days = models.PositiveIntegerField(
        "Срок в днях", validators=[MinValueValidator(1)]
    )
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Отклик"
        verbose_name_plural = "Отклики"
        indexes = [models.Index(fields=["project", "-created_at"])]

    def __str__(self):
        return f"{self.freelancer_name} → {self.project}"


class Profile(models.Model):
    class Role(models.TextChoices):
        FREELANCER = "freelancer", "Фрилансер"
        CLIENT = "client", "Заказчик"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField("Полное имя", max_length=160)
    role = models.CharField("Роль", max_length=16, choices=Role.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name or self.user.email


class PasswordResetCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reset_codes")
    code_hash = models.CharField(max_length=128)
    reset_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_expired(self):
        from django.utils import timezone

        return timezone.now() >= self.expires_at
