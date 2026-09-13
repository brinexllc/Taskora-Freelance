"""Typed Russian editors and signed, expiring before/after previews."""
import json

from django import forms
from django.core import signing
from django.forms.utils import flatatt
from django.utils.html import format_html

from ..models import Category
from .workflows import state_fingerprint


class CollectionWidget(forms.Widget):
    def __init__(self, kind, attrs=None):
        self.kind = kind
        super().__init__(attrs)

    class Media:
        js = ["admin/taskora/admin-editor.js"]

    def render(self, name, value, attrs=None, renderer=None):
        if isinstance(value, list):
            value = json.dumps(value, ensure_ascii=False)
        attrs = self.build_attrs(self.attrs, attrs)
        return format_html('<div class="ta-collection-editor" data-collection-kind="{}"><input type="hidden" name="{}" value="{}"{}><div data-collection-items></div><button type="button" class="ta-button secondary" data-collection-add>Добавить запись</button></div>', self.kind, name, value or "[]", flatatt(attrs))


class AvatarWidget(forms.Widget):
    class Media:
        js = ["admin/taskora/admin-editor.js"]

    def render(self, name, value, attrs=None, renderer=None):
        attrs = self.build_attrs(self.attrs, attrs)
        return format_html('<div class="ta-avatar-editor"><input type="hidden" name="{}" value="{}"{}><input type="file" accept="image/png,image/jpeg,image/webp" aria-label="Выбрать аватар"><button type="button" class="ta-button secondary" data-avatar-clear>Удалить аватар</button><small role="status"></small></div>', name, value or "", flatatt(attrs))


def initial_value(obj, key):
    if obj._meta.model_name == "user" and key not in {"first_name", "last_name", "email"}:
        return getattr(obj.profile, key, "")
    return getattr(obj, key, "")


