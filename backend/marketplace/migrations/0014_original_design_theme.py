from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0013_profile_languages_dark_default')]
    operations = [migrations.AlterField(
        model_name='profile', name='theme',
        field=models.CharField(choices=[('light', 'Светлая'), ('dark', 'Тёмная')], default='light', max_length=8),
    )]
