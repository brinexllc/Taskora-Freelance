from django.db import migrations, models


def migrate_skills(apps, schema_editor):
    alias = schema_editor.connection.alias
    Skill = apps.get_model('marketplace', 'Skill')
    for model_name in ('Profile', 'Project'):
        Model = apps.get_model('marketplace', model_name)
        for record in Model.objects.using(alias).iterator():
            names = record.legacy_skills or []
            if not isinstance(names, list) or any(not isinstance(name, str) or not name.strip() or len(name) > 60 for name in names):
                raise RuntimeError(f'Invalid skills in {model_name} #{record.pk}; fix the legacy value before migrating.')
            links = [Skill.objects.using(alias).get_or_create(name=name)[0].pk for name in dict.fromkeys(names)]
            record.skills.set(links)


def restore_skills(apps, schema_editor):
    alias = schema_editor.connection.alias
    for model_name in ('Profile', 'Project'):
        Model = apps.get_model('marketplace', model_name)
        for record in Model.objects.using(alias).iterator():
            record.legacy_skills = list(record.skills.values_list('name', flat=True))
            record.save(using=alias, update_fields=['legacy_skills'])


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0006_payment_payme_trans_id_payment_provider_data')]

    operations = [
        migrations.RenameField(model_name='profile', old_name='skills', new_name='legacy_skills'),
        migrations.RenameField(model_name='project', old_name='skills', new_name='legacy_skills'),
        migrations.AddField(model_name='profile', name='skills', field=models.ManyToManyField(blank=True, related_name='profiles', to='marketplace.skill', verbose_name='Навыки')),
        migrations.AddField(model_name='project', name='skills', field=models.ManyToManyField(blank=True, related_name='projects', to='marketplace.skill', verbose_name='Навыки')),
        migrations.RunPython(migrate_skills, restore_skills),
        migrations.RemoveField(model_name='profile', name='legacy_skills'),
        migrations.RemoveField(model_name='project', name='legacy_skills'),
    ]