def add_edit_fields(form, action, obj):
    def field(key, label, instance):
        instance.label = label
        instance.initial = initial_value(obj, key)
        form.fields[key] = instance

    short = lambda maximum=160, required=False: forms.CharField(max_length=maximum, required=required)
    long = lambda maximum=5000, required=False: forms.CharField(max_length=maximum, required=required, widget=forms.Textarea(attrs={"rows": 3}))
    if action == "user.edit":
        for key, label in [("first_name", "Имя"), ("last_name", "Фамилия"), ("full_name", "Публичное имя")]:
            field(key, label, short(required=key == "full_name"))
        field("email", "Email", forms.EmailField())
        field("phone", "Телефон +998", short(30))
        for key, label in [("professional_title", "Профессиональный заголовок"), ("location", "Город")]:
            field(key, label, short())
        field("about", "О себе", long(3000))
        field("professional_experience", "Профессиональный опыт", long(3000))
        field("avatar", "Аватар", forms.CharField(required=False, widget=AvatarWidget()))
        field("portfolio", "Портфолио", forms.JSONField(required=False, widget=CollectionWidget("portfolio")))
        field("services", "Услуги", forms.JSONField(required=False, widget=CollectionWidget("services")))
        field("available", "Доступен для новых заказов", forms.BooleanField(required=False))
    elif action == "project.edit":
        field("title", "Название заказа", short(180, True))
        if not hasattr(obj, "contract"):
            field("description", "Описание заказа", long(15000, True))
        form.fields["category_id"] = forms.ModelChoiceField(label="Категория", queryset=Category.objects.filter(active=True), initial=obj.category_id)
        field("featured", "Рекомендуемый заказ", forms.BooleanField(required=False))
    elif action == "contract.amend":
        for key, label, maximum in [("scope", "Объём работ", 15000), ("acceptance_criteria", "Критерии приёмки", 5000), ("demonstration_method", "Способ демонстрации", 3000), ("test_scenario", "Сценарий проверки", 5000)]:
            field(key, label, long(maximum, key != "scope"))
        field("review_days", "Дней на проверку", forms.IntegerField(min_value=1, max_value=30))
        if obj.funded_at:
            field("deadline", "Согласованный срок", forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")))
        else:
            field("delivery_days", "Дней на выполнение", forms.IntegerField(min_value=1, max_value=365))
    elif action == "catalogue.save":
        field("name", "Название", short(100 if obj._meta.model_name == "category" else 60, True))
        field("active", "Доступен для новых выборов", forms.BooleanField(required=False))
        for language, label in [("ru", "Русский"), ("uz", "O‘zbekcha"), ("uz-cyrl", "Ўзбекча"), ("en", "English")]:
            form.fields["label_" + language] = forms.CharField(label="Название — " + label, required=False, max_length=160, initial=obj.labels.get(language, ""))
        if obj._meta.model_name == "category":
            field("sort_order", "Порядок в каталоге", forms.IntegerField(min_value=0))
            form.fields["icon_key"] = forms.ChoiceField(label="Иконка", choices=[("code", "Разработка"), ("smartphone", "Мобильные приложения"), ("bot", "Автоматизация"), ("palette", "Дизайн"), ("megaphone", "Маркетинг"), ("pen", "Тексты"), ("shield", "Безопасность"), ("folder", "Другое")], initial=obj.icon_key)
    # Business fields precede the reason and final confirmation.
    base = [key for key in ("reason", "confirmed") if key in form.fields]
    form.order_fields([key for key in form.fields if key not in base] + base)


EDIT_ACTIONS = {"user.edit", "project.edit", "contract.amend", "catalogue.save"}


def edit_changes(form, action, obj):
    excluded = {"reason", "idempotency_key", "confirmed", "expected_state"}
    changes = {key: value.pk if hasattr(value, "pk") else value.isoformat() if hasattr(value, "isoformat") else value
               for key, value in form.cleaned_data.items() if key not in excluded}
    labels = {key[6:]: changes.pop(key) for key in list(changes) if key.startswith("label_")}
    if action == "catalogue.save":
        changes["labels"] = {key: value for key, value in labels.items() if value.strip()}
    if action == "user.edit":
        for key in ("portfolio", "services"):
            changes[key] = changes.get(key) or []
        if not changes.get("phone") and not obj.profile.phone:
            changes.pop("phone", None)
    # Avoid rewriting untouched fields and suppress redundant contract versions.
    return {key: value for key, value in changes.items() if str(initial_value(obj, key) if key != "category_id" else obj.category_id) != str(value)}


def edit_preview_rows(form, changes, obj):
    rows = []
    for key, value in changes.items():
        before = initial_value(obj, key)
        label = form.fields[key].label if key in form.fields else "Переводы" if key == "labels" else key
        def display(item):
            if key == "avatar":
                return "Изображение загружено" if item else "Не задано"
            if isinstance(item, bool):
                return "Да" if item else "Нет"
            if isinstance(item, list):
                return "; ".join(str(record.get("title", record)) if isinstance(record, dict) else str(record) for record in item) or "Нет записей"
            if isinstance(item, dict):
                return "; ".join(f"{lang}: {text}" for lang, text in item.items())
            if key == "category_id":
                return str(Category.objects.filter(pk=item).first() or "Не задано")
            return str(item or "Не задано")
        rows.append({"label": label, "before": display(before), "after": display(value)})
    return rows


def sign_edit_preview(action, obj, data, actor_id):
    return signing.dumps({"action": action, "object_id": str(obj.pk), "actor_id": actor_id, "expected_state": state_fingerprint(obj), "data": data}, salt="admin-edit-preview", compress=True)


def load_edit_preview(token, action, obj, actor_id):
    payload = signing.loads(token, salt="admin-edit-preview", max_age=900)
    if payload.get("action") != action or payload.get("object_id") != str(obj.pk) or payload.get("actor_id") != actor_id:
        raise signing.BadSignature("Предпросмотр относится к другому действию.")
    return payload["data"]


SNAPSHOT_LABELS = {
    "amount": "Сумма", "currency": "Валюта", "user_id": "ID пользователя", "recipient_id": "ID получателя",
    "destination": "Получатель", "provider": "Провайдер", "account": "Аккаунт провайдера", "provider_recipient_id": "Получатель у провайдера",
    "payout_provider": "Провайдер выплаты", "payout_account": "Аккаунт выплаты", "provider_reference": "Номер внешнего перевода",
    "claimed_by": "Принявший администратор", "claimed_at": "Дата принятия", "withdrawal_id": "ID вывода",
    "payment_id": "ID платежа", "contract_id": "ID договора", "contract_version": "Версия договора", "version": "Версия",
    "gross": "До комиссии", "gross_amount": "До комиссии", "net": "После комиссии", "fee": "Комиссия", "fee_amount": "Комиссия",
    "refund": "Возврат заказчику", "escrow": "Резерв", "escrow_amount": "Резерв", "fee_percent": "Ставка комиссии, %",
    "freelancer_fee_percent": "Комиссия исполнителя, %", "customer_fee_percent": "Комиссия заказчика, %",
    "calculation_basis": "База расчёта", "policy_version": "Версия политики", "payer": "Плательщик", "rounding": "Округление", "precision": "Точность",
    "before": "До изменения", "after": "После изменения", "reason": "Основание", "result": "Результат", "status": "Состояние",
    "request_id": "ID запроса", "operation_id": "UUID операции", "idempotency_key": "UUID повтора", "settlement_reference": "UUID расчёта",
    "evidence": "Подтверждение", "verified_at": "Дата проверки", "verified_by": "Проверил", "full_name": "Имя", "phone": "Телефон", "email": "Email",
    "balance": "Остаток", "available": "Доступен", "public_hidden": "Скрыт публично", "published": "Опубликован", "featured": "Рекомендуемый",
    "title": "Название", "description": "Описание", "is_active": "Активен", "customer_id": "ID заказчика", "freelancer_id": "ID исполнителя",
    "ru": "Русский", "uz": "O‘zbekcha", "uz-cyrl": "Ўзбекча", "en": "English", "contracts": "Договоры", "withdrawals": "Выводы",
    "scope": "Объём работ", "acceptance_criteria": "Критерии приёмки", "test_scenario": "Сценарий проверки", "demonstration_method": "Демонстрация",
    "review_days": "Дней на проверку", "delivery_days": "Дней на выполнение", "deadline": "Срок выполнения",
    "checked_at": "Дата проверки", "backend": "Сервер приложения", "database": "База данных", "database_engine": "Тип базы данных",
    "release_sha": "Версия выпуска", "environment": "Среда", "pending_migrations": "Ожидающие миграции",
    "private_storage": "Приватное хранилище", "exists": "Создано", "readable": "Доступно чтение", "writable": "Доступна запись",
    "file_counts": "Количество файлов", "last_successful_background_job": "Последняя успешная фоновая задача",
    "fiscal_queue": "Очередь чеков", "withdrawals_requiring_reconciliation": "Выводы, требующие сверки", "incidents": "Инциденты",
    "backup_confirmed_at": "Подтверждённая резервная копия", "restore_verified_at": "Проверка восстановления",
    "channels": "Каналы уведомлений", "internal": "Внутренний кабинет", "sms": "SMS", "real_money_enabled": "Реальные платежи разрешены",
    "file_sha256": "Контрольная сумма SHA-256", "file_bytes": "Размер файла, байт", "row_count": "Строк", "filters": "Фильтры",
}


def friendly_snapshot(value):
    """Readable labels for stored financial/history dictionaries; never executes markup."""
    if isinstance(value, dict):
        return "\n".join(f"{SNAPSHOT_LABELS.get(key, key)}: {friendly_snapshot(item)}" for key, item in value.items())
    if isinstance(value, list):
        return " · ".join(friendly_snapshot(item) for item in value) or "Нет записей"
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    if value is None:
        return "Не указано"
    return {"freelancer": "Исполнитель", "client": "Заказчик", "released_gross": "Валовая выплата исполнителю", "ROUND_HALF_UP": "До ближайшего значения; половина вверх", "success": "Успешно", "ok": "Доступно", "connected": "Подключено", "not_connected": "Не подключено", "disabled": "Отключено", "local": "Локальная", "test": "Тестовая", "unversioned": "Не указан"}.get(str(value), str(value))
