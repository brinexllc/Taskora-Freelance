"""Bounded Russian forms; previews carry version and immutable operation UUID."""
import uuid
import re

from django import forms

from .content_models import LANGUAGES
from .content_services import HOME_KEYS, SETTINGS_SCHEMA

HOME_LABELS = {
    'heroA':'Заголовок: первая строка','heroB':'Заголовок: вторая строка','heroC':'Заголовок: акцент',
    'designHeroText':'Описание в первом экране','trustText':'Обещание платформы','designSecureTitle':'Заголовок блока безопасности',
    'designSecureText':'Описание безопасности','securePayment':'Карточка безопасной оплаты: заголовок',
    'designEscrowText':'Карточка безопасной оплаты: текст','designMatching':'Карточка подбора: заголовок',
    'designMatchingText':'Карточка подбора: текст','oneidFeature':'Карточка проверки личности: заголовок',
    'oneidFeatureText':'Карточка проверки личности: текст','designSteps':'Заголовок этапов работы',
    'designStepsText':'Описание этапов работы','designStep1':'Первый шаг: заголовок','designStep1Text':'Первый шаг: текст',
    'designStep2':'Второй шаг: заголовок','designStep2Text':'Второй шаг: текст','designStep3':'Третий шаг: заголовок',
    'designStep3Text':'Третий шаг: текст','designTopFreelancers':'Подпись списка фрилансеров','specialists':'Заголовок специалистов',
    'today':'Призыв начать работу: заголовок','designCtaText':'Призыв начать работу: текст','designCompany':'Ссылка «Компания»',
    'designSupport':'Ссылка «Поддержка»','designMadeIn':'Подпись страны в подвале','footerPlatform':'Ссылка «Платформа»',
    'aboutPlatform':'Ссылка «О платформе»',
}


