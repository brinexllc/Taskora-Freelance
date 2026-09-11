import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Project(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        ACTIVE = "published", "Опубликован"
        CONTRACTING = "contracting", "Согласование договора"
        IN_PROGRESS = "in_progress", "В работе"
        REVIEW = "review", "На проверке"
        COMPLETED = "completed", "Завершён"
        CANCELLED = "cancelled", "Отменён"
        DISPUTED = "disputed", "Спор"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="projects")
    title = models.CharField("Название", max_length=180)
    description = models.TextField("Описание")
    legacy_category = models.CharField(max_length=24, default='other', editable=False)
    category = models.ForeignKey('Category', on_delete=models.PROTECT, related_name='projects', verbose_name='Категория')
    skills_unspecified = models.BooleanField(default=False)
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
    skills = models.ManyToManyField("Skill", verbose_name="Навыки", related_name="projects", blank=True)
    client_name = models.CharField("Имя заказчика", max_length=120)
    client_company = models.CharField("Компания", max_length=120, blank=True)
    status = models.CharField(
        "Статус", max_length=24, choices=Status.choices, default=Status.ACTIVE
    )
    featured = models.BooleanField("Рекомендуемый", default=False)
    deadline = models.DateField("Срок выполнения", null=True, blank=True)
    budget_type = models.CharField(max_length=8, choices=[("fixed", "Fixed Price"), ("hourly", "Hourly"), ("daily", "Daily")], default="fixed")
    visibility = models.CharField(max_length=8, default="public", editable=False)
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
        WITHDRAWN = "withdrawn", "Отозван"

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
    enabled_roles = models.JSONField(default=list, blank=True)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    professional_experience = models.TextField(blank=True, max_length=3000)
    professional_title = models.CharField(max_length=160, blank=True)
    location = models.CharField(max_length=160, blank=True)
    portfolio = models.JSONField(default=list, blank=True)
    services = models.JSONField(default=list, blank=True)
    spoken_languages = models.JSONField(default=list, blank=True)
    available = models.BooleanField(default=True)
    birth_date = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=13, unique=True, null=True, blank=True)
    has_passport = models.BooleanField(default=False)
    about = models.TextField(blank=True, max_length=3000)
    avatar = models.TextField(blank=True)
    skills = models.ManyToManyField("Skill", verbose_name="Навыки", related_name="profiles", blank=True)
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
        SIGNING = "draft", "Ожидает подписей"
        CUSTOMER_ACCEPTED = "customer_accepted", "Подтверждён заказчиком"
        FREELANCER_ACCEPTED = "freelancer_accepted", "Подтверждён исполнителем"
        AWAITING_FUNDING = "awaiting_funding", "Ожидает резервирования"
        ACTIVE = "active", "В работе"
        REVIEW = "submitted", "На проверке"
        DISPUTED = "disputed", "Спор"
        COMPLETED = "completed", "Завершён"
        CANCELLED = "cancelled", "Отменён"

    project = models.OneToOneField(Project, on_delete=models.PROTECT, related_name="contract")
    proposal = models.OneToOneField(Proposal, on_delete=models.PROTECT, related_name="contract")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="customer_contracts")
    freelancer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="freelancer_contracts")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    delivery_days = models.PositiveIntegerField()
    terms = models.TextField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.SIGNING)
    version = models.PositiveIntegerField(default=1)
    scope = models.TextField(blank=True)
    currency = models.CharField(max_length=3, default="UZS")
    budget_type = models.CharField(max_length=8, default="fixed")
    deadline = models.DateTimeField(null=True, blank=True)
    funded_at = models.DateTimeField(null=True, blank=True)
    escrow_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_fee_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    fee_policy_snapshot = models.JSONField(default=dict, blank=True)
    released_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refunded_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    customer_signed_at = models.DateTimeField(null=True, blank=True)
    freelancer_signed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=models.Q(escrow_amount__gte=0), name="nonnegative_escrow")]


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
    payme_trans_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    provider_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)


class ClickFiscalReceipt(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает отправки"
        SUBMITTING = "submitting", "Проверяется результат отправки"
        SUBMITTED = "submitted", "Ожидает чека CLICK"
        READY = "ready", "Чек получен"
        REVIEW = "review", "Требует проверки"

    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name="click_receipt")
    # Immutable checkout snapshot; later config changes cannot change an existing receipt.
    payload = models.JSONField(default=dict)
    click_payment_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    qr_code_url = models.URLField(max_length=2000, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=240, blank=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["status", "next_attempt_at"])]


class WalletEntry(models.Model):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    contract = models.ForeignKey(Contract, null=True, blank=True, on_delete=models.PROTECT, related_name="transactions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="wallet_entries")
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    kind = models.CharField(max_length=24, choices=[("topup", "Пополнение"), ("escrow_hold", "Резервирование"), ("escrow_release", "Выплата по договору"), ("platform_fee", "Комиссия"), ("adjustment", "Корректировка"), ("income", "Оплата работы"), ("purchase", "Оплата заказа"), ("withdrawal", "Вывод средств"), ("refund", "Возврат")])
    description = models.CharField(max_length=240)
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["payment", "user", "kind"], name="unique_payment_ledger_entry"), models.UniqueConstraint(fields=["contract", "user", "kind"], name="unique_contract_ledger_entry")]


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


