"""Versioned publications and durable, private administrative operations."""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


LANGUAGES = [('ru', 'Русский'), ('uz', 'O‘zbekcha'), ('uz-cyrl', 'Ўзбекча'), ('en', 'English')]


class ImmutablePublication(models.Model):
    version = models.PositiveIntegerField()
    base_version = models.PositiveIntegerField(default=0)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    effective_at = models.DateTimeField(null=True, blank=True)
    publication_key = models.UUIDField(null=True, blank=True, unique=True)
    publication_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        abstract = True
        ordering = ['-created_at', '-pk']

    def save(self, *args, **kwargs):
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if old.published_at and any(getattr(old, f.attname) != getattr(self, f.attname) for f in self._meta.concrete_fields):
                raise ValidationError('Опубликованная версия неизменяема. Создайте новую редакцию.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('История публикаций сохраняется.')


class ContentRevision(ImmutablePublication):
    language = models.CharField(max_length=8, choices=LANGUAGES)
    payload = models.JSONField()
    content_hash = models.CharField(max_length=64)
    legal_version = models.CharField(max_length=120)
    approved = models.BooleanField(default=False)

    class Meta(ImmutablePublication.Meta):
        constraints = [models.UniqueConstraint(fields=['language', 'version'], name='unique_content_revision')]
        indexes = [models.Index(fields=['language', 'published_at', 'effective_at'])]
        verbose_name = 'редакция контента'
        verbose_name_plural = 'Редакции контента'

    def __str__(self):
        return f'{self.language} · v{self.version} · {"Опубликовано" if self.published_at else "Черновик"}'

    @property
    def status(self):
        from django.utils import timezone
        return 'draft' if not self.published_at else 'scheduled' if self.effective_at > timezone.now() else 'published'


class PlatformSettingRevision(ImmutablePublication):
    key = models.CharField(max_length=80)
    value = models.JSONField()

    class Meta(ImmutablePublication.Meta):
        constraints = [models.UniqueConstraint(fields=['key', 'version'], name='unique_setting_revision')]
        indexes = [models.Index(fields=['key', 'published_at', 'effective_at'])]
        verbose_name = 'редакция настройки'
        verbose_name_plural = 'Редакции настроек'

    def __str__(self):
        return f'{self.key} · v{self.version}'


class Announcement(models.Model):
    title = models.CharField(max_length=120)
    text = models.CharField(max_length=500)
    link = models.CharField(max_length=200, blank=True)
    audience = models.JSONField(default=dict)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField()
    version = models.PositiveIntegerField(default=1)
    state = models.CharField(max_length=16, choices=[('draft', 'Черновик'), ('previewed', 'Предпросмотр'), ('queued', 'В очереди'), ('sent', 'Отправлено')], default='draft')
    recipient_count = models.PositiveIntegerField(default=0)
    recipient_hash = models.CharField(max_length=64, blank=True)
    previewed_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'объявление'
        verbose_name_plural = 'Объявления'

    def __str__(self):
        return self.title


class AnnouncementRecipient(models.Model):
    announcement = models.ForeignKey(Announcement, on_delete=models.PROTECT, related_name='recipients')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['announcement', 'user'], name='unique_announcement_recipient')]


class NotificationDelivery(models.Model):
    event_key = models.CharField(max_length=160)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    notification = models.OneToOneField('marketplace.Notification', on_delete=models.PROTECT, null=True, blank=True)
    channel = models.CharField(max_length=16, default='internal')
    template = models.CharField(max_length=80)
    status = models.CharField(max_length=24, default='delivered')
    detail = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['event_key', 'user', 'channel'], name='unique_notification_delivery')]
        ordering = ['-created_at', '-pk']
        verbose_name = 'доставка уведомления'
        verbose_name_plural = 'Доставка уведомлений'


class AdminJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=24, choices=[('diagnostics', 'Диагностика'), ('reconcile', 'Сверка'), ('retry', 'Безопасная повторная обработка'), ('export', 'Экспорт CSV'), ('announcement', 'Доставка объявления')])
    state = models.CharField(max_length=16, choices=[('queued', 'В очереди'), ('running', 'Выполняется'), ('succeeded', 'Завершено'), ('failed', 'Ошибка')], default='queued', db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    browser_session = models.ForeignKey('marketplace.BrowserSession', null=True, on_delete=models.PROTECT)
    reason = models.TextField()
    idempotency_key = models.UUIDField(unique=True)
    request_hash = models.CharField(max_length=64)
    dedupe_key = models.CharField(max_length=100)
    parameters = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    progress = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    # Opaque storage identifier, deliberately not a FileField with a public URL.
    storage_name = models.CharField(max_length=160, blank=True, editable=False)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['dedupe_key'], condition=models.Q(state__in=['queued', 'running']), name='unique_active_admin_job')]
        indexes = [models.Index(fields=['kind', 'state', 'created_at'])]
        verbose_name = 'фоновая задача'
        verbose_name_plural = 'Фоновые задачи'

    def __str__(self):
        return f'{self.get_kind_display()} · {self.get_state_display()}'
