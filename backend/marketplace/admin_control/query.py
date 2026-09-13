"""Bounded, explicit read models for the Taskora administrative workspace."""
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum, Max, OuterRef, Subquery, IntegerField, Value
from django.db.models.functions import TruncDate, Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_date


NAV = [
    ('overview', 'Обзор', 'grid', '/admin/'),
    ('users', 'Пользователи', 'users', '/admin/control/users/'),
    ('projects', 'Заказы и отклики', 'briefcase', '/admin/control/projects/'),
    ('contracts', 'Договоры и результаты', 'file', '/admin/control/contracts/'),
    ('disputes', 'Споры', 'shield', '/admin/control/disputes/'),
    ('finance', 'Финансы', 'wallet', '/admin/control/finance/'),
    ('messages', 'Сообщения и обращения', 'message', '/admin/control/messages/'),
    ('reviews', 'Отзывы', 'star', '/admin/control/reviews/'),
    ('catalogue', 'Категории и навыки', 'layers', '/admin/control/catalogue/'),
    ('content', 'Контент и уведомления', 'edit', '/admin/control/content/'),
    ('settings', 'Настройки', 'settings', '/admin/control/settings/'),
    ('operations', 'Состояние системы', 'activity', '/admin/control/operations/'),
    ('audit', 'Журнал действий', 'history', '/admin/control/audit/'),
]

