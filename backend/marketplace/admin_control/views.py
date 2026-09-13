"""Server-rendered work queues. Every mutation is CSRF-protected POST."""
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django import forms
from django.apps import apps
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from rest_framework.exceptions import APIException

from .query import NAV, GROUPS, RESOURCES, STATUS, base_queryset, dashboard, list_context, model_for, read_value, resource_url
from ..security import require_platform_admin_session


def context(request, section='overview', **extra):
    return {**admin.site.each_context(request), 'admin_nav':[{'key':key,'label':label,'icon':icon,'url':url,'active':key==section} for key,label,icon,url in NAV],
            'section':section,'environment':{'local':'Локальная среда','test':'Тестовая среда','staging':'Тестовый стенд','production':'Production'}.get(settings.TASKORA_ENV,settings.TASKORA_ENV),
            'now':timezone.now(), **extra}

def render(request, template, section='overview', **extra):
    response=TemplateResponse(request, 'admin/control/'+template, context(request,section,**extra))
    response['Cache-Control']='no-store'
    return response

def overview(request, extra_context=None):
    require_platform_admin_session(request)
    data=dashboard(request.GET)
    jobs=apps.get_model('marketplace','AdminJob')
    latest=jobs.objects.filter(kind='diagnostics',state='succeeded').order_by('-finished_at').first()
    data.update(health=latest, health_stale=not latest or not latest.finished_at or latest.finished_at<timezone.now()-timedelta(minutes=30))
    return render(request,'overview.html',title='Обзор платформы',**data)


GROUP_DESCRIPTIONS = {
 'users':'Аккаунты, безопасность и обязательства пользователей.',
 'projects':'Публикации, модерация и отклики исполнителей.',
 'contracts':'Условия сделок, результаты и история согласований.',
 'disputes':'Доказательства, решения и распределение резерва.',
 'finance':'Деньги пользователей и подтверждённые финансовые операции.',
 'messages':'Переписка, жалобы и обращения в поддержку.',
 'reviews':'Отзывы участников завершённых сделок.',
 'catalogue':'Категории, навыки и ручная проверка подтверждений.',
 'content':'Опубликованные тексты, юридические документы и уведомления.',
 'settings':'Правила платформы с сохранением каждой версии.',
 'operations':'Диагностика, сверка и фоновые задачи.',
 'audit':'История действий и оснований. Время — Asia/Tashkent.',
}

def listing(request, resource):
    require_platform_admin_session(request)
    if resource == 'cases': return redirect('/admin/control/disputes/')
    group=resource
    if resource in GROUPS:
        resource=GROUPS[resource][0]
    if resource not in RESOURCES: raise Http404
    data=list_context(resource,request.GET)
    section=data.pop('section')
    data['tabs']=[{'label':RESOURCES[key][1],'url':resource_url(key),'active':key==resource} for key in GROUPS.get(section,[])]
    data['description']=GROUP_DESCRIPTIONS.get(section,'')
    data['heading']=next((n[1] for n in NAV if n[0]==section),data['title'])
    data['create_links']=[]
    if section=='finance':
        data['notice']='Внешние переводы выполняются вручную. «Выполнен» фиксируется только после проверки фактического перевода. Pending исполнителя — тот же резерв договора до комиссии; он не прибавляется к общему остатку.'
        data['create_links']=[('Запустить сверку','/admin/control/new/job/?kind=reconcile')]
    if section=='catalogue':
        data['create_links']=[('Добавить категорию','/admin/control/new/category/'),('Добавить навык','/admin/control/new/skill/'),('Добавить синоним','/admin/control/new/alias/'),('Связать навык с категорией','/admin/control/new/categoryskill/')]
    if section=='content':
        data['create_links']=[('Новая редакция','/admin/control/new/content/'),('Создать объявление','/admin/control/new/announcement/')]
        data['notice']='Тексты платформы доступны на RU, UZ, ЎЗ и EN. Публикация создаёт новую версию; ранее принятые документы сохраняются.'
    if section=='settings':
        from .content_services import SETTINGS_SCHEMA, get_setting
        data['settings_cards']=[{'key':key,'label':value['label'],'value':get_setting(key),'url':'/admin/control/new/setting/?'+urlencode({'key':key})} for key,value in SETTINGS_SCHEMA.items()]
        data['notice']='Комиссия по умолчанию: 5% с исполнителя, 0% с заказчика. Настройки не меняют подписанные договоры. Разрешение реальных денег задаётся только в окружении сервера.'
    if section=='operations':
        jobs=apps.get_model('marketplace','AdminJob')
        latest=jobs.objects.filter(kind='diagnostics',state='succeeded').order_by('-finished_at').first()
        data.update(diagnostics=latest,create_links=[('Обновить диагностику','/admin/control/new/job/?kind=diagnostics'),('Сверить финансы','/admin/control/new/job/?kind=reconcile'),('Безопасная обработка','/admin/control/new/job/?kind=retry')])
        data['notice']='Задачи выполняются отдельным worker. Резервные копии и проверка восстановления показываются только по подтверждённым данным.'
    return render(request,'list.html',section,**data)


