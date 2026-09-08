"""Map legacy data before enforcing FK/identity constraints. No financial movement."""
import unicodedata
from django.db import migrations
from django.utils.text import slugify


def populate(apps, schema_editor):
    db = schema_editor.connection.alias
    Category = apps.get_model('marketplace', 'Category')
    Project = apps.get_model('marketplace', 'Project')
    Skill = apps.get_model('marketplace', 'Skill')
    Alias = apps.get_model('marketplace', 'SkillAlias')
    Audit = apps.get_model('marketplace', 'AuditLog')
    Contract = apps.get_model('marketplace', 'Contract')
    for slug in Project.objects.using(db).values_list('legacy_category', flat=True).distinct():
        category, created = Category.objects.using(db).get_or_create(slug=slug, defaults={'name': slug, 'active': False})
        if created:
            Audit.objects.using(db).create(action='legacy_category_review', object_type='category', object_id=str(category.pk), detail={'slug': slug, 'reason': 'Unknown legacy category preserved; manual mapping required.'})
        Project.objects.using(db).filter(legacy_category=slug).update(category=category)
    seen, slugs = {}, set()
    for skill in Skill.objects.using(db).order_by('id'):
        key = ' '.join(unicodedata.normalize('NFKC', skill.name).casefold().split())
        base = {'c#': 'csharp', 'c++': 'cpp'}.get(key, slugify(skill.name, allow_unicode=True) or 'skill')
        slug = base if base not in slugs else f'{base}-{skill.pk}'
        slugs.add(slug)
        skill.slug = slug
        target = seen.get(key)
        if target:
            for model in ('Profile', 'Project'):
                Model = apps.get_model('marketplace', model)
                for record in Model.objects.using(db).filter(skills=skill):
                    record.skills.add(target)
                    record.skills.remove(skill)
            skill.active = False
            skill.merged_into_id = target.pk
            Audit.objects.using(db).create(action='skill_merge', object_type='skill', object_id=str(skill.pk), detail={'target': target.pk, 'reason': 'Identical normalized legacy name', 'before': skill.name})
        else:
            skill.normalized_name = key
            seen[key] = skill
            Alias.objects.using(db).create(key=key, skill=skill)
        skill.save(using=db)
    for contract in Contract.objects.using(db).iterator():
        rate = str(contract.fee_percent)
        contract.fee_policy_snapshot = {'currency': contract.currency, 'freelancer_fee_percent': rate,
            'customer_fee_percent': '0.00', 'calculation_basis': 'released_gross', 'policy_version': f'commission-v1:{rate}',
            'payer': 'freelancer', 'rounding': 'ROUND_HALF_UP', 'precision': '0.01', 'source': 'legacy_contract'}
        contract.save(using=db, update_fields=['fee_policy_snapshot'])


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0009_categoryskill_platformfee_skillalias_and_more')]
    operations = [
        migrations.RunPython(populate, migrations.RunPython.noop),
    ]
