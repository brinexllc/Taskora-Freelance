"""Canonical skill identity, aliases and transactional, auditable merges."""
import unicodedata

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.text import slugify

LANGUAGES = {'ru', 'uz', 'uz-cyrl', 'en'}


def normalize_key(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def validate_identity(obj):
    if not isinstance(obj.labels, dict) or any(k not in LANGUAGES or not isinstance(v, str) or not v.strip() for k, v in obj.labels.items()):
        raise ValidationError({'labels': 'Ожидаются непустые переводы ru, uz, uz-cyrl, en.'})
    if obj.pk:
        old_slug = type(obj).objects.filter(pk=obj.pk).values_list('slug', flat=True).first()
        if old_slug and old_slug != obj.slug:
            raise ValidationError({'slug': 'Slug назначается один раз.'})


def skill_slug(name):
    return {'c#': 'csharp', 'c++': 'cpp'}.get(normalize_key(name), slugify(name, allow_unicode=True) or 'skill')


@transaction.atomic
def save_skill(obj, *args, **kwargs):
    from .models import Skill, SkillAlias
    obj.name = ' '.join(unicodedata.normalize('NFKC', obj.name).split())
    key = normalize_key(obj.name)
    if not key:
        raise ValidationError({'name': 'Укажите название навыка.'})
    if not obj.slug:
        base = skill_slug(obj.name)
        obj.slug = base
        suffix = 2
        while Skill.objects.filter(slug=obj.slug).exclude(pk=obj.pk).exists():
            obj.slug = f'{base}-{suffix}'
            suffix += 1
    validate_identity(obj)
    if not obj.merged_into_id:
        if SkillAlias.objects.filter(key=key).exclude(skill_id=obj.pk).exists():
            raise ValidationError({'name': 'Имя или алиас уже принадлежит другому навыку.'})
        obj.normalized_name = key
    else:
        obj.normalized_name = None
        obj.active = False
    if kwargs.get('update_fields'):
        kwargs['update_fields'] = set(kwargs['update_fields']) | {'normalized_name', 'slug', 'name', 'active'}
    obj.full_clean(exclude=['normalized_name'] if obj.merged_into_id else [])
    models.Model.save(obj, *args, **kwargs)
    if not obj.merged_into_id:
        SkillAlias.objects.get_or_create(key=key, defaults={'skill': obj})


def label_for(obj, lang='ru'):
    return obj.labels.get(lang) or obj.labels.get('ru') or obj.name


def canonical_skill(skill):
    while skill.merged_into_id:
        skill = skill.merged_into
    return skill


def resolve_skill_name(value):
    from .models import SkillAlias
    alias = SkillAlias.objects.select_related('skill').filter(key=normalize_key(value)).first()
    return canonical_skill(alias.skill) if alias else None


def audit(obj, actor, action, before, reason):
    from .models import AuditLog
    from django.forms.models import model_to_dict
    after = model_to_dict(obj, exclude=['categories'])
    AuditLog.objects.create(actor=actor, action=action, object_type=obj._meta.model_name,
                            object_id=str(obj.pk), detail={'before': before, 'after': after, 'reason': reason})


@transaction.atomic
def merge_skills(source_id, target_id, *, actor=None, reason):
    from .models import CategorySkill, Profile, Project, Skill, SkillAlias
    if source_id == target_id or not reason.strip():
        raise ValidationError('Выберите разные навыки и укажите основание.')
    locked = {s.pk: s for s in Skill.objects.select_for_update().filter(pk__in=[source_id, target_id]).order_by('pk')}
    source, target = locked[source_id], locked[target_id]
    if source.merged_into_id or target.merged_into_id or not target.active:
        raise ValidationError('Объединение возможно только в активный канонический навык.')
    before = {'name': source.name, 'profiles': source.profiles.count(), 'projects': source.projects.count()}
    for model in (Profile, Project):
        for record in model.objects.filter(skills=source).iterator():
            record.skills.add(target)
            record.skills.remove(source)
    for link in CategorySkill.objects.filter(skill=source):
        CategorySkill.objects.get_or_create(skill=target, category=link.category, defaults={'sort_order': link.sort_order})
    CategorySkill.objects.filter(skill=source).delete()
    SkillAlias.objects.filter(skill=source).update(skill=target)
    source.merged_into = target
    source.save()
    # Verified labels are intentionally untouched: review is required, never grant verification here.
    audit(source, actor, 'skill_merge', before, reason)
    return target