DETAIL_FIELDS = {
 'users':[('profile.professional_title','Профессиональный заголовок'),('profile.location','Местоположение'),('profile.about','О себе'),('profile.professional_experience','Опыт'),('profile.spoken_languages','Языки общения'),('profile.available','Доступность'),('profile.role','Текущий режим'),('profile.public_hidden','Профиль скрыт')],
 'projects':[('description','Описание'),('acceptance_criteria','Критерии приёмки'),('demonstration_method','Демонстрация'),('test_scenario','Шаги проверки'),('budget_min','Минимальный бюджет, UZS'),('deadline','Срок'),('skills_unspecified','Технологии выбирает исполнитель'),('moderation_version','Версия модерации')],
 'proposals':[('cover_letter','Сопроводительное письмо')],
 'contracts':[('version','Версия'),('currency','Валюта'),('terms','Текст согласованных условий'),('scope','Объём работ'),('acceptance_criteria','Критерии приёмки'),('demonstration_method','Демонстрация'),('test_scenario','Шаги проверки'),('delivery_days','Дней на выполнение'),('review_days','Дней на приёмку'),('deadline','Срок'),('customer_signed_at','Подпись заказчика'),('freelancer_signed_at','Подпись исполнителя'),('funded_at','Резерв создан'),('fee_policy_snapshot','Снимок комиссии'),('fee_amount','Расчётная комиссия'),('actual_fee_amount','Начисленная комиссия'),('released_amount','Выплачено до комиссии'),('refunded_amount','Возвращено в кошелёк'),('completed_at','Завершён')],
 'deliverables':[('deadline_snapshot','Срок по договору')],
 'amendments':[('changes','Предлагаемые изменения')],
 'disputes':[('opened_by','Инициатор'),('reason','Заявление'),('resolution','Решение'),('freelancer_amount','Валовая выплата исполнителю'),('resolved_by','Решение принял'),('resolved_at','Дата решения')],
 'payments':[('click_trans_id','ID CLICK'),('payme_trans_id','ID PAYME')],
 'withdrawals':[('reference','UUID заявки'),('claim_snapshot','Снимок суммы и получателя'),('claimed_by','Принял оператор'),('claimed_at','Принято'),('resolution_reason','Основание'),('transfer_evidence','Подтверждение перевода'),('processed_at','Обработано')],
 'ledger':[('description','Основание')],
 'reviews':[('text','Оригинальный отзыв'),('moderation_reason','Причина модерации')],
 'reports':[('reason','Текст жалобы'),('decision','Решение'),('resolved_by','Рассмотрел'),('resolved_at','Закрыта')],
 'proposal-reports':[('reason','Текст жалобы'),('decision','Решение'),('resolved_by','Рассмотрел'),('resolved_at','Закрыта')],
 'support':[('contract','Договор'),('dispute','Связанный спор')],
 'verifications':[('evidence_type','Вид доказательства'),('description','Описание'),('reviewer','Проверил'),('decision','Решение'),('decided_at','Дата решения')],
 'skills':[('labels','Переводы')], 'categories':[('labels','Переводы')],
 'content-revisions':[('content_hash','Хеш документа'),('legal_version','Юридическая версия'),('author','Автор'),('reason','Основание'),('effective_at','Вступает в силу'),('payload','Содержание редакции')],
 'setting-revisions':[('author','Автор'),('reason','Основание'),('effective_at','Вступает в силу')],
 'jobs':[('state','Состояние'),('progress','Обработано'),('total','Всего'),('actor','Автор'),('reason','Основание'),('result','Результат'),('error','Ошибка'),('expires_at','Доступен до')],
 'audit':[('before','До изменения'),('after','После изменения'),('detail','Подробности'),('request_id','ID запроса'),('operation_id','UUID операции')],
 'obligations':[('description','Обязательство'),('resolved_at','Закрыто')],
}

def action_link(resource,pk,action,label,tone=''):
    return {'url':resource_url(resource,pk)+f'action/{action}/','label':label,'tone':tone}

def resource_object(resource,pk):
    try:
        identifier=model_for(resource)._meta.pk.to_python(pk)
    except (ValueError,TypeError,DjangoValidationError) as exc:
        raise Http404 from exc
    return get_object_or_404(base_queryset(resource),pk=identifier)

