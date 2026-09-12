from django.db import migrations


def inventory_legacy_withdrawals(apps, schema_editor):
    Withdrawal = apps.get_model('marketplace', 'Withdrawal')
    Withdrawal.objects.using(schema_editor.connection.alias).filter(status='pending', claimed_at__isnull=True).update(
        status='reconciliation_required', resolution_reason='legacy payout inventory required')


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0015_audit_stabilization')]
    operations = [migrations.RunPython(inventory_legacy_withdrawals, migrations.RunPython.noop)]
