from rest_framework import generics, serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Category, Skill
from .pagination import ProjectPagination
from .taxonomy import LANGUAGES, canonical_skill, label_for, normalize_key, resolve_skill_name
from .fees import current_policy


def request_language(request):
    lang = request.query_params.get('lang', 'ru') if request else 'ru'
    if lang not in LANGUAGES:
        raise serializers.ValidationError({'lang': 'ru | uz | uz-cyrl | en'})
    return lang


class SkillSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    category_slugs = serializers.SlugRelatedField(source='categories', slug_field='slug', many=True, read_only=True)

    def get_label(self, obj):
        return label_for(obj, self.context.get('lang') or request_language(self.context.get('request')))

    class Meta:
        model = Skill
        fields = ['id', 'slug', 'name', 'label', 'labels', 'category_slugs', 'active']


class SelectedSkillField(serializers.Field):
    def __init__(self, by_id=False, **kwargs):
        self.by_id = by_id
        super().__init__(**kwargs)

    def to_representation(self, value):
        return [s.pk if self.by_id else s.name for s in value.all()]

    def to_internal_value(self, data):
        if not isinstance(data, list) or len(data) > 30:
            raise serializers.ValidationError('Выберите до 30 навыков.')
        existing = set(self.parent.instance.skills.values_list('pk', flat=True)) if self.parent.instance else set()
        selected = {}
        for value in data:
            if self.by_id:
                pk = serializers.IntegerField(min_value=1).run_validation(value)
                skill = Skill.objects.filter(pk=pk).first()
                skill = canonical_skill(skill) if skill else None
            else:
                value = serializers.CharField(max_length=180).run_validation(value)
                skill = resolve_skill_name(value)
            if not skill or (not skill.active and skill.pk not in existing):
                raise serializers.ValidationError('Выберите активный навык из справочника.')
            selected[skill.pk] = skill
        return list(selected.values())


class SkillsWriteSerializer(serializers.ModelSerializer):
    skills = SelectedSkillField(required=False)
    skill_ids = SelectedSkillField(by_id=True, required=False, write_only=True)
    skill_details = SkillSerializer(source='skills', many=True, read_only=True)

    def validate(self, attrs):
        ids = attrs.pop('skill_ids', None)
        names = attrs.get('skills')
        if ids is not None:
            if names is not None and {s.pk for s in names} != {s.pk for s in ids}:
                raise serializers.ValidationError({'skill_ids': 'skills и skill_ids должны обозначать одинаковый набор.'})
            attrs['skills'] = ids
        return super().validate(attrs)


@api_view(['GET'])
def catalog(request):
    lang = request_language(request)
    return Response({'taxonomy_version': 'catalog-v1', 'categories': [
        {'id': c.pk, 'slug': c.slug, 'name': c.name, 'label': label_for(c, lang), 'active': c.active,
         'sort_order': c.sort_order, 'icon_key': c.icon_key} for c in Category.objects.filter(active=True)]})


@api_view(['GET'])
def platform_fees(request):
    return Response(current_policy())


class SkillListView(generics.ListAPIView):
    serializer_class = SkillSerializer
    pagination_class = ProjectPagination
    filter_backends = []

    def get_queryset(self):
        request_language(self.request)
        qs = Skill.objects.filter(active=True, merged_into__isnull=True).prefetch_related('categories', 'aliases')
        category = self.request.query_params.get('category')
        if category:
            if not Category.objects.filter(slug=category).exists():
                raise serializers.ValidationError({'category': 'Неизвестная категория.'})
            qs = qs.filter(categories__slug=category)
        search = normalize_key(self.request.query_params.get('search', ''))
        # NFKC + casefold work identically on SQLite and PostgreSQL, including all four languages.
        ranked = []
        for skill in qs:
            keys = [normalize_key(skill.name), *[normalize_key(v) for v in skill.labels.values()], *[a.key for a in skill.aliases.all()]]
            if search and not any(search in key for key in keys):
                continue
            rank = 0 if search in keys else 1 if any(k.startswith(search) for k in keys) else 2
            ranked.append((rank, normalize_key(skill.name), skill.pk, skill))
        return [item[-1] for item in sorted(ranked, key=lambda item: item[:3])]


def filter_skills(qs, params):
    match = params.get('skill_match', 'all')
    if match not in {'all', 'any'}:
        raise serializers.ValidationError({'skill_match': 'all | any'})
    ids = params.getlist('skill_id')
    selected = set()
    for value in ids:
        pk = serializers.IntegerField(min_value=1).run_validation(value)
        skill = Skill.objects.filter(pk=pk).first()
        if not skill:
            raise serializers.ValidationError({'skill_id': 'Неизвестный навык.'})
        selected.add(canonical_skill(skill).pk)
    if selected:
        if match == 'any':
            qs = qs.filter(skills__pk__in=selected)
        else:
            for pk in sorted(selected):
                qs = qs.filter(skills__pk=pk)
    if params.get('skill'):
        skill = resolve_skill_name(params['skill'])
        if not skill:
            raise serializers.ValidationError({'skill': 'Неизвестный навык.'})
        qs = qs.filter(skills=skill)
    return qs.distinct()