def detail(request,resource,pk):
    require_platform_admin_session(request)
    if resource not in RESOURCES: raise Http404
    obj=resource_object(resource,pk)
    section=RESOURCES[resource][2]
    list_url = resource_url(resource)
    return_to = request.GET.get('return','')
    if return_to.startswith(list_url+'?') and '\\' not in return_to:
        list_url = return_to
    fields=RESOURCES[resource][3]+DETAIL_FIELDS.get(resource,[])
    unique_fields=dict(fields)
    details=[{'label':label,'value':read_value(obj,key)} for key,label in unique_fields.items()]
    links=[]; actions=[]; blocks=[]
    model=obj._meta.model_name
    def link(res,label,**filters): links.append({'label':label,'url':resource_url(res,**filters)})
    def action(key,label,tone=''): actions.append(action_link(resource,pk,key,label,tone))
    if resource=='users':
        from .workflows import obligations_for, verified_skill_names
        data=obligations_for(obj.pk)
        blocks.append({'title':'Действующие обязательства','values':{'Незавершённые договоры':data['contracts'],'Резерв договоров, UZS':data['escrow'],'Незавершённые выводы':data['withdrawals']}})
        if hasattr(obj,'profile'):
            profile=obj.profile
            def safe_profile_image(value):
                return value if isinstance(value,str) and len(value)<=2_800_000 and value.startswith(('data:image/jpeg;base64,','data:image/png;base64,','data:image/webp;base64,')) else ''
            if safe_profile_image(profile.avatar): blocks.append({'title':'Аватар профиля','image':profile.avatar})
            works=[]
            for item in (profile.portfolio if isinstance(profile.portfolio,list) else [])[:9]:
                if not isinstance(item,dict): continue
                url=str(item.get('url',''))
                works.append({'heading':str(item.get('title','Без названия')),'text':'\n'.join(str(item.get(key,'')) for key in ('category','description') if item.get(key)),
                              'image':safe_profile_image(item.get('image','')),'external_url':url if url.lower().startswith(('https://','http://')) else ''})
            blocks.append({'title':'Портфолио','rows':works})
            services=[]
            for item in (profile.services if isinstance(profile.services,list) else [])[:6]:
                if not isinstance(item,dict): continue
                services.append({'heading':str(item.get('title','Без названия')),
                                 'text':f'{item.get("description", "")}\nЦена: {item.get("price", "Не указана")} UZS\nСрок выполнения: {item.get("delivery_days", "Не указан")} дн.'})
            blocks.append({'title':'Услуги','rows':services})
            blocks.append({'title':'Навыки пользователя','text':', '.join(profile.skills.values_list('name',flat=True)) or 'Навыки не указаны'})
            verified=verified_skill_names(obj.pk)
            blocks.append({'title':'Подтверждённые навыки','text':', '.join(verified) or 'Действующих подтверждений нет. Добавление навыка в профиль не подтверждает его.'})
            mfa=apps.get_model('marketplace','MultiFactorCredential').objects.filter(user=obj,enabled_at__isnull=False).exists()
            blocks.append({'title':'Состояние защиты','values':{'Многофакторная защита':'Подключена' if mfa else 'Не подключена','Паспортный признак в исходном профиле':'Указан' if profile.has_passport else 'Не указан'}})
        for res,label in [('projects','Заказы'),('proposals','Отклики'),('contracts','Договоры'),('reviews','Отзывы'),('wallets','Кошелёк'),('withdrawals','Выплаты'),('reports','Жалобы'),('support','Поддержка'),('verifications','Подтверждения навыков')]:link(res,label,user=pk)
        action('user.edit','Исправить профиль')
        action('user.block' if obj.is_active else 'user.unblock','Заблокировать' if obj.is_active else 'Разблокировать','danger' if obj.is_active else '')
        action('user.revoke_sessions','Отозвать сессии и токены')
        action('user.revoke_session','Отозвать отдельную сессию')
        action('user.revoke_token','Отозвать отдельный API-токен')
        action('user.recovery','Инициировать восстановление доступа')
        if obj.is_active and hasattr(obj,'profile') and obj.profile.public_hidden: action('user.restore','Восстановить публичный профиль')
        sessions=apps.get_model('marketplace','BrowserSession').objects.filter(user=obj,revoked_at__isnull=True,expires_at__gt=timezone.now()).order_by('-last_seen_at')[:100]
        blocks.append({'title':'Активные сессии','rows':[{'heading':s.user_agent or 'Браузер','text':f'Последняя активность: {timezone.localtime(s.last_seen_at):%d.%m.%Y %H:%M}; истекает {timezone.localtime(s.expires_at):%d.%m.%Y %H:%M}'} for s in sessions]})
        consents=apps.get_model('marketplace','LegalConsent').objects.filter(user=obj).order_by('-pk')[:100]
        blocks.append({'title':'Согласия с документами','rows':[{'heading':f'Согласие №{c.pk} · версия {c.version}',
            'text':f'Язык: {STATUS.get(c.language,c.language)}\nПринято: {timezone.localtime(c.accepted_at):%d.%m.%Y %H:%M}\nХеш принятого документа: {c.content_hash}',
            'snapshot':read_value(c,'content_snapshot')} for c in consents]})
    if resource=='projects':
        link('proposals','Отклики',project=pk); link('contracts','Договор',project=pk)
        if obj.owner_id: links.append({'label':'Профиль заказчика','url':resource_url('users',obj.owner_id)})
        action('project.moderate','Решение модерации'); action('project.edit','Исправить публикацию')
        blocks.append({'title':'Навыки','text':', '.join(obj.skills.values_list('name',flat=True)) or 'Исполнитель выбирает технологии' if obj.skills_unspecified else ', '.join(obj.skills.values_list('name',flat=True)) or 'Не указаны'})
        blocks.append({'title':'Вложения','files':[{'label':f.filename,'url':f'/admin/control/files/projectattachment/{f.pk}/'} for f in obj.attachments.all()[:100]]})
    if resource in ('contracts','conversations'):
        links.extend([{'label':'Исходный заказ','url':resource_url('projects',obj.project_id)},
                      {'label':'Принятый отклик','url':resource_url('proposals',obj.proposal_id)},
                      {'label':'Профиль заказчика','url':resource_url('users',obj.customer_id)},
                      {'label':'Профиль исполнителя','url':resource_url('users',obj.freelancer_id)}])
        for res,label in [('deliverables','Результаты'),('amendments','Версии условий'),('ledger','Движения средств'),('payments','Платежи'),('disputes','Спор'),('reviews','Отзывы')]:link(res,label,contract=pk)
        link('fees','Начисленная комиссия',contract=pk)
        links.append({'label':'Переписка','url':resource_url('conversations',pk)})
        if resource=='contracts':
            if obj.status in ('draft','customer_accepted','freelancer_accepted','awaiting_funding','active'): action('contract.amend','Предложить исправление условий')
            if obj.status in ('draft','customer_accepted','freelancer_accepted','awaiting_funding') and not obj.funded_at: action('contract.cancel','Отменить до финансирования','danger')
            links.append({'label':'Исправление комиссии до финансирования','url':f'/admin/marketplace/contract/{pk}/revise-fee/'})
        blocks.append({'title':'История сделки','rows':[{'heading':f'{e.created_at:%d.%m.%Y} · {e.kind}','text':e.description} for e in obj.events.order_by('-created_at')[:100]]})
    if resource=='proposals':
        links.append({'label':'Исходный заказ','url':resource_url('projects',obj.project_id)})
        if obj.freelancer_id: links.append({'label':'Профиль исполнителя','url':resource_url('users',obj.freelancer_id)})
        linked_contract=getattr(obj,'contract',None)
        if linked_contract: links.append({'label':'Связанный договор','url':resource_url('contracts',linked_contract.pk)})
        conversation=getattr(obj,'conversation',None)
        if conversation: links.append({'label':'Обсуждение отклика','url':resource_url('proposal-conversations',conversation.pk)})
    if resource=='wallets':
        from django.db.models import Sum
        Contract=apps.get_model('marketplace','Contract');Withdrawal=apps.get_model('marketplace','Withdrawal')
        balance_data={label:str(qs.aggregate(v=Sum(field))['v'] or 0) for label,qs,field in [('Frozen / резерв заказчика',Contract.objects.filter(customer_id=obj.user_id),'escrow_amount'),('Pending / ожидается до комиссии',Contract.objects.filter(freelancer_id=obj.user_id),'escrow_amount'),('Pending Withdrawal',Withdrawal.objects.filter(user_id=obj.user_id,status__in=['pending','processing','reconciliation_required']),'amount')]}
        blocks.append({'title':'Средства по назначению, UZS','values':balance_data})
        link('ledger','История движений',user=obj.user_id);link('withdrawals','Выводы',user=obj.user_id)
        links.append({'label':'Корректировка с основанием','url':f'/admin/marketplace/profile/{pk}/adjust-balance/'})
    if resource=='withdrawals': links.append({'label':'Проверить и обработать заявку','url':f'/admin/marketplace/withdrawal/{pk}/operate/'})
    if resource=='payments':
        link('ledger','Связанная проводка',payment=pk)
        receipt=getattr(obj,'click_receipt',None)
        if receipt: links.append({'label':'Чек CLICK','url':resource_url('receipts',receipt.pk)})
    if resource=='deliverables':
        links.append({'label':'Защищённый файл','url':f'/admin/control/files/deliverable/{pk}/'})
    if resource in ('deliverables','amendments','reviews','fees'):
        links.append({'label':'Связанный договор','url':resource_url('contracts',obj.contract_id)})
    if resource=='disputes':
        links.append({'label':'Договор и материалы','url':resource_url('contracts',obj.contract_id)})
        links.append({'label':'Переписка по договору','url':resource_url('conversations',obj.contract_id)})
        if obj.status!='resolved':
            action('dispute.transition','Изменить стадию');action('dispute.note','Заметка / запрос доказательств')
            if obj.status=='admin_review':action('dispute.preview','Рассчитать решение')
        blocks.append({'title':'Служебные заметки и запросы','rows':[{'heading':('Запрос участнику' if n.recipient_id else 'Внутренняя заметка')+f' · {n.actor}','text':n.text} for n in obj.admin_notes.select_related('actor').order_by('-created_at')[:100]]})
    if resource in ('reports','proposal-reports'):
        if obj.status not in ('resolved','rejected'):action('report.review' if resource=='reports' else 'proposal_report.review','Рассмотреть жалобу')
    if resource=='support':
        action('support.reply','Ответить от администрации')
        if obj.contract_id and not obj.dispute_id:action('support.convert','Открыть спор по обращению')
    if resource=='reviews':action('review.moderate','Скрыть / восстановить отзыв')
    if resource=='verifications':
        action('verification.decide','Решение по навыку')
        if obj.evidence_file:links.append({'label':'Документ подтверждения','url':f'/admin/control/files/skillverification/{pk}/'})
    if resource in ('skills','categories'):
        action('catalogue.save','Изменить с основанием')
        if resource=='skills':
            action('skill.merge','Объединить с каноническим навыком')
            blocks.append({'title':'Синонимы','text':', '.join(obj.aliases.values_list('key',flat=True)) or 'Нет синонимов'})
            blocks.append({'title':'Категории','text':', '.join(obj.categories.values_list('name',flat=True)) or 'Не назначены'})
    if resource=='content-revisions':
        links.append({'label':'Создать редакцию на основе этой','url':f'/admin/control/new/content/?source={pk}'})
        if not obj.published_at:links.append({'label':'Предпросмотр и публикация','url':f'/admin/control/publish/{pk}/'})
    if resource=='jobs':
        if obj.storage_name and obj.state=='succeeded':
            links.append({'label':'Скачать защищённый CSV' if obj.kind=='export' else 'Скачать полный отчёт JSON','url':f'/admin/control/exports/{pk}/'})
        if obj.state=='failed' and obj.actor_id==request.user.pk:
            links.append({'label':'Повторить безопасную задачу','url':f'/admin/control/new/retry/?job={pk}'})
    private=resource in ('conversations','proposal-conversations','support','deliverables','verifications','proposals')
    private_grant=request.session.get('admin_disclosure',{}).get(f'{resource}:{pk}',{})
    disclosed=bool(private_grant and private_grant.get('expires',0)>timezone.now().timestamp())
    if private and disclosed:
        require_platform_admin_session(request,sensitive=True)
        if resource in ('conversations','proposal-conversations','support'):
            qs=obj.messages.select_related('author' if resource=='support' else 'sender').order_by('-created_at')[:100]
            rows=[]
            for m in qs:
                author=getattr(m,'author',None) or getattr(m,'sender',None)
                rows.append({'heading':('Администрация Taskora' if getattr(m,'administration',False) else str(author or 'Система'))+f' · {timezone.localtime(m.created_at):%d.%m.%Y %H:%M}', 'text':m.text,
                             'file_url':f'/admin/control/files/{m._meta.model_name}/{m.pk}/' if getattr(m,'file',None) else '', 'filename':getattr(m,'filename','')})
            blocks.append({'title':'Материалы для модерации','rows':rows})
        if resource=='deliverables':
            blocks.append({'title':'Описание результата','text':obj.preview_text+'\n'+obj.verification_steps+'\n'+obj.revision_note})
            if obj.demo_url: blocks.append({'title':'Демонстрация результата','text':obj.demo_url})
        if resource=='verifications' and obj.evidence_url: blocks.append({'title':'Источник доказательства','text':obj.evidence_url})
    if resource=='proposals' and not disclosed:
        details=[f for f in details if f['label']!='Сопроводительное письмо']
    if resource=='verifications' and not disclosed:
        details=[f for f in details if f['label']!='Описание']
    if resource=='obligations' and obj.status=='open':
        action('obligation.resolve','Подтвердить завершение обязательства')
        target_resource='contracts' if obj.object_type=='contract' else 'withdrawals'
        links.append({'label':'Проверить связанный объект','url':resource_url(target_resource,obj.object_id)})
    if resource in ('conversations','proposal-conversations') and disclosed:
        action('message.moderate','Скрыть / восстановить сообщение')
    link('audit','История действий',object_type=model,object_id=pk)
    return render(request,'detail.html',section,title=f'{RESOURCES[resource][1]} · #{pk}',resource=resource,obj=obj,details=details,links=links,actions=actions,blocks=blocks,private=private,disclosed=disclosed,list_url=list_url,disclose_url=resource_url(resource,pk)+'action/private.reveal/')


