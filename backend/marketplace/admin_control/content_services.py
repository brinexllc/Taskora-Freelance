"""Explicit commands for content, policy and notification publication."""
import hashlib
import json
import re
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import OperationalError, ProgrammingError, transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from .content_models import (Announcement, AnnouncementRecipient, ContentRevision,
                             NotificationDelivery, PlatformSettingRevision)

HOME_KEYS = ('heroA', 'heroB', 'heroC', 'designHeroText', 'trustText', 'designSecureTitle',
    'designSecureText', 'securePayment', 'designEscrowText', 'designMatching', 'designMatchingText',
    'oneidFeature', 'oneidFeatureText', 'designSteps', 'designStepsText', 'designStep1',
    'designStep1Text', 'designStep2', 'designStep2Text', 'designStep3', 'designStep3Text',
    'designTopFreelancers', 'specialists', 'today', 'designCtaText', 'designCompany',
    'designSupport', 'designMadeIn', 'footerPlatform', 'aboutPlatform')
LEGAL_KEYS = ('terms', 'privacy', 'how_it_works', 'fees', 'support_guidance', 'notice')
SCALAR_KEYS = ('terms', 'privacy', 'fees', 'support_guidance', 'notice')
SETTINGS_SCHEMA = {
    'platform_fee_percent': {'label': 'Комиссия исполнителя, %', 'type': 'decimal', 'min': '0', 'max': '100', 'default': '5.00'},
    'project_moderation_mode': {'label': 'Модерация заказов', 'type': 'choice', 'choices': ['pre', 'post'], 'default': 'post'},
    'support_response_hours': {'label': 'Срок ответа поддержки, часов', 'type': 'integer', 'min': 1, 'max': 720, 'default': 48},
    'dispute_response_hours': {'label': 'Срок ответа по спору, часов', 'type': 'integer', 'min': 1, 'max': 720, 'default': 48},
    'skill_verification_enabled': {'label': 'Приём заявок на проверку навыков', 'type': 'boolean', 'default': True},
    'topups_paused': {'label': 'Приостановить новые пополнения', 'type': 'boolean', 'default': False},
    'reserves_paused': {'label': 'Приостановить новые резервы', 'type': 'boolean', 'default': False},
    'withdrawals_paused': {'label': 'Приостановить новые выводы', 'type': 'boolean', 'default': False},
    'maintenance_enabled': {'label': 'Режим обслуживания сайта', 'type': 'boolean', 'default': False},
    'email_notifications_enabled': {'label': 'Email-уведомления', 'type': 'boolean', 'default': False},
    'sms_notifications_enabled': {'label': 'SMS-уведомления', 'type': 'boolean', 'default': False},
}


class ContentConflict(APIException):
    status_code = 409
    default_code = 'stale_version'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def command_actor(actor, request, *, sensitive=False):
    from ..security import require_platform_admin_session
    session = require_platform_admin_session(request, sensitive=sensitive)
    if actor.pk != request.user.pk:
        raise PermissionDenied('Инициатор не совпадает с защищённой сессией.')
    # Serializes administrator commands even when no initial revision exists.
    if transaction.get_connection().in_atomic_block:
        actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
        if not actor.is_active or not actor.is_staff or not actor.is_superuser:
            raise PermissionDenied('Доступ администратора отозван.')
    return session


def clean_reason(reason):
    reason = str(reason or '').strip()
    if not 10 <= len(reason) <= 2000:
        raise ValidationError({'reason': 'Укажите основание: от 10 до 2000 символов.'})
    return reason


def record_audit(actor, request, action, obj, reason, before=None, after=None, operation_id=None, outcome='success'):
    from ..models import AuditLog
    return AuditLog.objects.create(actor=actor, action=action, object_type=obj._meta.model_name,
        object_id=str(obj.pk), reason=reason, before=before or {}, after=after or {},
        operation_id=operation_id, outcome=outcome,
        request_id=str(getattr(request, 'request_id', '') or (request.META.get('HTTP_X_REQUEST_ID', '') if request else ''))[:80],
        detail={'reason': reason, 'before': before or {}, 'after': after or {}})


def clean_text(value, maximum=10000):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValidationError('Текст превышает допустимый размер.')
    # Plain text only; no HTML, executable URLs, embedded credentials or control bytes.
    if re.search(r'<\s*/?\s*[a-z!]|javascript\s*:|data\s*:|-----BEGIN [A-Z ]*PRIVATE KEY|(?:sk_live_|sk-proj-)|[\x00-\x08\x0b\x0c\x0e-\x1f]', value, re.I):
        raise ValidationError('Допустим только обычный текст без HTML, скриптов и секретных ключей.')
    return value.strip()