# Every display field is allowed explicitly; credentials and private file paths are never serialized.
RESOURCES = {
 'users': ('User', 'Пользователи', 'users', [('id','ID'),('username','Пользователь'),('profile.full_name','Имя'),('email','Email'),('profile.phone','Телефон'),('profile.enabled_roles','Режимы'),('is_active','Активен'),('date_joined','Регистрация')], ['username','email','profile__full_name','profile__phone'], 'date_joined'),
 'projects': ('Project','Заказы','projects',[('id','ID'),('title','Заказ'),('owner','Заказчик'),('category','Категория'),('budget_max','Бюджет, UZS'),('status','Статус сделки'),('moderation_status','Модерация'),('featured','Рекомендуемый'),('created_at','Создан')], ['title','owner__username'], 'created_at'),
 'proposals': ('Proposal','Отклики','projects',[('id','ID'),('project','Заказ'),('freelancer','Исполнитель'),('amount','Сумма, UZS'),('delivery_days','Дней'),('status','Статус'),('created_at','Получен')], ['project__title','freelancer__username'],'created_at'),
 'contracts': ('Contract','Договоры','contracts',[('id','ID'),('project','Договор'),('customer','Заказчик'),('freelancer','Исполнитель'),('amount','Сумма, UZS'),('escrow_amount','Резерв, UZS'),('status','Статус'),('created_at','Создан')], ['project__title','customer__username','freelancer__username'],'created_at'),
 'deliverables': ('Deliverable','Результаты работы','contracts',[('id','ID'),('contract','Договор'),('contract_version','Версия'),('filename','Файл'),('review_due_at','Приёмка до'),('review_escalated_at','Эскалация'),('created_at','Сдан')], ['contract__project__title','filename'],'created_at'),
 'amendments': ('ContractAmendment','Изменения условий','contracts',[('id','ID'),('contract','Договор'),('base_version','Исходная версия'),('proposed_by','Инициатор'),('customer_accepted_at','Согласие заказчика'),('freelancer_accepted_at','Согласие исполнителя'),('applied_at','Применено')], ['contract__project__title'],'created_at'),
 'disputes': ('Dispute','Споры','disputes',[('id','ID'),('contract','Договор'),('contract.customer','Заказчик'),('contract.freelancer','Исполнитель'),('contract.escrow_amount','Резерв, UZS'),('status','Стадия'),('created_at','Открыт')], ['contract__project__title','reason'],'created_at'),
 'wallets': ('Profile','Кошельки','finance',[('user_id','ID'),('user','Пользователь'),('full_name','Имя'),('balance','Доступно, UZS'),('created_at','Создан')], ['user__username','full_name'],'created_at'),
 'ledger': ('WalletEntry','Движения средств','finance',[('reference','Операция'),('user','Пользователь'),('kind','Вид движения'),('amount','Сумма, UZS'),('contract','Договор'),('payment_id','Платёж'),('withdrawal_id','Вывод'),('created_at','Дата')], ['user__username','description'],'created_at'),
 'payments': ('Payment','Платежи','finance',[('reference','Платёж'),('user','Пользователь'),('amount','Сумма, UZS'),('provider','Провайдер'),('status','Статус'),('paid_at','Подтверждён'),('created_at','Создан')], ['user__username','click_trans_id','payme_trans_id'],'created_at'),
 'withdrawals': ('Withdrawal','Выводы средств','finance',[('id','ID'),('user','Пользователь'),('amount','Сумма, UZS'),('destination','Получатель'),('status','Статус'),('provider_reference','Внешняя операция'),('created_at','Заявка')], ['user__username','provider_reference'],'created_at'),
 'fees': ('PlatformFee','Комиссия платформы','finance',[('reference','Операция'),('contract','Договор'),('gross_amount','До комиссии, UZS'),('fee_percent','Ставка, %'),('fee_amount','Комиссия, UZS'),('created_at','Начислена')], ['contract__project__title'],'created_at'),
 'receipts': ('ClickFiscalReceipt','Фискальные чеки','finance',[('id','ID'),('payment','Платёж'),('status','Состояние'),('attempts','Попытки'),('last_error','Последняя ошибка'),('next_attempt_at','Следующая попытка'),('updated_at','Обновлён')], ['click_payment_id'],'created_at'),
 'conversations': ('Contract','Переписка по договорам','messages',[('id','Договор'),('project','Заказ'),('customer','Заказчик'),('freelancer','Исполнитель'),('message_count','Сообщений'),('last_message','Активность')], ['project__title','customer__username','freelancer__username'],'created_at'),
 'proposal-conversations': ('ProposalConversation','Обсуждения откликов','messages',[('id','Обсуждение'),('proposal.project','Заказ'),('proposal.freelancer','Исполнитель'),('message_count','Сообщений'),('last_message','Активность')], ['proposal__project__title','proposal__freelancer__username'],'created_at'),
 'reports': ('ContentReport','Жалобы','messages',[('id','ID'),('reporter','Автор'),('object_type','Объект'),('object_id','ID объекта'),('status','Состояние'),('created_at','Получена')], ['reporter__username','reason'],'created_at'),
 'proposal-reports': ('ProposalReport','Жалобы на отклики','messages',[('id','ID'),('reporter','Автор'),('conversation_id','Обсуждение'),('status','Состояние'),('created_at','Получена'),('resolved_at','Закрыта')], ['reporter__username','reason'],'created_at'),
 'support': ('SupportTicket','Поддержка','messages',[('id','ID'),('author','Автор'),('subject','Тема'),('status','Состояние'),('created_at','Создано'),('updated_at','Обновлено')], ['subject','author__username'],'created_at'),
 'reviews': ('Review','Отзывы','reviews',[('id','ID'),('author','Автор'),('target','Получатель'),('contract','Договор'),('rating','Оценка'),('published','Опубликован'),('created_at','Создан')], ['author__username','target__username','text'],'created_at'),
 'categories': ('Category','Категории','catalogue',[('id','ID'),('name','Название'),('slug','Slug'),('active','Активна'),('sort_order','Порядок'),('icon_key','Иконка')], ['name','slug'],None),
 'skills': ('Skill','Навыки','catalogue',[('id','ID'),('name','Навык'),('slug','Slug'),('active','Активен'),('profile_count','Профилей'),('project_count','Заказов'),('merged_into','Объединён с')], ['name','slug','aliases__key'],None),
 'verifications': ('SkillVerification','Подтверждения навыков','catalogue',[('id','ID'),('user','Пользователь'),('skill','Навык'),('status','Состояние'),('created_at','Подано'),('expires_at','Действует до')], ['user__username','skill__name'],'created_at'),
 'content-revisions': ('ContentRevision','Версии контента','content',[('id','ID'),('language','Язык'),('version','Версия'),('status','Состояние'),('created_at','Создана'),('published_at','Опубликована')], [],'created_at'),
 'setting-revisions': ('PlatformSettingRevision','История настроек','settings',[('id','ID'),('key','Параметр'),('value','Значение'),('version','Версия'),('created_at','Создана')], ['key'],'created_at'),
 'notifications': ('Notification','Внутренние уведомления','content',[('id','ID'),('user','Получатель'),('kind','Событие'),('text','Сообщение'),('read_at','Прочитано'),('created_at','Создано')], ['user__username','kind','text'],'created_at'),
 'jobs': ('AdminJob','Фоновые задачи','operations',[('id','ID'),('kind','Задача'),('state','Состояние'),('created_at','Создана'),('started_at','Начало'),('finished_at','Завершение')], ['kind'],'created_at'),
 'announcements': ('Announcement','Объявления','content',[('id','ID'),('title','Заголовок'),('state','Состояние'),('recipient_count','Получателей'),('created_at','Создано'),('sent_at','Отправлено')], ['title','text'],'created_at'),
 'deliveries': ('NotificationDelivery','Доставка уведомлений','content',[('id','ID'),('user','Получатель'),('template','Шаблон'),('channel','Канал'),('status','Состояние'),('created_at','Создано'),('delivered_at','Доставлено')], ['template','event_key','user__username'],'created_at'),
 'obligations': ('AdminObligation','Незакрытые обязательства','operations',[('id','ID'),('user','Пользователь'),('object_type','Объект'),('object_id','ID объекта'),('status','Состояние'),('created_at','Создано')], ['user__username'],'created_at'),
 'audit': ('AuditLog','Журнал действий','audit',[('id','ID'),('actor','Администратор'),('action','Действие'),('object_type','Объект'),('object_id','ID объекта'),('reason','Основание'),('outcome','Результат'),('created_at','Время')], ['actor__username','action','object_id','reason','request_id'],'created_at'),
}
RESOURCES['users'][3].extend([('profile.email_verified_at','Email подтверждён'),('profile.phone_verified_at','Телефон подтверждён'),('active_contracts','Активные договоры'),('open_disputes','Незакрытые споры'),('last_seen','Последняя активность')])
RESOURCES['projects'][3].extend([('skills_summary','Навыки'),('deadline','Срок')])
GROUPS = {
 'projects':['projects','proposals'], 'contracts':['contracts','deliverables','amendments'],
 'finance':['wallets','ledger','payments','withdrawals','fees','receipts'],
 'messages':['conversations','proposal-conversations','reports','proposal-reports','support'],
 'catalogue':['categories','skills','verifications'], 'content':['content-revisions','announcements','notifications','deliveries'],
 'settings':['setting-revisions'], 'operations':['jobs','obligations'],
}
STATUS = {
 'pending':'Ожидает проверки','approved':'Одобрено','rejected':'Отклонено','hidden':'Скрыто',
 'published':'Опубликован','draft':'Черновик','active':'В работе','completed':'Завершён','cancelled':'Отменён',
 'in_progress':'В работе','review':'На проверке','submitted':'На проверке','contracting':'Согласование',
 'opened':'Открыт','evidence_collection':'Сбор доказательств','admin_review':'Рассмотрение','resolved':'Решено',
 'disputed':'Спор','awaiting_funding':'Ожидает резерва','customer_accepted':'Подпись заказчика','freelancer_accepted':'Подпись исполнителя',
 'paid':'Выполнен','prepared':'Подготовлен','processing':'Обрабатывается','reconciliation_required':'Требуется сверка',
 'accepted':'Принят','withdrawn':'Отозван','in_review':'Рассматривается','revoked':'Отозвано',
 'new':'Новое','open':'Открыто','waiting':'Нужны сведения','needs_info':'Нужны сведения','needs_information':'Нужны сведения','waiting_user':'Ожидает пользователя','closed':'Закрыто',
 'queued':'В очереди','running':'Выполняется','succeeded':'Завершено','failed':'Ошибка','success':'Успешно',
 'ru':'Русский','uz':'O‘zbekcha','uz-cyrl':'Ўзбекча','en':'English','client':'Заказчик','freelancer':'Фрилансер',
 'internal':'Внутренний','delivered':'Доставлено','sent':'Отправлено','previewed':'Предпросмотр','scheduled':'Запланировано','not_connected':'Не подключено',
}