class ReasonForm(forms.Form):
    reason=forms.CharField(label='Основание действия',min_length=10,max_length=1000,widget=forms.Textarea(attrs={'rows':3,'placeholder':'Укажите причину и ссылку на обращение при наличии'}))
    idempotency_key=forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    confirmed=forms.BooleanField(label='Я проверил данные и подтверждаю действие')


def command_form(action,obj,data=None):
    form=ReasonForm(data)
    from .workflows import state_fingerprint
    form.fields['expected_state']=forms.CharField(widget=forms.HiddenInput,initial=state_fingerprint(obj))
    def field(name,item):form.fields[name]=item
    choice=lambda label,values:forms.ChoiceField(label=label,choices=[(v,STATUS.get(v,v)) for v in values])
    if action=='user.recovery':field('channel',forms.ChoiceField(label='Канал штатного восстановления',choices=[('email','Email пользователя'),('phone','Телефон пользователя')]))
    if action=='user.revoke_session':
        rows=apps.get_model('marketplace','BrowserSession').objects.filter(user=obj,revoked_at__isnull=True,expires_at__gt=timezone.now()).order_by('-last_seen_at')[:100]
        field('credential_id',forms.ChoiceField(label='Активная сессия',choices=[(str(row.pk),f'{row.user_agent or "Браузер"} · {timezone.localtime(row.last_seen_at):%d.%m.%Y %H:%M}') for row in rows]))
    if action=='user.revoke_token':
        from rest_framework.authtoken.models import Token
        rows=apps.get_model('marketplace','ScopedApiToken').objects.filter(user=obj,revoked_at__isnull=True,expires_at__gt=timezone.now()).order_by('-created_at')[:100]
        choices=[(str(row.pk),f'{row.name} · до {timezone.localtime(row.expires_at):%d.%m.%Y}') for row in rows]
        if Token.objects.filter(user=obj).exists(): choices.append(('legacy','Устаревший токен API'))
        field('credential_id',forms.ChoiceField(label='Активный API-токен',choices=choices))
    if action=='project.moderate':
        field('status',choice('Решение',['approved','hidden','rejected','pending']))
        field('expected_version',forms.IntegerField(widget=forms.HiddenInput,initial=obj.moderation_version))
    if action in ('user.edit','project.edit','contract.amend','catalogue.save'):
        if action=='user.edit':
            initial={'full_name':getattr(obj.profile,'full_name',''),'about':getattr(obj.profile,'about','')}
            hint='Разрешено: full_name, about, avatar, portfolio, available, email, phone. Новый контакт потребуется подтвердить.'
        elif action=='project.edit':
            initial={'title':obj.title,'description':obj.description,'featured':obj.featured}
            hint='Разрешено: title, description, featured, category_id. Подписанные условия не меняются.'
        elif action=='contract.amend':
            initial={'scope':obj.scope,'acceptance_criteria':obj.acceptance_criteria}
            hint='Предложение вступит в силу только после подтверждения обеими сторонами.'
        else:
            initial={k:getattr(obj,k) for k in ('name','slug','labels','active')}
            hint='Названия, переводы и активность. Использованные элементы сохраняются.'
        field('changes',forms.JSONField(label='Предлагаемые изменения',initial=initial,widget=forms.Textarea(attrs={'rows':10}),help_text=hint))
    if action=='review.moderate':field('published',forms.TypedChoiceField(label='Публикация',choices=[('true','Восстановить'),('false','Скрыть')],coerce=lambda s:s=='true'))
    if action=='dispute.transition':field('status',choice('Стадия',['evidence_collection','admin_review']))
    if action=='dispute.note':
        field('text',forms.CharField(label='Заметка или запрос',max_length=5000,widget=forms.Textarea(attrs={'rows':5})))
        field('recipient',forms.TypedChoiceField(label='Получатель',choices=[('','Внутренняя заметка'),(str(obj.contract.customer_id),'Заказчик'),(str(obj.contract.freelancer_id),'Исполнитель')],coerce=lambda s:int(s) if s else None,required=False))
    if action=='dispute.preview':field('gross',forms.DecimalField(label='Валовая сумма исполнителю, UZS',max_digits=12,decimal_places=2,min_value=0,max_value=obj.contract.escrow_amount,help_text='0 — полный возврат заказчику. Весь резерв — полная выплата. Комиссию рассчитает сервер.'))
    if action in ('report.review','proposal_report.review'):field('status',choice('Состояние',['in_review','needs_information','resolved','rejected']))
    if action=='support.reply':
        field('text',forms.CharField(label='Ответ администрации',max_length=5000,widget=forms.Textarea(attrs={'rows':6})))
        field('status',choice('Состояние',['in_review','waiting_user','resolved']))
    if action=='verification.decide':
        field('status',choice('Решение',['in_review','approved','rejected','revoked']))
        field('expires_at',forms.DateTimeField(label='Действует до (необязательно)',required=False,widget=forms.DateTimeInput(attrs={'type':'datetime-local'})))
    if action=='skill.merge':field('target_id',forms.ModelChoiceField(label='Канонический навык',queryset=apps.get_model('marketplace','Skill').objects.filter(active=True,merged_into__isnull=True).exclude(pk=obj.pk)))
    if action=='message.moderate':
        rows=obj.messages.all().order_by('-created_at')
        if obj._meta.model_name=='contract': rows=rows.filter(system=False)
        field('message_id',forms.ChoiceField(label='Сообщение',choices=[(str(row.pk),f'№{row.pk} · {timezone.localtime(row.created_at):%d.%m.%Y %H:%M}') for row in rows[:100]]))
        field('hidden',forms.TypedChoiceField(label='Показ участникам',choices=[('true','Скрыть'),('false','Восстановить')],coerce=lambda s:s=='true'))
    from .ui_forms import EDIT_ACTIONS, add_edit_fields
    if action in EDIT_ACTIONS:
        form.fields.pop('changes',None)
        add_edit_fields(form,action,obj)
    return form


