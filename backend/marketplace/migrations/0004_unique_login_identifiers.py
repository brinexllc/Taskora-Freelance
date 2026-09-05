from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0003_contract_deliverable_payment_walletentry_withdrawal_and_more")]
    # Both supported databases (PostgreSQL and SQLite) support these expression indexes.
    # Do not merge accounts automatically if pre-existing manual records conflict.
    operations = [
        migrations.RunSQL(
            "CREATE UNIQUE INDEX taskora_username_ci ON auth_user (LOWER(username))",
            "DROP INDEX taskora_username_ci",
        ),
        migrations.RunSQL(
            "CREATE UNIQUE INDEX taskora_email_ci ON auth_user (LOWER(email)) WHERE email <> ''",
            "DROP INDEX taskora_email_ci",
        ),
    ]
