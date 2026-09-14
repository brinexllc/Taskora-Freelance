"""One effective money policy shared by the API, admin controls and diagnostics."""
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from rest_framework.exceptions import APIException


def money_enabled():
    from .admin_control.content_services import get_setting
    return get_setting('real_money_enabled') is True


def financial_blockers(*, include_switch=True, include_migrations=False):
    from .security import current_legal_content
    blockers = []

    def add(code, message, url, action):
        blockers.append({'code': code, 'message': message, 'url': url, 'action': action})

    if include_switch and not money_enabled():
        add('money_disabled', 'Денежные операции выключены владельцем.',
            '/admin/control/launch/', 'Настроить запуск')
    if settings.TASKORA_ENV in {'staging', 'production'}:
        if settings.PAYME_TEST_MODE:
            add('test_provider', 'Подключение Payme использует тестовый режим. Для реальных операций требуется производственное подключение.',
                '/admin/control/operations/', 'Проверить подключение')
        try:
            document = current_legal_content('ru')
        except (APIException, DjangoValidationError):
            add('legal_unavailable', 'Опубликованные правила временно недоступны.',
                '/admin/control/content/', 'Открыть документы')
        else:
            if document.get('approved') is not True:
                add('legal_unapproved', 'Владелец ещё не подтвердил согласование опубликованных правил.',
                    '/admin/control/new/content/?language=ru', 'Проверить и утвердить правила')
            fields = {
                'operator': {'legal_name': 'наименование оператора', 'tax_id': 'ИНН', 'address': 'адрес оператора'},
                'support': {'email': 'email поддержки', 'response_time': 'срок ответа поддержки',
                    'withdrawal_rules': 'правила вывода', 'refund_rules': 'правила возврата', 'dispute_rules': 'правила споров'},
            }
            for section, labels in fields.items():
                values = document.get(section)
                values = values if isinstance(values, dict) else {}
                missing = [label for key, label in labels.items()
                    if not isinstance(values.get(key), str) or not values[key].strip()]
                if missing:
                    add(section + '_incomplete', 'Заполните: ' + ', '.join(missing) + '.',
                        '/admin/control/new/content/?language=ru', 'Заполнить реквизиты и правила')
            try:
                support = document.get('support')
                validate_email(support.get('email', '') if isinstance(support, dict) else '')
            except DjangoValidationError:
                add('support_email', 'Укажите корректный email поддержки.',
                    '/admin/control/new/content/?language=ru', 'Исправить email')
    if include_migrations:
        from .operations import pending_migrations
        if pending_migrations():
            add('migrations_pending', 'Обновление базы ещё не завершено. Дождитесь успешного выпуска приложения.',
                '/admin/control/operations/', 'Открыть состояние системы')
    return blockers


def financial_operations_enabled():
    return not financial_blockers()