ACTION_TITLES={'user.edit':'Исправление профиля','user.block':'Блокировка пользователя','user.unblock':'Разблокировка пользователя','user.restore':'Восстановление профиля','user.revoke_sessions':'Отзыв сессий и токенов','project.moderate':'Модерация заказа','project.edit':'Исправление публикации','review.moderate':'Модерация отзыва','dispute.transition':'Стадия рассмотрения','dispute.note':'Заметка и запрос доказательств','dispute.preview':'Предпросмотр решения спора','report.review':'Рассмотрение жалобы','proposal_report.review':'Рассмотрение жалобы','support.reply':'Ответ администрации','support.convert':'Открытие спора','verification.decide':'Подтверждение навыка','skill.merge':'Объединение навыков','contract.amend':'Предложение исправления условий','catalogue.save':'Изменение справочника','private.reveal':'Просмотр для модерации'}
ACTION_RESOURCES={'users':{'user.edit','user.block','user.unblock','user.restore','user.revoke_sessions'},'projects':{'project.edit','project.moderate'},'contracts':{'contract.amend'},'reviews':{'review.moderate'},'disputes':{'dispute.transition','dispute.note','dispute.preview'},'reports':{'report.review'},'proposal-reports':{'proposal_report.review'},'support':{'support.reply','support.convert','private.reveal'},'verifications':{'verification.decide','private.reveal'},'skills':{'skill.merge','catalogue.save'},'categories':{'catalogue.save'},'conversations':{'private.reveal'},'proposal-conversations':{'private.reveal'},'deliverables':{'private.reveal'},'proposals':{'private.reveal'}}
ACTION_RESOURCES['users'].update({'user.revoke_session','user.revoke_token'})
ACTION_RESOURCES['users'].add('user.recovery')
ACTION_TITLES['user.recovery']='Восстановление доступа по подтверждённому обращению'
ACTION_RESOURCES['contracts'].add('contract.cancel')
ACTION_RESOURCES['obligations']={'obligation.resolve'}
ACTION_TITLES['obligation.resolve']='Подтверждение завершённого обязательства'
ACTION_RESOURCES['conversations'].add('message.moderate')
ACTION_RESOURCES['proposal-conversations'].add('message.moderate')
ACTION_TITLES['message.moderate']='Модерация сообщения с сохранением оригинала'
ACTION_TITLES.update({'user.revoke_session':'Отзыв отдельной сессии','user.revoke_token':'Отзыв отдельного токена','contract.cancel':'Обоснованная отмена до финансирования'})


