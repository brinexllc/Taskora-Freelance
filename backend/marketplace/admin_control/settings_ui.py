"""Human-readable control state, separate from a saved switch value."""
import uuid
from django.conf import settings
from .content_models import PlatformSettingRevision
from .content_services import SETTINGS_SCHEMA, get_setting, setting_requires_confirmation


def setting_version(key):
    row = PlatformSettingRevision.objects.filter(key=key, published_at__isnull=False).order_by('-version').first()
    return row.version if row else 0


def setting_cards():
    from ..financial_admission import financial_blockers
    from ..click import click_ready
    from ..payme_views import payme_ready
    blockers = financial_blockers()
    cards = []
    for key, schema in SETTINGS_SCHEMA.items():
        value = get_setting(key)
        boolean = schema['type'] == 'boolean'
        paused = key.endswith('_paused')
        display = ('Приостановлено' if value else 'Разрешено') if paused else ('Включено' if value else 'Выключено') if boolean else str(value)
        if key == 'project_moderation_mode':
            display = {'pre': 'До публикации', 'post': 'После публикации'}.get(value, value)
        card = {'key': key, 'label': schema['label'].replace('Приостановить новые', 'Новые'),
            'value': display, 'url': f'/admin/control/new/setting/?key={key}',
            'toggle': boolean, 'next_value': 'false' if value else 'true',
            'button': ('Возобновить' if value else 'Приостановить') if paused else ('Выключить' if value else 'Включить'),
            'version': setting_version(key), 'idempotency_key': uuid.uuid4(),
            'requires_confirmation': setting_requires_confirmation(key, not value), 'hint': ''}
        if key == 'real_money_enabled':
            card.update(url='/admin/control/launch/', toggle=bool(value))
            card['hint'] = 'Проверить условия и управлять запуском денежных операций.'
            if value and blockers:
                card.update(value='Включено · требуется настройка', hint=blockers[0]['message'])
        elif paused and not value:
            if blockers:
                card.update(value='Ожидает запуска денежных операций', hint='Переключатель разрешён. ' + blockers[0]['message'], setup_url='/admin/control/launch/')
            elif key == 'topups_paused' and not click_ready() and not payme_ready():
                card.update(value='Ожидает подключения оплаты', hint='Разрешение сохранено. Платёжный канал пока не подключён.', setup_url='/admin/control/operations/')
        elif key == 'email_notifications_enabled' and value and not settings.EMAIL_HOST:
            card.update(value='Ожидает подключения email', hint='Разрешение сохранено. Отправка станет доступна после подключения почтового сервиса.')
        elif key == 'sms_notifications_enabled' and value and not settings.ESKIZ_TOKEN:
            card.update(value='Ожидает подключения SMS', hint='Разрешение сохранено. Отправка станет доступна после подключения SMS-сервиса.')
        cards.append(card)
    return cards