def clean_link(value):
    value = clean_text(value, 200)
    if not value:
        return ''
    parsed = urlsplit(value)
    if value.startswith('/') and not value.startswith('//') and '\\' not in value:
        return value
    if parsed.scheme == 'https' and parsed.netloc and not parsed.username and not parsed.password:
        return value
    raise ValidationError('Ссылка должна быть HTTPS или начинаться с одного /.')


def validate_payload(payload):
    if not isinstance(payload, dict) or set(payload) - set(LEGAL_KEYS) - {'operator', 'support', 'homepage', 'faq'}:
        raise ValidationError('Неизвестные поля контента. Используйте ограниченную схему.')
    result = {}
    for key in SCALAR_KEYS:
        result[key] = clean_text(payload.get(key, ''))
    if not result['terms'] or not result['privacy']:
        raise ValidationError('Условия и политика конфиденциальности обязательны.')
    steps = payload.get('how_it_works', [])
    if not isinstance(steps, list) or len(steps) > 12:
        raise ValidationError('Допустимо не более 12 шагов.')
    result['how_it_works'] = [clean_text(item, 1000) for item in steps]
    for section, allowed in [('operator', {'legal_name', 'tax_id', 'address'}), ('support', {'email', 'phone', 'response_time', 'withdrawal_rules', 'refund_rules', 'dispute_rules', 'url'}), ('homepage', set(HOME_KEYS))]:
        values = payload.get(section, {})
        if not isinstance(values, dict) or set(values) - allowed:
            raise ValidationError(f'Неизвестные поля раздела {section}.')
        result[section] = {key: clean_link(value) if key == 'url' else clean_text(value, 3000) for key, value in values.items()}
    if set(result['homepage']) != set(HOME_KEYS) or any(not result['homepage'][key] for key in HOME_KEYS):
        raise ValidationError('Сохраните все существующие текстовые блоки homepage. Создавайте черновик на основе текущей редакции.')
    if result['support'].get('email'):
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_email(result['support']['email'])
        except DjangoValidationError:
            raise ValidationError('Некорректный email поддержки.')
    faq = payload.get('faq', [])
    if not isinstance(faq, list) or len(faq) > 50:
        raise ValidationError('В FAQ допустимо не более 50 записей.')
    result['faq'] = []
    for item in faq:
        if not isinstance(item, dict) or set(item) != {'question', 'answer'}:
            raise ValidationError('FAQ содержит только question и answer.')
        result['faq'].append({'question': clean_text(item['question'], 300), 'answer': clean_text(item['answer'], 3000)})
    if len(json.dumps(result).encode()) > 150000:
        raise ValidationError('Контент превышает 150 КБ.')
    return result


def legal_payload(payload):
    return {key: payload[key] for key in (*LEGAL_KEYS, 'operator', 'support') if key in payload}


def latest_published(model, **filters):
    return model.objects.filter(**filters, published_at__isnull=False, effective_at__lte=timezone.now()).order_by('-version').first()


def current_legal_document(language):
    language = language if language in {'ru', 'uz', 'uz-cyrl', 'en'} else 'ru'
    try:
        revision = latest_published(ContentRevision, language=language)
    except (OperationalError, ProgrammingError) as exc:
        error = APIException('Опубликованная редакция временно недоступна. Повторите позже.')
        error.status_code = 503
        raise error from exc
    if not revision:
        error = APIException('Опубликованная редакция недоступна. Повторите позже.')
        error.status_code = 503
        raise error
    content = legal_payload(revision.payload)
    return {'version': revision.legal_version, 'hash': digest(content), 'language': language,
        'content': content, 'approved': revision.approved, 'operator': content.get('operator', {}),
        'support': content.get('support', {}), 'homepage': revision.payload.get('homepage', {}),
        'faq': revision.payload.get('faq', []), 'published_at': revision.published_at.isoformat(),
        'effective_at': revision.effective_at.isoformat(), 'maintenance': get_setting('maintenance_enabled', False)}


def _version(model, field, value):
    # The initial published row is a shared lock for all administrators of this stream.
    list(model.objects.select_for_update().filter(**{field: value}).order_by('pk').values_list('pk', flat=True))
    return model.objects.filter(**{field: value}, published_at__isnull=False).aggregate(n=Max('version'))['n'] or 0