@require_http_methods(['GET','POST'])
def command(request,resource,pk,action):
    require_platform_admin_session(request)
    if action not in ACTION_RESOURCES.get(resource,set()):raise Http404
    obj=resource_object(resource,pk)
    from .ui_forms import EDIT_ACTIONS, edit_changes, edit_preview_rows, sign_edit_preview, load_edit_preview
    from django.core import signing
    if request.method=='POST' and action in EDIT_ACTIONS and request.POST.get('edit_preview'):
        try:
            data=load_edit_preview(request.POST['edit_preview'],action,obj,request.user.pk)
            if request.POST.get('execute')!='yes' or request.POST.get('confirmed')!='on':raise DjangoValidationError('Подтвердите проверенный предпросмотр.')
            from .workflows import execute_command
            execute_command(request,action,obj.pk,data)
            messages.success(request,'Изменения применены. Предыдущее состояние и основание сохранены.')
            return redirect(resource_url(resource,pk))
        except (signing.BadSignature,APIException,DjangoValidationError,ValueError) as exc:
            return render(request,'edit_preview.html',RESOURCES[resource][2],title=ACTION_TITLES[action],error=str(getattr(exc,'detail',exc)),back_url=resource_url(resource,pk),restart_url=resource_url(resource,pk)+f'action/{action}/')
    form=command_form(action,obj,request.POST if request.method=='POST' else None)
    preview=None
    if request.method=='POST' and form.is_valid():
        try:
            data=dict(form.cleaned_data)
            data['idempotency_key']=str(data['idempotency_key'])
            if data.get('expires_at'):data['expires_at']=data['expires_at'].isoformat()
            if action=='catalogue.save':data['kind']='category' if resource=='categories' else 'skill'
            if action=='skill.merge':data['target_id']=data['target_id'].pk
            if action=='message.moderate':data['proposal']=resource=='proposal-conversations'
            if action in EDIT_ACTIONS:
                changes=edit_changes(form,action,obj)
                if not changes:raise DjangoValidationError('Укажите хотя бы одно изменение.')
                data={key:value for key,value in data.items() if key in ('reason','idempotency_key','confirmed','expected_state','kind')}
                data['changes']=changes
                token=sign_edit_preview(action,obj,data,request.user.pk)
                return render(request,'edit_preview.html',RESOURCES[resource][2],title=ACTION_TITLES[action],rows=edit_preview_rows(form,changes,obj),edit_preview=token,reason=data['reason'],back_url=resource_url(resource,pk),restart_url=resource_url(resource,pk)+f'action/{action}/')
            if action=='private.reveal':
                require_platform_admin_session(request,sensitive=True)
                from .workflows import audit
                audit(request.user,'private_material_read',obj,data['reason'],request=request)
                grants=request.session.get('admin_disclosure',{})
                grants[f'{resource}:{pk}']={'expires':timezone.now().timestamp()+300,'reason':data['reason']}
                request.session['admin_disclosure']=grants
                return redirect(resource_url(resource,pk))
            from .workflows import execute_command
            preview=execute_command(request,action,obj.pk,data)
            if action=='dispute.preview':
                return render(request,'preview.html','disputes',title='Подтверждение решения спора',preview=preview,operation_key=data['idempotency_key'],object=obj,reason=data['reason'],back_url=resource_url(resource,pk))
            messages.success(request,'Действие выполнено. Основание и изменения сохранены в журнале.')
            return redirect(resource_url(resource,pk))
        except (APIException,DjangoValidationError,ValueError) as exc:
            form.add_error(None,str(getattr(exc,'detail',exc)))
    extra={}
    if action=='user.block':
        from .workflows import obligations_for
        obligations=obligations_for(obj.pk)
        extra['facts']={'Незавершённые договоры':obligations['contracts'],'Резерв договоров, UZS':obligations['escrow'],'Незавершённые выводы':obligations['withdrawals']}
        extra['notice']='Блокировка отзывает доступ. Договоры, деньги и история сохраняются; незакрытые обязательства попадут в очередь.'
    if action=='skill.merge':extra['facts']={'Профилей':obj.profiles.count(),'Заказов':obj.projects.count(),'Подтверждений для повторной проверки':obj.verifications.filter(status='approved').count()}
    if action=='dispute.preview':extra['facts']={'Договор':obj.contract_id,'Заказчик':str(obj.contract.customer),'Исполнитель':str(obj.contract.freelancer),'Полный резерв, UZS':str(obj.contract.escrow_amount),'Комиссия, %':str(obj.contract.fee_percent)}
    return render(request,'form.html',RESOURCES[resource][2],title=ACTION_TITLES[action],form=form,back_url=resource_url(resource,pk),submit_label='Рассчитать решение' if action=='dispute.preview' else 'Сравнить изменения' if action in EDIT_ACTIONS else 'Подтвердить действие',**extra)


