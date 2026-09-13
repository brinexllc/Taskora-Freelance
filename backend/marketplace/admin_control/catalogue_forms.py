"""Native creation forms for catalogue entries; identifiers are assigned only here."""
import uuid

from django import forms

from ..models import Category, Skill
from .content_models import LANGUAGES


ICONS = [('code','Разработка'),('smartphone','Мобильные приложения'),('bot','Автоматизация'),
    ('palette','Дизайн'),('megaphone','Маркетинг'),('pen','Тексты'),('shield','Безопасность'),('folder','Другое')]


class CatalogueCreateForm(forms.Form):
    reason = forms.CharField(label='Основание создания',min_length=10,max_length=1000,widget=forms.Textarea(attrs={'rows':3}))
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    confirmed = forms.BooleanField(label='Я проверил данные и подтверждаю создание')

    def __init__(self,kind,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.kind=kind
        if kind not in {'category','skill','alias','categoryskill'}:
            raise ValueError('Unknown catalogue entry kind')
        if kind in {'category','skill'}:
            self.fields['name']=forms.CharField(label='Название категории' if kind=='category' else 'Название навыка',max_length=100 if kind=='category' else 60)
            self.fields['slug']=forms.SlugField(label='Постоянный код в адресах',max_length=24 if kind=='category' else 100,
                allow_unicode=kind=='skill',required=kind=='category',help_text='После создания код неизменяем. Для навыка можно оставить пустым: код будет создан из названия.')
            for language,label in LANGUAGES:
                self.fields['label_'+language]=forms.CharField(label='Название — '+label,max_length=160,required=False)
            self.fields['active']=forms.BooleanField(label='Доступен для новых выборов',initial=True,required=False)
        if kind=='category':
            self.fields['sort_order']=forms.IntegerField(label='Порядок в каталоге',min_value=0,max_value=2147483647,initial=100)
            self.fields['icon_key']=forms.ChoiceField(label='Иконка',choices=ICONS,initial='folder')
        if kind=='alias':
            self.fields['key']=forms.CharField(label='Синоним навыка',max_length=180,help_text='Регистр и повторяющиеся пробелы будут нормализованы. Синоним не подтверждает навык пользователя.')
        if kind in {'alias','categoryskill'}:
            self.fields['skill_id']=forms.ModelChoiceField(label='Канонический навык',queryset=Skill.objects.filter(active=True,merged_into__isnull=True).order_by('name'))
        if kind=='categoryskill':
            self.fields['category_id']=forms.ModelChoiceField(label='Категория',queryset=Category.objects.filter(active=True).order_by('sort_order','name'))
            self.fields['sort_order']=forms.IntegerField(label='Порядок навыка в категории',min_value=0,max_value=2147483647,initial=0)
        self.order_fields([name for name in self.fields if name not in {'reason','confirmed'}]+['reason','confirmed'])

    def clean(self):
        data=super().clean()
        if self.errors:
            return data
        changes={name:value.pk if hasattr(value,'pk') else value for name,value in data.items()
            if name not in {'reason','idempotency_key','confirmed'} and not name.startswith('label_')}
        if self.kind in {'category','skill'}:
            changes['labels']={language:data['label_'+language] for language,_ in LANGUAGES if data.get('label_'+language)}
        return {'reason':data['reason'],'idempotency_key':str(data['idempotency_key']),'confirmed':data['confirmed'],
            'kind':self.kind,'changes':changes}