def model_for(resource):
    name = RESOURCES[resource][0]
    return get_user_model() if name == 'User' else apps.get_model('marketplace', name)

def resource_url(resource, pk=None, **filters):
    base = f'/admin/control/{resource}/' + (f'{pk}/' if pk is not None else '')
    return base + ('?' + urlencode(filters) if filters else '')

def masked(value):
    if not value:
        return '—'
    value = str(value)
    if '@' in value:
        left, right = value.split('@',1)
        return left[:2] + '•••@' + right
    if len(value) > 5:
        return value[:4] + ' ••• •• ' + value[-2:]
    return '•••'

def redact_private_values(value, *, mask_contacts=True):
    """Legacy financial/audit dictionaries may contain embedded credentials."""
    if isinstance(value, dict):
        hidden = ('password', 'secret', 'token', 'cookie', 'authorization', 'code_hash', 'session_key')
        return {str(key): '[скрыто]' if any(part in str(key).lower() for part in hidden)
                or str(key).lower() in {'provider_recipient_id', 'payout_account', 'account', 'card', 'card_number', 'pan'}
                else masked(item) if mask_contacts and str(item) not in {'connected','not_connected','disabled'} and (str(key).lower() in {'email', 'phone'}
                    or str(key).lower().endswith(('_email', '_phone')))
                else redact_private_values(item, mask_contacts=mask_contacts) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_private_values(item, mask_contacts=mask_contacts) for item in value]
    return value