@require_http_methods(['POST'])
def resolve_preview(request,pk):
    require_platform_admin_session(request)
    from .workflows import execute_dispute
    preview=get_object_or_404(apps.get_model('marketplace','DisputePreview'),pk=pk,actor=request.user)
    try:
        require_platform_admin_session(request,sensitive=True)
        result=execute_dispute(pk,request.POST.get('idempotency_key'),request.user,request=request,confirmed=request.POST.get('confirmed')=='on')
    except (APIException,DjangoValidationError,ValueError) as exc:
        return render(request,'preview.html','disputes',title='Решение не выполнено',preview={'id':str(preview.pk),'snapshot':preview.snapshot,'expires_at':preview.expires_at},reason=preview.reason,operation_key=request.POST.get('idempotency_key'),error=str(getattr(exc,'detail',exc)),back_url=resource_url('disputes',preview.dispute_id))
    messages.success(request,'Решение исполнено. Расчёт и уведомления участникам сохранены.')
    return redirect(resource_url('disputes',preview.dispute_id))


@require_http_methods(['GET','POST'])
def private_file(request,kind,pk):
    require_platform_admin_session(request)
    allowed={'deliverable','message','projectattachment','proposalmessage','skillverification'}
    if kind not in allowed:raise Http404
    obj=get_object_or_404(apps.get_model('marketplace',kind),pk=pk)
    form=ReasonForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        try:
            require_platform_admin_session(request,sensitive=True)
            from ..views import admin_private_file_response
            # The shared stream verifies the session, model permission and audit.
            return admin_private_file_response(request,kind,pk,reason=form.cleaned_data['reason'])
        except (APIException,DjangoValidationError) as exc:form.add_error(None,str(getattr(exc,'detail',exc)))
    return render(request,'form.html','messages',title='Доступ к приватному файлу',form=form,notice=getattr(obj,'filename','Защищённый материал'),back_url='/admin/',submit_label='Проверить доступ и скачать')


def global_search(request):
    require_platform_admin_session(request)
    q=request.GET.get('q','').strip()[:160]
    groups=[]
    if q:
        for resource in ('users','projects','contracts','payments','withdrawals'):
            from .query import filtered_queryset
            objects=filtered_queryset(resource,{'q':q})[:5]
            groups.append({'title':RESOURCES[resource][1],'url':resource_url(resource,q=q),'rows':[{'title':str(getattr(o,'title',None) or getattr(o,'username',None) or getattr(o,'reference',None) or f'#{o.pk}'),'url':resource_url(resource,o.pk)} for o in objects]})
    return render(request,'search.html',title='Поиск по платформе',q=q,groups=groups)


@require_http_methods(['GET','POST'])
def create(request,kind):
    require_platform_admin_session(request)
    from .content_forms import ContentDraftForm,PlatformSettingForm,AnnouncementForm,JobForm,ExportForm
    from . import content_services as svc
    from . import jobs
    bound=request.POST if request.method=='POST' else None
    initial={};title='';section='content';notice='';result=None
    if kind=='content':
        source=apps.get_model('marketplace','ContentRevision').objects.filter(pk=request.GET.get('source')).first() if request.GET.get('source','').isdigit() else None
        source=source or svc.latest_published(apps.get_model('marketplace','ContentRevision'),language=request.GET.get('language','ru'))
        latest=apps.get_model('marketplace','ContentRevision').objects.filter(language=source.language if source else 'ru',published_at__isnull=False).order_by('-version').first()
        initial={'language':source.language if source else 'ru','payload':source.payload if source else {},'approved':source.approved if source else False,'expected_version':latest.version if latest else 0}
        form=ContentDraftForm(bound,initial=initial);title='Новая редакция контента'
    elif kind=='setting':
        section='settings';key=request.GET.get('key',next(iter(svc.SETTINGS_SCHEMA)))
        if key not in svc.SETTINGS_SCHEMA:raise Http404
        latest=apps.get_model('marketplace','PlatformSettingRevision').objects.filter(key=key,published_at__isnull=False).order_by('-version').first()
        initial={'key':key,'value':svc.get_setting(key),'expected_version':latest.version if latest else 0}
        form=PlatformSettingForm(bound,initial=initial);title='Изменение правила платформы'
    elif kind=='announcement':form=AnnouncementForm(bound);title='Новое объявление'
    elif kind=='job':
        form=JobForm(bound,initial={'kind':request.GET.get('kind','diagnostics')});title='Запуск фоновой задачи';section='operations'
    elif kind=='retry':
        obj=get_object_or_404(apps.get_model('marketplace','AdminJob'),pk=request.GET.get('job'),actor=request.user,state='failed')
        form=ReasonForm(bound,initial={'reason':obj.reason});title='Повтор безопасной задачи';section='operations'
        notice=f'{obj.get_kind_display()}: {obj.error}. Повтор внутренних уведомлений использует прежние ключи событий и адресатов.'
    elif kind=='export':
        filters={key:value for key,value in request.GET.items() if key not in ('dataset','size','page')}
        form=ExportForm(bound,initial={'dataset':request.GET.get('dataset','users'),'filters':filters});title='Экспорт данных';section='operations'
        notice='CSV формируется в фоне по выбранным фильтрам. Скачивание доступно только создателю в течение 24 часов; контакты маскируются.'
    elif kind in ('category','skill','alias','categoryskill'):
        from .catalogue_forms import CatalogueCreateForm
        section='catalogue';form=CatalogueCreateForm(kind,bound);title={'category':'Новая категория','skill':'Новый навык','alias':'Новый синоним','categoryskill':'Связь категории и навыка'}[kind]
        notice='Названия и переводы можно исправить позже с основанием. Постоянный код сохраняется. Связи не присваивают пользователям подтверждения навыков.'
    else:raise Http404
    if request.method=='POST' and form.is_valid():
        data=dict(form.cleaned_data)
        try:
            if kind=='content':
                obj=svc.create_content_draft(actor=request.user,request=request,**data)
                return redirect(resource_url('content-revisions',obj.pk))
            if kind=='setting':
                preview=svc.preview_setting(data['key'],data['value'])
                if request.POST.get('publish')=='yes':
                    obj=svc.publish_setting(actor=request.user,request=request,**data)
                    messages.success(request,'Новая версия настройки опубликована.')
                    return redirect('/admin/control/settings/')
                result=preview
            if kind=='announcement':
                obj=svc.create_announcement(actor=request.user,request=request,**data)
                return redirect(f'/admin/control/announcements/{obj.pk}/')
            if kind=='job':
                obj=jobs.enqueue_job(actor=request.user,request=request,**data)
                return redirect(resource_url('jobs',obj.pk))
            if kind=='retry':
                job=jobs.retry_job(actor=request.user,request=request,job_id=obj.pk,reason=data['reason'],idempotency_key=data['idempotency_key'])
                return redirect(resource_url('jobs',job.pk))
            if kind=='export':
                obj=jobs.enqueue_export(actor=request.user,request=request,**data)
                return redirect(resource_url('jobs',obj.pk))
            if kind in ('category','skill','alias','categoryskill'):
                from .workflows import execute_command
                execute_command(request,'catalogue.save',None,data)
                messages.success(request,'Запись справочника добавлена.')
                return redirect(resource_url('categories' if kind=='category' else 'skills'))
        except (APIException,DjangoValidationError,ValueError) as exc:form.add_error(None,str(getattr(exc,'detail',exc)))
    if kind=='content':
        from .content_models import LANGUAGES
        return render(request,'content_form.html',section,title=title,form=form,back_url='/admin/control/content/',languages=LANGUAGES)
    export_facts={'Область выгрузки':dict(form.fields['dataset'].choices).get(initial.get('dataset',request.GET.get('dataset','users'))),'Фильтры':filters or 'Все записи выбранного раздела'} if kind=='export' else None
    return render(request,'form.html',section,title=title,form=form,back_url=f'/admin/control/{section}/',notice=notice,submit_label='Подтвердить публикацию' if result else 'Предпросмотр' if kind=='setting' else 'Сохранить черновик' if kind=='announcement' else 'Подтвердить',facts=result or export_facts,publish=bool(result))