class ContentDraftForm(forms.Form):
    language = forms.ChoiceField(label='Язык редакции', choices=LANGUAGES, disabled=True)
    approved = forms.BooleanField(label='Редакция юридически согласована владельцем', required=False)
    reason = forms.CharField(label='Основание', min_length=10, max_length=2000, widget=forms.Textarea(attrs={'rows': 3}))
    expected_version = forms.IntegerField(widget=forms.HiddenInput, min_value=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        payload = self.initial.get('payload', {})
        self.section_fields = []
        legal = []
        for key, label in [('terms','Условия использования'),('privacy','Политика конфиденциальности'),('fees','Правила комиссии'),('support_guidance','Как обратиться за помощью'),('notice','Юридическое примечание')]:
            self.fields[key] = forms.CharField(label=label, max_length=10000, required=key in {'terms','privacy'}, widget=forms.Textarea(attrs={'rows':6 if key in {'terms','privacy'} else 3}))
            self.initial[key] = payload.get(key,'')
            legal.append(key)
        self.fields['how_it_works'] = forms.CharField(label='Шаги работы с сервисом', required=False, widget=forms.Textarea(attrs={'rows':4}), help_text='Каждый шаг — с новой строки.')
        self.initial['how_it_works'] = '\n'.join(payload.get('how_it_works',[]))
        legal.append('how_it_works')
        self.section_fields.append(('Документы и правила',legal))
        contact_fields = []
        for section, mapping in [('operator',{'legal_name':'Юридическое наименование','tax_id':'ИНН организации','address':'Адрес оператора'}),
            ('support',{'email':'Email поддержки','phone':'Телефон поддержки','url':'Ссылка поддержки','response_time':'Срок ответа поддержки','withdrawal_rules':'Срок и правила вывода','refund_rules':'Срок и правила возврата','dispute_rules':'Срок и правила спора'})]:
            for key,label in mapping.items():
                name = f'{section}_{key}'
                self.fields[name] = forms.CharField(label=label,required=False,max_length=3000)
                self.initial[name] = payload.get(section,{}).get(key,'')
                contact_fields.append(name)
        self.section_fields.append(('Оператор и поддержка',contact_fields))
        for key in HOME_KEYS:
            self.fields['home_'+key] = forms.CharField(label=HOME_LABELS[key],max_length=3000,widget=forms.Textarea(attrs={'rows':2}))
            self.initial['home_'+key] = payload.get('homepage',{}).get(key,'')
        self.section_fields.append(('Главная страница',['home_'+key for key in HOME_KEYS]))
        self.fields['faq_text'] = forms.CharField(label='Вопросы и ответы',required=False,max_length=150000,widget=forms.Textarea(attrs={'rows':10}),help_text='Первая строка — вопрос, следующие строки — ответ. Разделяйте разные вопросы пустой строкой. До 50 вопросов.')
        self.initial['faq_text'] = '\n\n'.join(item['question']+'\n'+item['answer'] for item in payload.get('faq',[]))
        self.section_fields.append(('FAQ',['faq_text']))

    def sections(self):
        return [{'title':title,'fields':[self[name] for name in names]} for title,names in self.section_fields]

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        payload = {key:data[key] for key in ['terms','privacy','fees','support_guidance','notice']}
        payload['how_it_works'] = [line.strip() for line in data['how_it_works'].splitlines() if line.strip()]
        for section in ['operator','support']:
            payload[section] = {name[len(section)+1:]:value for name,value in data.items() if name.startswith(section+'_') and name not in {'support_guidance'} and value}
        payload['homepage'] = {key:data['home_'+key] for key in HOME_KEYS}
        payload['faq'] = []
        for block in re.split(r'\n\s*\n',data['faq_text'].strip()):
            if not block.strip(): continue
            lines = block.splitlines()
            if len(lines)<2:
                self.add_error('faq_text','У каждого вопроса должен быть ответ со следующей строки.')
                return data
            payload['faq'].append({'question':lines[0].strip(),'answer':'\n'.join(lines[1:]).strip()})
        from .content_services import validate_payload
        from rest_framework.exceptions import ValidationError as ServiceValidationError
        try:
            payload = validate_payload(payload)
        except ServiceValidationError as exc:
            raise forms.ValidationError(str(exc.detail))
        return {**{key:data[key] for key in ['language','approved','reason','expected_version']},'payload':payload}


class ContentPublishForm(forms.Form):
    expected_version = forms.IntegerField(widget=forms.HiddenInput, min_value=0)
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    effective_at = forms.DateTimeField(label='Дата вступления в силу', required=False, help_text='По умолчанию — сразу. Часовой пояс Asia/Tashkent.')
    reason = forms.CharField(label='Основание публикации', min_length=10, max_length=2000, widget=forms.Textarea(attrs={'rows': 3}))


class PlatformSettingForm(forms.Form):
    key = forms.ChoiceField(label='Настройка', choices=[(key, value['label']) for key, value in SETTINGS_SCHEMA.items()])
    value = forms.JSONField(label='Новое значение (JSON)', help_text='Логическое: true/false; строка: "post"; комиссия: "5.00"; срок: 48.')
    reason = forms.CharField(label='Основание', min_length=10, max_length=2000, widget=forms.Textarea(attrs={'rows': 3}))
    expected_version = forms.IntegerField(widget=forms.HiddenInput, min_value=0)
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    effective_at = forms.DateTimeField(label='Дата вступления в силу', required=False)

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        key = self.initial.get('key') or self.data.get('key')
        schema = SETTINGS_SCHEMA.get(key)
        if not schema:return
        self.fields['key'].disabled = True
        if schema['type']=='boolean':
            self.fields['value'] = forms.TypedChoiceField(label='Новое значение',choices=[('true','Включено'),('false','Выключено')],coerce=lambda value:value=='true')
            self.initial['value'] = 'true' if self.initial.get('value') else 'false'
        elif schema['type']=='integer':
            self.fields['value'] = forms.IntegerField(label='Новое значение',min_value=schema['min'],max_value=schema['max'])
        elif schema['type']=='decimal':
            self.fields['value'] = forms.DecimalField(label='Новая комиссия, %',min_value=0,max_value=100,max_digits=5,decimal_places=2)
        else:
            labels={'pre':'До публикации','post':'После публикации'}
            self.fields['value'] = forms.ChoiceField(label='Режим',choices=[(value,labels.get(value,value)) for value in schema['choices']])

    def clean_value(self):
        value = self.cleaned_data['value']
        from decimal import Decimal
        return str(value) if isinstance(value,Decimal) else value


class AnnouncementForm(forms.Form):
    title = forms.CharField(label='Заголовок', max_length=120)
    text = forms.CharField(label='Текст внутреннего уведомления', max_length=500, widget=forms.Textarea(attrs={'rows': 5}))
    link = forms.CharField(label='Ссылка', max_length=200, required=False)
    role = forms.ChoiceField(label='Аудитория',choices=[('','Все активные пользователи'),('client','Заказчики'),('freelancer','Фрилансеры')],required=False)
    registered_from = forms.DateTimeField(label='Регистрация с',required=False,help_text='Часовой пояс Asia/Tashkent.')
    registered_to = forms.DateTimeField(label='Регистрация до (не включая)',required=False)
    reason = forms.CharField(label='Основание', min_length=10, max_length=2000, widget=forms.Textarea(attrs={'rows': 3}))

    def clean(self):
        data=super().clean()
        audience={key:value.isoformat() if hasattr(value,'isoformat') else value for key,value in data.items() if key in {'role','registered_from','registered_to'} and value}
        if data.get('registered_from') and data.get('registered_to') and data['registered_from']>=data['registered_to']:
            raise forms.ValidationError('Начало периода должно быть раньше окончания.')
        return {**{key:value for key,value in data.items() if key not in {'role','registered_from','registered_to'}},'audience':audience}


class JobForm(forms.Form):
    kind = forms.ChoiceField(label='Задача', choices=[('diagnostics', 'Обновить диагностику'), ('reconcile', 'Сверить финансы'), ('retry', 'Повторить безопасную обработку напоминаний')])
    reason = forms.CharField(label='Основание', min_length=10, max_length=2000, widget=forms.Textarea(attrs={'rows': 3}))
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)


class ExportForm(forms.Form):
    dataset = forms.ChoiceField(label='Данные', choices=[('users', 'Пользователи'), ('projects', 'Заказы'), ('contracts', 'Договоры'), ('payments', 'Платежи'), ('withdrawals', 'Выводы'), ('fees', 'Комиссии'), ('audit', 'Аудит')])
    filters = forms.JSONField(label='Фильтры списка', required=False, initial=dict, widget=forms.HiddenInput)
    reveal_contacts = forms.BooleanField(label='Раскрыть контакты пользователей в выгрузке', required=False)
    contact_reason = forms.CharField(label='Отдельное основание раскрытия контактов', min_length=10, max_length=2000, required=False)
    reason = forms.CharField(label='Основание экспорта', min_length=10, max_length=2000)
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
