from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0011_catalog_constraints')]
    operations = [
        migrations.AddField(model_name='profile', name='professional_title', field=models.CharField(blank=True, max_length=160)),
        migrations.AddField(model_name='profile', name='location', field=models.CharField(blank=True, max_length=160)),
        migrations.AddField(model_name='profile', name='portfolio', field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name='profile', name='services', field=models.JSONField(blank=True, default=list)),
    ]
