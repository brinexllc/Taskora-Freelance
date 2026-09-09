from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0012_profile_showcase')]
    operations = [
        migrations.AddField(model_name='profile', name='spoken_languages', field=models.JSONField(default=list, blank=True)),
        migrations.AlterField(model_name='profile', name='theme', field=models.CharField(max_length=8, choices=[('light', 'Светлая'), ('dark', 'Тёмная')], default='dark')),
    ]
