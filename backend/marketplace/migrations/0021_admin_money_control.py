from django.db import migrations
from django.utils import timezone


def seed_money_control(apps, schema_editor):
    Setting = apps.get_model('marketplace', 'PlatformSettingRevision')
    now = timezone.now()
    Setting.objects.using(schema_editor.connection.alias).get_or_create(
        key='real_money_enabled', version=1,
        defaults={'value': False, 'published_at': now, 'effective_at': now,
            'reason': 'Начальная настройка: до решения владельца сохраняется прежний режим окружения.'})


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0020_admin_content_operations')]
    operations = [migrations.RunPython(seed_money_control, migrations.RunPython.noop)]
