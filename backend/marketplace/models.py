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

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="projects")
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
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает решения"
        ACCEPTED = "accepted", "Принят"
        REJECTED = "rejected", "Отклонён"

    freelancer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="proposals")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
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
        constraints = [models.UniqueConstraint(fields=["project", "freelancer"], name="unique_project_freelancer")]

    def __str__(self):
        return f"{self.freelancer_name} → {self.project}"


class Profile(models.Model):
    class Role(models.TextChoices):
        FREELANCER = "freelancer", "Фрилансер"
        CLIENT = "client", "Заказчик"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField("Полное имя", max_length=160)
    role = models.CharField("Роль", max_length=16, choices=Role.choices, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=13, unique=True, null=True, blank=True)
    has_passport = models.BooleanField(default=False)
    about = models.TextField(blank=True, max_length=3000)
    avatar = models.TextField(blank=True)
    skills = models.JSONField(default=list, blank=True)
    verified_skills = models.JSONField(default=list, blank=True)
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    rate_unit = models.CharField(max_length=8, choices=[("hour", "За час"), ("day", "За день")], default="hour")
    language = models.CharField(max_length=8, choices=[("ru", "Русский"), ("uz", "O‘zbekcha"), ("uz-cyrl", "Ўзбекча"), ("en", "English")], default="ru")
    theme = models.CharField(max_length=8, choices=[("light", "Светлая"), ("dark", "Тёмная")], default="light")
    balance = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(balance__gte=0), name="nonnegative_wallet_balance")]

    @property
    def age(self):
        from django.utils import timezone
        if not self.birth_date:
            return None
        today = timezone.localdate()
        return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))

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
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_expired(self):
        from django.utils import timezone

        return timezone.now() >= self.expires_at


def private_work_path(instance, filename):
    # Never use user-controlled filenames as storage paths or expose MEDIA_URL.
    return f"deliverables/{instance.contract_id}/{uuid.uuid4().hex}"


class Contract(models.Model):
    class Status(models.TextChoices):
        SIGNING = "signing", "Ожидает подписей"
        ACTIVE = "active", "В работе"
        REVIEW = "review", "На проверке"
        COMPLETED = "completed", "Завершён"

    project = models.OneToOneField(Project, on_delete=models.PROTECT, related_name="contract")
    proposal = models.OneToOneField(Proposal, on_delete=models.PROTECT, related_name="contract")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="customer_contracts")
    freelancer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="freelancer_contracts")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    delivery_days = models.PositiveIntegerField()
    terms = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SIGNING)
    customer_signed_at = models.DateTimeField(null=True, blank=True)
    freelancer_signed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Deliverable(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="deliverables")
    file = models.FileField(upload_to=private_work_path)
    filename = models.CharField(max_length=255)
    preview_text = models.TextField(max_length=15000)
    preview_image = models.TextField(blank=True)
    revision_note = models.TextField(blank=True, max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает оплаты"
        PREPARED = "prepared", "Подготовлен"
        PAID = "paid", "Оплачен"
        CANCELLED = "cancelled", "Отменён"

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments")
    contract = models.ForeignKey(Contract, null=True, blank=True, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    provider = models.CharField(max_length=12, default="click")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    click_trans_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)


class WalletEntry(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="wallet_entries")
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    kind = models.CharField(max_length=24, choices=[("topup", "Пополнение"), ("income", "Оплата работы"), ("purchase", "Оплата заказа"), ("withdrawal", "Вывод средств"), ("refund", "Возврат")])
    description = models.CharField(max_length=240)
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["payment", "user", "kind"], name="unique_payment_ledger_entry")]


class Withdrawal(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="withdrawals")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Only a masked destination is retained; card numbers are never collected.
    destination = models.CharField(max_length=160)
    status = models.CharField(max_length=12, choices=[("pending", "В обработке"), ("paid", "Выполнен"), ("rejected", "Отклонён")], default="pending")
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    provider_reference = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
