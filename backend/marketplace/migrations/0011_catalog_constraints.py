"""Separate transaction from data migration: PostgreSQL must flush deferred FK triggers first."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0010_preserve_catalog_identity')]
    operations = [
        migrations.AlterField(model_name='project', name='category', field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='projects', to='marketplace.category', verbose_name='Категория')),
        migrations.AlterField(model_name='project', name='legacy_category', field=models.CharField(default='other', editable=False, max_length=24)),
        migrations.AlterField(model_name='skill', name='slug', field=models.SlugField(unique=True, max_length=100, allow_unicode=True)),
        migrations.AddIndex(model_name='project', index=models.Index(fields=['status', 'category'], name='marketplace_status_d3c1a3_idx')),
    ]
