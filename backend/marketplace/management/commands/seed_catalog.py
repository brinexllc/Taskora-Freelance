import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.models import model_to_dict
from marketplace.models import AuditLog, Category, CategorySkill, Skill, SkillAlias
from marketplace.taxonomy import audit, merge_skills, normalize_key, resolve_skill_name


class Command(BaseCommand):
    help = 'Idempotent production catalog import. Defaults to dry-run; never creates users or balances.'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument('--dry-run', action='store_true')
        group.add_argument('--apply', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        manifest = json.loads((Path(__file__).parents[2] / 'catalog-v1.json').read_text(encoding='utf-8'))
        report = {'mode': 'apply' if options['apply'] else 'dry-run', 'categories_created': [], 'skills_created': [], 'merged': [], 'review': []}
        try:
            for item in manifest['categories']:
                category, created = Category.objects.get_or_create(slug=item['slug'], defaults={k:v for k,v in item.items() if k != 'slug'})
                if created:
                    report['categories_created'].append(category.slug)
                    audit(category, None, 'catalog_seed', {}, manifest['version'])
                elif not AuditLog.objects.filter(action='catalog_seed', object_type='category', object_id=str(category.pk)).exists():
                    before = model_to_dict(category)
                    # Preserve custom names and inactive state. Only replace the five original seed labels.
                    original = {'development':'Разработка','design':'Дизайн','marketing':'Маркетинг','writing':'Тексты','other':'Другое'}
                    if category.name == original.get(category.slug):
                        category.name = item['name']
                    if not category.labels:
                        category.labels = {**item['labels'], 'ru': category.name}
                    if category.sort_order == 100:
                        category.sort_order = item['sort_order']
                    if category.icon_key == 'folder':
                        category.icon_key = item['icon_key']
                    category.save()
                    audit(category, None, 'catalog_seed', before, manifest['version'])
            for item in manifest['skills']:
                candidates = [s for key in [item['name'], *item['aliases']] if (s := resolve_skill_name(key))]
                skill = resolve_skill_name(item['name']) or (candidates[0] if candidates else None)
                if skill is None:
                    skill = Skill.objects.create(name=item['name'], slug=item['slug'], labels=item['labels'])
                    report['skills_created'].append(skill.name)
                initialized = AuditLog.objects.filter(action='catalog_seed', object_type='skill', object_id=str(skill.pk)).exists()
                if not initialized:
                    before = model_to_dict(skill, exclude=['categories'])
                    if normalize_key(skill.name) in {normalize_key(n) for n in item['aliases']}:
                        skill.name = item['name']
                    if not skill.labels:
                        skill.labels = item['labels']
                    skill.save()
                    for source in {s.pk: s for s in candidates}.values():
                        if source.pk != skill.pk and not source.merged_into_id:
                            merge_skills(source.pk, skill.pk, reason=f'{manifest["version"]}: explicit synonym')
                            report['merged'].append({'source': source.pk, 'target': skill.pk})
                    for alias in [item['name'], *item['aliases']]:
                        key = normalize_key(alias)
                        entry, created = SkillAlias.objects.get_or_create(key=key, defaults={'skill': skill})
                        if entry.skill_id != skill.pk:
                            raise CommandError(f'Alias conflict: {key}')
                    for order, slug in enumerate(item['categories']):
                        CategorySkill.objects.get_or_create(skill=skill, category=Category.objects.get(slug=slug), defaults={'sort_order': order})
                    audit(skill, None, 'catalog_seed', before, manifest['version'])
            for skill in Skill.objects.filter(name__in=['Analytics','Strategy'], merged_into__isnull=True):
                report['review'].append({'id':skill.pk,'name':skill.name,'profiles':skill.profiles.count(),'projects':skill.projects.count(),'proposal':'Preserve; broad meaning requires owner review.'})
            report['review'] += list(AuditLog.objects.filter(action='legacy_category_review').values('object_id','detail'))
            report['active_categories'] = Category.objects.filter(active=True).count()
            report['canonical_skills'] = Skill.objects.filter(merged_into__isnull=True).count()
            if not options['apply']:
                transaction.set_rollback(True)
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        except ValidationError as exc:
            raise CommandError(str(exc))