def read_value(obj, path, *, mask_contacts=True):
    if path == 'skills_summary':
        return ', '.join(skill.name for skill in obj.skills.all()) or ('На выбор исполнителя' if obj.skills_unspecified else '—')
    value = obj
    try:
        for part in path.split('.'):
            if value is None:
                return None
            if part in ('status','state','kind') and hasattr(value, f'get_{part}_display'):
                value = getattr(value, f'get_{part}_display')()
            else:
                value = getattr(value, part, None)
    except (AttributeError, get_user_model().profile.RelatedObjectDoesNotExist):
        return None
    if path in ('email','profile.phone','phone') and mask_contacts:
        return masked(value)
    if isinstance(value, bool):
        return 'Да' if value else 'Нет'
    if isinstance(value, Decimal):
        return f'{value:,.2f}'.replace(',', ' ')
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime('%d.%m.%Y, %H:%M')
    if isinstance(value, list):
        return ', '.join(STATUS.get(str(v),str(v)) for v in redact_private_values(value, mask_contacts=mask_contacts))
    if isinstance(value, dict):
        from .ui_forms import friendly_snapshot
        return friendly_snapshot(redact_private_values(value, mask_contacts=mask_contacts))
    return STATUS.get(value,value) if isinstance(value,str) else value

def base_queryset(resource):
    model = model_for(resource)
    qs = model.objects.all()
    relations = [f.name for f in model._meta.fields if f.many_to_one or f.one_to_one]
    if resource == 'users':
        relations = ['profile']
    if relations:
        qs = qs.select_related(*relations)
    if resource == 'users':
        Contract = apps.get_model('marketplace', 'Contract')
        Dispute = apps.get_model('marketplace', 'Dispute')
        BrowserSession = apps.get_model('marketplace', 'BrowserSession')
        def related_count(model, field, **where):
            rows = model.objects.filter(**{field:OuterRef('pk')}, **where).order_by().values(field).annotate(total=Count('pk')).values('total')
            return Coalesce(Subquery(rows, output_field=IntegerField()), Value(0))
        current = [value for value, _ in Contract.Status.choices if value not in ('completed','cancelled')]
        qs = qs.annotate(
            active_contracts=related_count(Contract,'customer_id',status__in=current)+related_count(Contract,'freelancer_id',status__in=current),
            open_disputes=related_count(Dispute,'contract__customer_id',status__in=['opened','evidence_collection','admin_review'])+related_count(Dispute,'contract__freelancer_id',status__in=['opened','evidence_collection','admin_review']),
            last_seen=Subquery(BrowserSession.objects.filter(user_id=OuterRef('pk')).order_by('-last_seen_at').values('last_seen_at')[:1]),
        )
    elif resource == 'projects':
        qs = qs.prefetch_related('skills')
    elif resource == 'conversations':
        qs = qs.annotate(message_count=Count('messages'),last_message=Max('messages__created_at'))
    elif resource == 'proposal-conversations':
        qs = qs.select_related('proposal__project','proposal__freelancer').annotate(message_count=Count('messages'),last_message=Max('messages__created_at'))
    elif resource == 'skills':
        qs = qs.annotate(profile_count=Count('profiles',distinct=True),project_count=Count('projects',distinct=True))
    elif resource == 'disputes':
        qs = qs.select_related('contract__customer','contract__freelancer','contract__project')
    return qs