def assert_version(actual, expected):
    try:
        expected = int(expected)
    except (ValueError, TypeError):
        raise ValidationError('Требуется номер проверенной версии.')
    if actual != expected:
        raise ContentConflict({'detail': 'Данные изменились. Обновите предпросмотр.', 'current_version': actual})


@transaction.atomic
def create_content_draft(*, actor, request, language, payload, reason, expected_version, approved=False):
    command_actor(actor, request)
    reason = clean_reason(reason)
    if language not in {'ru', 'uz', 'uz-cyrl', 'en'}:
        raise ValidationError('Неизвестный язык.')
    if type(approved) is not bool:
        raise ValidationError('Признак юридического согласования должен быть логическим.')
    payload = validate_payload(payload)
    current = _version(ContentRevision, 'language', language)
    assert_version(current, expected_version)
    version = (ContentRevision.objects.filter(language=language).aggregate(n=Max('version'))['n'] or 0) + 1
    hash_value = digest(legal_payload(payload))
    base = ContentRevision.objects.filter(language=language, version=current, published_at__isnull=False).first()
    legal_version = base.legal_version if base and base.content_hash == hash_value else f'cms-{language}-v{version}-{hash_value[:12]}'
    revision = ContentRevision.objects.create(language=language, payload=payload, author=actor, reason=reason,
        version=version, base_version=current, content_hash=hash_value, legal_version=legal_version, approved=approved)
    record_audit(actor, request, 'content_draft', revision, reason, after={'language': language, 'version': version, 'hash': hash_value})
    return revision