class Category(models.Model):
    slug = models.SlugField(unique=True, max_length=24)
    name = models.CharField(max_length=100)
    active = models.BooleanField(default=True)
    labels = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=100)
    icon_key = models.CharField(max_length=24, default='folder', choices=[(v, v) for v in ['code', 'smartphone', 'bot', 'palette', 'megaphone', 'pen', 'shield', 'folder']])

    class Meta:
        ordering = ['sort_order', 'id']

    def save(self, *args, **kwargs):
        from .taxonomy import validate_identity
        validate_identity(self)
        super().save(*args, **kwargs)

    def clean(self):
        from .taxonomy import validate_identity
        validate_identity(self)

    def __str__(self):
        return self.name


class Skill(models.Model):
    name = models.CharField(max_length=60, unique=True)
    active = models.BooleanField(default=True)
    slug = models.SlugField(unique=True, max_length=100, allow_unicode=True)
    normalized_name = models.CharField(max_length=180, unique=True, null=True, editable=False)
    labels = models.JSONField(default=dict, blank=True)
    merged_into = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='merged_skills')
    categories = models.ManyToManyField(Category, through='CategorySkill', related_name='skills')

    def save(self, *args, **kwargs):
        from .taxonomy import save_skill
        return save_skill(self, *args, **kwargs)

    def clean(self):
        from .taxonomy import normalize_key, validate_identity
        from django.core.exceptions import ValidationError
        validate_identity(self)
        if not self.merged_into_id and SkillAlias.objects.filter(key=normalize_key(self.name)).exclude(skill_id=self.pk).exists():
            raise ValidationError({'name': 'Имя или алиас принадлежит другому навыку.'})

    def __str__(self):
        return self.name


class SkillAlias(models.Model):
    # This registry contains canonical names AND aliases, so their namespaces cannot collide.
    key = models.CharField(max_length=180, unique=True)
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT, related_name='aliases')

    def clean(self):
        from .taxonomy import normalize_key
        from django.core.exceptions import ValidationError
        self.key = normalize_key(self.key)
        if not self.key or self.skill.merged_into_id:
            raise ValidationError('Укажите ключ канонического навыка.')
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if old.key == old.skill.normalized_name and (self.key != old.key or self.skill_id != old.skill_id):
                raise ValidationError('Каноническое имя нельзя переназначить через алиас.')
        if Skill.objects.filter(normalized_name=self.key).exclude(pk=self.skill_id).exists():
            raise ValidationError('Ключ совпадает с именем другого навыка.')
        conflict = type(self).objects.filter(key=self.key).exclude(pk=self.pk).first()
        if conflict:
            raise ValidationError({'key': 'Этот нормализованный ключ уже существует.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CategorySkill(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        constraints = [models.UniqueConstraint(fields=['category', 'skill'], name='unique_category_skill')]


class PlatformFee(models.Model):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    settlement_reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    contract = models.OneToOneField(Contract, on_delete=models.PROTECT, related_name='platform_fee')
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee_percent = models.DecimalField(max_digits=5, decimal_places=2)
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    source = models.CharField(max_length=16, choices=[('settlement', 'Расчёт'), ('backfill', 'Историческая сверка')], default='settlement')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(gross_amount__gte=0, fee_amount__gte=0, fee_amount__lte=models.F('gross_amount'), fee_percent__gte=0, fee_percent__lte=100), name='valid_platform_fee')]


class ContractEvent(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    kind = models.CharField(max_length=40)
    description = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class Message(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    text = models.TextField(max_length=5000, blank=True)
    file = models.FileField(upload_to=private_work_path, blank=True)
    filename = models.CharField(max_length=255, blank=True)
    system = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class Dispute(models.Model):
    contract = models.OneToOneField(Contract, on_delete=models.PROTECT, related_name="dispute")
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="opened_disputes")
    reason = models.TextField(max_length=5000)
    status = models.CharField(max_length=24, choices=[("opened", "Открыт"), ("evidence_collection", "Сбор доказательств"), ("admin_review", "На рассмотрении"), ("resolved", "Решён")], default="opened")
    resolution = models.TextField(blank=True)
    freelancer_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="resolved_disputes")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Review(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="reviews")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="written_reviews")
    target = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="received_reviews")
    rating = models.PositiveSmallIntegerField()
    text = models.TextField(max_length=3000)
    communication = models.PositiveSmallIntegerField(null=True, blank=True)
    quality = models.PositiveSmallIntegerField(null=True, blank=True)
    deadline = models.PositiveSmallIntegerField(null=True, blank=True)
    published = models.BooleanField(default=True)
    moderation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["contract", "author"], name="one_review_per_author"), models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="review_rating_range")]


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    contract = models.ForeignKey(Contract, null=True, blank=True, on_delete=models.PROTECT)
    kind = models.CharField(max_length=40)
    text = models.CharField(max_length=500)
    link = models.CharField(max_length=200, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


def attachment_path(instance, filename):
    return f"attachments/{uuid.uuid4().hex}"


class ProjectAttachment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="attachments")
    file = models.FileField(upload_to=attachment_path)
    filename = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