def filtered_queryset(resource, params):
    qs = base_queryset(resource)
    model = model_for(resource)
    fields = {f.name:f for f in model._meta.fields}
    search = params.get('q','').strip()[:160]
    if search:
        condition = Q()
        for field in RESOURCES[resource][4]:
            condition |= Q(**{field+'__icontains':search})
        if search.isdigit():
            condition |= Q(pk=search)
        if 'reference' in fields:
            import uuid
            try:
                condition |= Q(reference=uuid.UUID(search))
            except ValueError:
                pass
        qs = qs.filter(condition) if condition else qs.none()
    for key in ('status','state','moderation_status','provider','kind','object_type','object_id','outcome','action','request_id','language'):
        if params.get(key) and key in fields:
            qs = qs.filter(**{key:params[key]})
    for key in ('active','published','featured','is_active'):
        if params.get(key) in ('true','false') and key in fields:
            qs = qs.filter(**{key:params[key]=='true'})
    for key in ('category','owner','project','contract','user','payment','withdrawal','actor'):
        value = params.get(key,'')
        if value.isdigit():
            if key in fields:
                qs = qs.filter(**{key+'_id':value})
            elif key == 'user':
                if resource == 'users': qs = qs.filter(pk=value)
                elif resource in ('contracts','conversations'): qs = qs.filter(Q(customer_id=value)|Q(freelancer_id=value))
                elif resource == 'projects': qs = qs.filter(owner_id=value)
                elif resource == 'proposals': qs = qs.filter(freelancer_id=value)
                elif resource == 'reviews': qs = qs.filter(Q(author_id=value)|Q(target_id=value))
                elif resource in ('reports','proposal-reports'): qs = qs.filter(reporter_id=value)
                elif resource == 'support': qs = qs.filter(author_id=value)
    if resource == 'users':
        if params.get('role') in ('client','freelancer'):
            # The JSON is a flat list of controlled role names; quoted token match works on both supported databases.
            from django.db.models import TextField
            from django.db.models.functions import Cast
            qs = qs.annotate(role_text=Cast('profile__enabled_roles',TextField())).filter(Q(profile__role=params['role'])|Q(role_text__contains='"'+params['role']+'"'))
        for channel in ('email','phone'):
            if params.get(channel+'_verified') in ('true','false'):
                qs = qs.filter(**{'profile__'+channel+'_verified_at__isnull':params[channel+'_verified']=='false'})
    for key,lookup in [('budget_min','budget_max__gte'),('budget_max','budget_min__lte')]:
        if resource == 'projects' and params.get(key):
            from rest_framework.exceptions import ValidationError
            try:
                value = Decimal(params[key])
                if not value.is_finite() or value < 0: raise ValueError
                qs = qs.filter(**{lookup:value})
            except (ValueError, ArithmeticError): raise ValidationError('Бюджет должен быть неотрицательным числом.')
    if resource == 'projects':
        if params.get('skill','').isdigit(): qs = qs.filter(skills__id=params['skill'])
        if params.get('deadline_before'):
            deadline, _ = date_bounds({'start':params['deadline_before']},default=False)
            qs = qs.filter(deadline__lt=deadline+timedelta(days=1))
    date_field = RESOURCES[resource][5]
    if resource == 'contracts' and params.get('date_basis') == 'completed_at': date_field = 'completed_at'
    if date_field:
        start,end = date_bounds(params,default=False)
        if start: qs = qs.filter(**{date_field+'__gte':start})
        if end: qs = qs.filter(**{date_field+'__lt':end})
    if params.get('queue') == 'open':
        if 'status' in fields: qs = qs.exclude(status__in=['completed','resolved','closed','paid','rejected','cancelled','revoked','succeeded'])
    if params.get('overdue') == 'true' and resource == 'deliverables':
        qs = qs.filter(review_due_at__lt=timezone.now(), contract__status='submitted')
    allowed = {key for key, _ in RESOURCES[resource][3] if key in fields and not fields[key].is_relation} | {'id'}
    if date_field: allowed.add(date_field)
    sort = params.get('sort','-'+(date_field or 'id'))
    if sort.lstrip('-') not in allowed: sort = '-pk'
    return qs.order_by(sort,'pk').distinct()