def publication_key(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError('Нужен неизменный UUID операции.')


def effective_date(value):
    value = value or timezone.now()
    if isinstance(value, str):
        from django.utils.dateparse import parse_datetime
        value = parse_datetime(value)
    if not value or timezone.is_naive(value) or value > timezone.now() + timedelta(days=365):
        raise ValidationError('Укажите дату со смещением UTC не более чем на год вперёд.')
    return value


@transaction.atomic
def publish_content(*, actor, request, revision_id, reason, expected_version, idempotency_key, effective_at=None):
    command_actor(actor, request, sensitive=True)
    reason, key = clean_reason(reason), publication_key(idempotency_key)
    revision = ContentRevision.objects.get(pk=revision_id)
    actual = _version(ContentRevision, 'language', revision.language)
    revision.refresh_from_db()
    params_hash = digest([actor.pk, revision_id, reason, expected_version, str(effective_at or '')])
    prior = ContentRevision.objects.filter(publication_key=key).first()
    if prior:
        if prior.pk != revision.pk or prior.publication_hash != params_hash:
            raise ContentConflict('Ключ уже использован для другой публикации.')
        return prior
    assert_version(actual, expected_version)
    if revision.published_at or revision.base_version != actual:
        raise ContentConflict('Черновик устарел или уже опубликован. Создайте новую редакцию.')
    before = latest_published(ContentRevision, language=revision.language)
    revision.published_at, revision.effective_at = timezone.now(), effective_date(effective_at)
    revision.publication_key, revision.publication_hash = key, params_hash
    revision.save()
    record_audit(actor, request, 'content_publish', revision, reason,
        before={'version': before.version, 'hash': before.content_hash} if before else {},
        after={'version': revision.version, 'hash': revision.content_hash, 'effective_at': revision.effective_at.isoformat()}, operation_id=key)
    return revision


def validate_setting(key, value):
    schema = SETTINGS_SCHEMA.get(key)
    if not schema:
        raise ValidationError('Настройка не разрешена. Секреты управляются только окружением.')
    kind = schema['type']
    if kind == 'boolean':
        if type(value) is not bool:
            raise ValidationError('Требуется JSON true или false.')
    elif kind == 'integer':
        if type(value) is not int or not schema['min'] <= value <= schema['max']:
            raise ValidationError(f"Требуется целое число {schema['min']}–{schema['max']}.")
    elif kind == 'choice':
        if value not in schema['choices']:
            raise ValidationError('Значение отсутствует в разрешённом справочнике.')
    elif kind == 'decimal':
        from ..fees import fee_rate
        value = str(fee_rate(value))
    return value


def get_setting(key, default=None):
    revision = latest_published(PlatformSettingRevision, key=key)
    if revision:
        if key == 'platform_fee_percent' and not revision.author_id:
            from ..fees import fee_rate
            return str(fee_rate(settings.PLATFORM_FEE_PERCENT))
        return revision.value
    return SETTINGS_SCHEMA.get(key, {}).get('default', default)


def preview_setting(key, value):
    value = validate_setting(key, value)
    revision = latest_published(PlatformSettingRevision, key=key)
    return {'key': key, 'label': SETTINGS_SCHEMA[key]['label'], 'before': revision.value if revision else SETTINGS_SCHEMA[key]['default'],
        'after': value, 'expected_version': revision.version if revision else 0,
        'scope': 'Только новые версии согласования; подписанные снимки комиссии сохраняются.' if key == 'platform_fee_percent' else 'Новые операции после публикации.',
        'real_money_enabled': bool(settings.REAL_MONEY_ENABLED)}


@transaction.atomic
def publish_setting(*, actor, request, key, value, reason, expected_version, idempotency_key, effective_at=None):
    command_actor(actor, request, sensitive=True)
    reason, operation_key = clean_reason(reason), publication_key(idempotency_key)
    value = validate_setting(key, value)
    actual = _version(PlatformSettingRevision, 'key', key)
    params_hash = digest([actor.pk, key, value, reason, expected_version, str(effective_at or '')])
    prior = PlatformSettingRevision.objects.filter(publication_key=operation_key).first()
    if prior:
        if prior.publication_hash != params_hash:
            raise ContentConflict('Ключ уже использован для другой настройки.')
        return prior
    assert_version(actual, expected_version)
    before = get_setting(key)
    if key in {'topups_paused', 'reserves_paused', 'withdrawals_paused'} and before is True and value is False:
        from ..payment_views import financial_operations_enabled
        from ..operations import pending_migrations
        if not financial_operations_enabled() or pending_migrations():
            raise ValidationError('Возобновление требует допуска денежных операций и завершённых миграций.')
        if key == 'topups_paused':
            from ..click import click_ready
            from ..payme_views import payme_ready
            if not click_ready() and not payme_ready():
                raise ValidationError('Возобновление пополнений требует подключённого платёжного канала.')
    if key == 'email_notifications_enabled' and value and not settings.EMAIL_HOST:
        raise ValidationError('Email-канал не подключён.')
    if key == 'sms_notifications_enabled' and value and not settings.ESKIZ_TOKEN:
        raise ValidationError('SMS-канал не подключён.')
    revision = PlatformSettingRevision.objects.create(key=key, value=value, version=actual + 1, base_version=actual,
        author=actor, reason=reason, published_at=timezone.now(), effective_at=effective_date(effective_at),
        publication_key=operation_key, publication_hash=params_hash)
    record_audit(actor, request, 'setting_publish', revision, reason, before={'value': before},
        after={'key': key, 'value': value, 'version': revision.version}, operation_id=operation_key)
    return revision


def ensure_operation_enabled(operation):
    if operation not in {'topups', 'reserves', 'withdrawals'}:
        raise ValueError('Unknown financial gate')
    if get_setting(f'{operation}_paused', False):
        raise PermissionDenied({'code': 'operation_paused', 'detail': 'Новые операции временно приостановлены администратором.'})
    # Preserve local sandbox behavior; production admission remains environment-owned.
    if getattr(settings, 'TASKORA_ENV', 'local') in {'staging', 'production'} and not settings.REAL_MONEY_ENABLED:
        raise PermissionDenied({'code': 'financial_operations_disabled', 'detail': 'Денежные операции отключены в окружении.'})


def audience_queryset(audience):
    if not isinstance(audience, dict) or set(audience) - {'role', 'registered_from', 'registered_to'}:
        raise ValidationError('Разрешены фильтры role, registered_from, registered_to.')
    qs = get_user_model().objects.filter(is_active=True, is_staff=False, is_superuser=False).order_by('pk')
    if audience.get('role'):
        if audience['role'] not in {'client', 'freelancer'}:
            raise ValidationError('Неизвестный режим аудитории.')
        from django.db.models import Q
        qs = qs.filter(Q(profile__role=audience['role']) | Q(profile__enabled_roles__icontains='"' + audience['role'] + '"'))
    for param, suffix in [('registered_from', 'gte'), ('registered_to', 'lt')]:
        if audience.get(param):
            value = effective_date(audience[param])
            qs = qs.filter(**{f'date_joined__{suffix}': value})
    return qs


def audience_digest(qs):
    state, count = hashlib.sha256(), 0
    for pk in qs.values_list('pk', flat=True).iterator(chunk_size=1000):
        state.update(f'{pk}\n'.encode())
        count += 1
    return count, state.hexdigest()


@transaction.atomic
def create_announcement(*, actor, request, title, text, link='', audience=None, reason):
    command_actor(actor, request)
    reason = clean_reason(reason)
    audience = audience or {}
    audience_queryset(audience)
    announcement = Announcement.objects.create(title=clean_text(title, 120), text=clean_text(text, 500),
        link=clean_link(link), audience=audience, author=actor, reason=reason)
    if not announcement.title or not announcement.text:
        raise ValidationError('Заполните заголовок и текст.')
    record_audit(actor, request, 'announcement_draft', announcement, reason, after={'audience': audience})
    return announcement


@transaction.atomic
def preview_announcement(*, actor, request, announcement_id):
    command_actor(actor, request)
    announcement = Announcement.objects.select_for_update().get(pk=announcement_id, author=actor)
    if announcement.state not in {'draft', 'previewed'}:
        raise ContentConflict('Объявление уже передано на отправку.')
    qs = audience_queryset(announcement.audience)
    announcement.recipients.all().delete()
    batch, count, state = [], 0, hashlib.sha256()
    for pk in qs.values_list('pk', flat=True).iterator(chunk_size=1000):
        state.update(f'{pk}\n'.encode())
        batch.append(AnnouncementRecipient(announcement=announcement, user_id=pk))
        count += 1
        if len(batch) == 1000:
            AnnouncementRecipient.objects.bulk_create(batch)
            batch.clear()
    AnnouncementRecipient.objects.bulk_create(batch)
    announcement.recipient_count, announcement.recipient_hash = count, state.hexdigest()
    announcement.state, announcement.previewed_at = 'previewed', timezone.now()
    announcement.version += 1
    announcement.save()
    record_audit(actor, request, 'announcement_preview', announcement, announcement.reason, after={'audience': announcement.audience, 'count': count, 'hash': announcement.recipient_hash})
    return announcement


@transaction.atomic
def enqueue_announcement(*, actor, request, announcement_id, expected_version, idempotency_key, reason):
    from .jobs import enqueue_job
    command_actor(actor, request, sensitive=True)
    announcement = Announcement.objects.select_for_update().get(pk=announcement_id, author=actor)
    key = publication_key(idempotency_key)
    from .content_models import AdminJob
    previous = AdminJob.objects.filter(idempotency_key=key).first()
    if previous:
        if previous.actor_id != actor.pk or previous.kind != 'announcement' or previous.parameters != {'announcement_id': announcement.pk, 'expected_version': int(expected_version)} or previous.reason != reason.strip():
            raise ContentConflict('Ключ уже использован для другой отправки.')
        return previous
    assert_version(announcement.version, expected_version)
    if announcement.state != 'previewed' or announcement.previewed_at < timezone.now() - timedelta(minutes=30):
        raise ValidationError('Сначала выполните предпросмотр аудитории; он действует 30 минут.')
    count, value_hash = audience_digest(audience_queryset(announcement.audience))
    if count != announcement.recipient_count or value_hash != announcement.recipient_hash:
        raise ContentConflict('Аудитория изменилась. Обновите предпросмотр.')
    job = enqueue_job(actor=actor, request=request, kind='announcement', parameters={'announcement_id': announcement.pk, 'expected_version': int(expected_version)}, reason=reason, idempotency_key=key)
    announcement.state = 'queued'
    announcement.save(update_fields=['state'])
    record_audit(actor, request, 'announcement_send', announcement, reason, after={'audience': announcement.audience, 'count': count, 'job': str(job.pk)}, operation_id=key)
    return job


@transaction.atomic
def deliver_notification(*, user_id, event_key, kind, text, contract=None, link=''):
    from ..models import Notification
    row, created = NotificationDelivery.objects.get_or_create(user_id=user_id, event_key=str(event_key)[:160], channel='internal', defaults={'template': kind})
    if created:
        row.notification = Notification.objects.create(user_id=user_id, kind=kind, text=text[:500], contract=contract, link=link)
        row.delivered_at, row.status = timezone.now(), 'delivered'
        row.save(update_fields=['notification', 'delivered_at', 'status'])
    return row.notification