@require_http_methods(['GET','POST'])
def publish_content(request,pk):
    require_platform_admin_session(request)
    from .content_forms import ContentPublishForm
    from .content_services import publish_content as publish,latest_published
    model=apps.get_model('marketplace','ContentRevision');obj=get_object_or_404(model,pk=pk)
    latest=model.objects.filter(language=obj.language,published_at__isnull=False).order_by('-version').first()
    form=ContentPublishForm(request.POST if request.method=='POST' else None,initial={'expected_version':latest.version if latest else 0})
    if request.method=='POST' and form.is_valid():
        try:
            publish(actor=request.user,request=request,revision_id=pk,**form.cleaned_data)
            messages.success(request,'Редакция опубликована. Предыдущие согласия сохранены.')
            return redirect(resource_url('content-revisions',pk))
        except (APIException,DjangoValidationError,ValueError) as exc:form.add_error(None,str(getattr(exc,'detail',exc)))
    from .content_forms import HOME_LABELS
    labels={'legal_name':'Юридическое наименование','tax_id':'ИНН','address':'Адрес','email':'Email поддержки','phone':'Телефон поддержки','url':'Ссылка поддержки','response_time':'Срок ответа','withdrawal_rules':'Правила вывода','refund_rules':'Правила возврата','dispute_rules':'Правила спора'}
    return render(request,'content_preview.html','content',title=f'Публикация редакции {obj.language} · v{obj.version}',form=form,revision=obj,
        homepage=[{'label':HOME_LABELS.get(key,key),'text':value} for key,value in obj.payload.get('homepage',{}).items()],
        contacts=[{'label':labels.get(key,key),'text':value} for group in ['operator','support'] for key,value in obj.payload.get(group,{}).items()],back_url=resource_url('content-revisions',pk))


@require_http_methods(['GET','POST'])
def announcement(request,pk):
    require_platform_admin_session(request)
    from .content_services import preview_announcement,enqueue_announcement
    obj=get_object_or_404(apps.get_model('marketplace','Announcement'),pk=pk,author=request.user)
    form=ReasonForm(request.POST if request.method=='POST' else None,initial={'reason':obj.reason,'expected_version':obj.version})
    form.fields['expected_version']=forms.IntegerField(widget=forms.HiddenInput,initial=obj.version,min_value=1)
    if request.method=='POST' and form.is_valid():
        try:
            if request.POST.get('send')=='yes':
                job=enqueue_announcement(actor=request.user,request=request,announcement_id=pk,expected_version=form.cleaned_data['expected_version'],idempotency_key=form.cleaned_data['idempotency_key'],reason=form.cleaned_data['reason'])
                return redirect(resource_url('jobs',job.pk))
            preview_announcement(actor=request.user,request=request,announcement_id=pk)
            obj.refresh_from_db()
            form=ReasonForm(initial={'reason':obj.reason,'expected_version':obj.version})
            form.fields['expected_version']=forms.IntegerField(widget=forms.HiddenInput,initial=obj.version,min_value=1)
        except (APIException,DjangoValidationError,ValueError) as exc:form.add_error(None,str(getattr(exc,'detail',exc)))
    return render(request,'form.html','content',title='Предпросмотр объявления',form=form,back_url='/admin/control/content/',facts={'Заголовок':obj.title,'Текст':obj.text,'Аудитория':obj.audience,'Получателей':obj.recipient_count if obj.previewed_at else 'Предпросмотр не выполнен','Состояние':obj.get_state_display()},send=obj.state=='previewed',submit_label='Подтвердить отправку' if obj.state=='previewed' else 'Рассчитать аудиторию')


def export_download(request,pk):
    require_platform_admin_session(request)
    from .jobs import download_job
    return download_job(actor=request.user,request=request,job_id=pk)


def security_page(request):
    require_platform_admin_session(request)
    return render(request,'security.html',title='Подтверждение безопасности')