def date_bounds(params, default=True):
    from rest_framework.exceptions import ValidationError
    today = timezone.localdate()
    period = params.get('period','30' if default else '')
    try:
        start = parse_date(params.get('start',''))
        end = parse_date(params.get('end',''))
    except (ValueError, TypeError):
        raise ValidationError('Укажите существующие даты в формате ГГГГ-ММ-ДД.')
    if (params.get('start') and not start) or (params.get('end') and not end):
        raise ValidationError('Укажите даты в формате ГГГГ-ММ-ДД.')
    if start and end and start > end:
        raise ValidationError('Начало периода не может быть позже окончания.')
    if not start and period in ('1','7','30'):
        end = end or today
        try:
            start = end-timedelta(days=int(period)-1)
        except OverflowError:
            raise ValidationError('Начало периода выходит за допустимый диапазон.')
    zone = ZoneInfo('Asia/Tashkent')
    try:
        return (datetime.combine(start,time.min,zone) if start else None,
                datetime.combine(end+timedelta(days=1),time.min,zone) if end else None)
    except OverflowError:
        raise ValidationError('Конец периода выходит за допустимый диапазон.')

def list_context(resource, params):
    page_size = int(params.get('size','25')) if params.get('size','25') in ('25','50','100') else 25
    qs = filtered_queryset(resource,params)
    page = Paginator(qs,page_size).get_page(params.get('page','1'))
    cols = RESOURCES[resource][3]
    objects = list(page)
    if resource == 'projects':
        for obj in objects: obj.skills_summary = ', '.join(skill.name for skill in obj.skills.all()) or ('На выбор исполнителя' if obj.skills_unspecified else '—')
    rows = [{'id':obj.pk,'url':resource_url(resource,obj.pk) if resource!='announcements' else f'/admin/control/announcements/{obj.pk}/','cells':[{'value':read_value(obj,key),'status':key in ('status','state','moderation_status','is_active','active','published'),'raw':str(getattr(obj,key,''))} for key,_ in cols]} for obj in objects]
    if params:
        return_to = resource_url(resource, **dict(params.items()))
        for row in rows: row['url'] += '?' + urlencode({'return':return_to})
    choices = []
    try:
        field=model_for(resource)._meta.get_field('state' if resource in ('jobs','announcements') else 'status')
        choices=[(key,STATUS.get(key,label)) for key,label in field.choices or []]
    except Exception: pass
    query=params.copy()
    query.pop('page',None)
    visible_filters={'q','size','status','state','start','end','user','contract','role','is_active','email_verified','phone_verified','moderation_status','category','skill','deadline_before','budget_min','budget_max','action','object_type','object_id','request_id','outcome','sort'}
    return {'resource':resource,'columns':[label for _,label in cols],'rows':rows,'page_obj':page,
            'total':page.paginator.count,'size':page_size,'querystring':query.urlencode() if hasattr(query,'urlencode') else urlencode(query),
            'preserved_filters':[(key,value) for key,value in params.items() if key not in visible_filters and key!='page'],
            'status_choices':choices,'status_field':'state' if resource in ('jobs','announcements') else 'status','selected_status':params.get('state' if resource in ('jobs','announcements') else 'status',''),'filters':params,'title':RESOURCES[resource][1],
            'section':RESOURCES[resource][2],'exportable':resource in ('users','projects','contracts','payments','withdrawals','fees','audit')}

