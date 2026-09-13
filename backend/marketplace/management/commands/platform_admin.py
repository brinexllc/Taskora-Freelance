"""Trusted-console provisioning/recovery; never exposes credentials in the panel."""
import getpass
import os
import sys
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token

from marketplace.models import AuditLog, PasswordResetCode, Profile
from marketplace.security import revoke_user_sessions
from marketplace.security_models import ContactVerification, MultiFactorCredential, ScopedApiToken


class Command(BaseCommand):
    help = 'Создать или восстановить администратора через доверенную серверную консоль с аудитом.'

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('--reason', required=True)
        parser.add_argument('--email', default='')
        parser.add_argument('--create', action='store_true', help='Создать новую учётную запись.')
        parser.add_argument('--recover-mfa', action='store_true', help='Отозвать утраченный MFA; потребуется новое подключение.')
        parser.add_argument('--password-env', default='TASKORA_ADMIN_PASSWORD', help='Имя переменной окружения с новым паролем; иначе защищённый интерактивный ввод.')

    @transaction.atomic
    def handle(self, *args, **options):
        reason = options['reason'].strip()
        if len(reason) < 10:
            raise CommandError('Укажите основание не короче 10 символов.')
        User = get_user_model()
        user = User.objects.select_for_update().filter(username=options['username']).first()
        if options['create'] and user:
            raise CommandError('Учётная запись существует. Для восстановления не используйте --create.')
        if not options['create'] and not user:
            raise CommandError('Учётная запись не найдена. Для создания используйте --create.')
        if not user:
            user = User(username=options['username'], email=options['email'])
        before = {'is_active': user.is_active, 'is_staff': user.is_staff, 'is_superuser': user.is_superuser} if user.pk else {}
        password = os.environ.get(options['password_env'])
        if not password:
            if not sys.stdin.isatty():
                raise CommandError('Передайте новый пароль через указанную переменную окружения или интерактивную консоль.')
            password = getpass.getpass('Новый пароль администратора: ')
            if password != getpass.getpass('Повторите новый пароль: '):
                raise CommandError('Пароли не совпадают.')
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        user.set_password(password)
        user.is_active = user.is_staff = user.is_superuser = True
        user.save()
        Profile.objects.get_or_create(user=user, defaults={'full_name': user.get_full_name() or user.username})
        revoke_user_sessions(user)
        Token.objects.filter(user=user).delete()
        now = timezone.now()
        ScopedApiToken.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=now)
        PasswordResetCode.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
        ContactVerification.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
        if options['recover_mfa']:
            MultiFactorCredential.objects.filter(user=user).delete()
        request_id = str(uuid.uuid4())
        AuditLog.objects.create(actor=None, action='platform_admin_created' if options['create'] else 'platform_admin_recovered',
            object_type='user', object_id=str(user.pk), reason=reason, before=before,
            after={'is_active': True, 'is_staff': True, 'is_superuser': True}, request_id=request_id, detail={
                'task': 'platform_admin', 'reason': reason, 'before': before,
                'after': {'is_active': True, 'is_staff': True, 'is_superuser': True},
                'mfa_reset': options['recover_mfa'], 'request_id': request_id, 'outcome': 'success'})
        self.stdout.write(self.style.SUCCESS(f'Администратор #{user.pk} готов. Старые сессии отозваны. Вход в панель требует MFA.'))