def dashboard(params):
    User=get_user_model()
    Project=apps.get_model('marketplace','Project'); Contract=apps.get_model('marketplace','Contract')
    Fee=apps.get_model('marketplace','PlatformFee'); Profile=apps.get_model('marketplace','Profile')
    Withdrawal=apps.get_model('marketplace','Withdrawal'); Dispute=apps.get_model('marketplace','Dispute')
    start,end=date_bounds(params)
    def period(qs,field='created_at'):
        if start: qs=qs.filter(**{field+'__gte':start})
        if end: qs=qs.filter(**{field+'__lt':end})
        return qs
    def total(qs,field):return qs.aggregate(value=Sum(field))['value'] or Decimal('0')
    period_filters={'start':start.date().isoformat() if start else '', 'end':(end.date()-timedelta(days=1)).isoformat() if end else ''}
    metrics=[
      {'label':'Пользователи','value':User.objects.count(),'note':f'+{period(User.objects.all(),"date_joined").count()} за период','icon':'users','url':resource_url('users')},
      {'label':'Новые заказы','value':period(Project.objects.all()).count(),'note':'За выбранный период','icon':'briefcase','url':resource_url('projects',**period_filters)},
      {'label':'Объём расчётов','value':total(period(Contract.objects.filter(completed_at__isnull=False),'completed_at'),'released_amount'),'note':'Валовая выплата до комиссии · UZS','icon':'wallet','url':resource_url('contracts',status='completed',date_basis='completed_at',**period_filters)},
      {'label':'Доход платформы','value':total(period(Fee.objects.all()),'fee_amount'),'note':'Фактически начислено · UZS','icon':'trend','url':resource_url('fees',**period_filters)},
    ]
    balances=[
      {'label':'Доступно в кошельках','value':total(Profile.objects.all(),'balance'),'url':resource_url('wallets'),'note':'Available'},
      {'label':'В резерве договоров','value':total(Contract.objects.all(),'escrow_amount'),'url':resource_url('contracts'),'note':'Frozen / escrow'},
      {'label':'Ожидают вывода','value':total(Withdrawal.objects.filter(status__in=['pending','processing','reconciliation_required']),'amount'),'url':resource_url('withdrawals',queue='open'),'note':'Pending Withdrawal'},
    ]
    queue=[]
    for res,model,statuses,label in [('disputes','Dispute',['opened','evidence_collection','admin_review'],'Открытые споры'),('withdrawals','Withdrawal',['pending','processing','reconciliation_required'],'Заявки на вывод'),('reports','ContentReport',['new','in_review','needs_information'],'Жалобы'),('verifications','SkillVerification',['submitted','in_review'],'Подтверждения навыков'),('proposal-reports','ProposalReport',['new','in_review','needs_information'],'Жалобы на отклики'),('support','SupportTicket',['open','in_review','waiting_user'],'Обращения в поддержку'),('obligations','AdminObligation',['open'],'Обязательства после блокировок')]:
        qs=apps.get_model('marketplace',model).objects.filter(status__in=statuses)
        queue.append({'label':label,'count':qs.count(),'url':resource_url(res,queue='open'),'oldest':qs.order_by('created_at').values_list('created_at',flat=True).first(),'icon':dict((n[0],n[2]) for n in NAV).get(res,'shield')})
    jobs=apps.get_model('marketplace','AdminJob').objects.filter(kind='reconcile',state='failed')
    queue.append({'label':'Ошибки сверки','count':jobs.count(),'url':resource_url('jobs',kind='reconcile',state='failed'),'oldest':jobs.order_by('created_at').values_list('created_at',flat=True).first(),'icon':'activity'})
    queue.sort(key=lambda v:(not bool(v['count']),v['oldest'] or timezone.now()))
    chart_data=list(period(Fee.objects.all()).annotate(day=TruncDate('created_at',tzinfo=ZoneInfo('Asia/Tashkent'))).values('day').annotate(amount=Sum('fee_amount')).order_by('day'))
    max_amount=max([float(v['amount']) for v in chart_data],default=0) or 1
    bars=[{'label':v['day'].strftime('%d.%m'),'date':v['day'].isoformat(),'amount':v['amount'],'height':max(3,round(float(v['amount'])/max_amount*100))} for v in chart_data]
    recent=list_context('contracts',{'size':'25'})['rows'][:5]
    status_groups=[]
    for resource, model, label in [('projects',Project,'Заказы сейчас'),('contracts',Contract,'Договоры сейчас')]:
        counts=dict(model.objects.values_list('status').annotate(total=Count('pk')).values_list('status','total'))
        status_groups.append({'label':label,'items':[{'label':STATUS.get(value,caption),'count':counts.get(value,0),'url':resource_url(resource,status=value)} for value,caption in model.Status.choices]})
    activity=[
        {'label':'Новые аккаунты за период','count':period(User.objects.all(),'date_joined').count(),'url':resource_url('users',**period_filters)},
        {'label':'Заблокированные аккаунты сейчас','count':User.objects.filter(is_active=False).count(),'url':resource_url('users',is_active='false')},
        {'label':'Новые договоры за период','count':period(Contract.objects.all()).count(),'url':resource_url('contracts',**period_filters)},
        {'label':'Завершённые договоры за период','count':period(Contract.objects.filter(status='completed'),'completed_at').count(),'url':resource_url('contracts',status='completed',date_basis='completed_at',**period_filters)},
    ]
    return {'metrics':metrics,'balances':balances,'queue':queue,'chart':bars,'recent':recent,
            'status_groups':status_groups,'activity':activity,
            'updated_at':timezone.now(),'period':params.get('period','30'),'start':params.get('start',''),'end':params.get('end',''),
            'blocked_users':User.objects.filter(is_active=False).count(),
            'completed_contracts':period(Contract.objects.filter(status='completed'),'completed_at').count()}
