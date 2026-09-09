from django.contrib import admin, messages
from rest_framework.exceptions import APIException, ValidationError
from .models import Contract, Deliverable, PasswordResetCode, Payment, Profile, Project, Proposal, WalletEntry, Withdrawal
from .services import process_withdrawal
from .models import Category, Skill, SkillAlias, CategorySkill, PlatformFee, ContractEvent, Message, Dispute, Review, Notification, AuditLog, ProjectAttachment, ClickFiscalReceipt
from .escrow import resolve_dispute
from django import forms
from decimal import Decimal
import uuid
from django.urls import path, reverse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.core.exceptions import PermissionDenied
from django.utils.html import format_html, format_html_join
from .admin_operations import adjust_balance


class BalanceAdjustmentForm(forms.Form):
    amount = forms.DecimalField(label='Сумма корректировки, UZS', max_digits=12, decimal_places=2)
    reason = forms.CharField(label='Основание', min_length=10, max_length=255, widget=forms.Textarea)
    reference = forms.UUIDField(widget=forms.HiddenInput)
    confirmed = forms.BooleanField(label='Подтверждаю изменение доступного баланса и основание операции')

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'category', 'budget_min', 'budget_max', 'status')
    list_filter = ('category', 'status')
    search_fields = ('title', 'description', 'client_name')
    readonly_fields = ('status', 'created_at', 'updated_at')
    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status not in ('draft', 'published'):
            return tuple(f.name for f in self.model._meta.fields) + ('skills',)
        return self.readonly_fields

@admin.register(Proposal)
class ProposalAdmin(admin.ModelAdmin):
    list_display = ('freelancer_name', 'project', 'amount', 'status')
    readonly_fields = ('status', 'created_at')
    def get_readonly_fields(self, request, obj=None):
        return tuple(f.name for f in self.model._meta.fields)
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'role', 'balance', 'created_at', 'balance_operation')
    list_filter = ('role',)
    search_fields = ('full_name', 'user__email', 'user__username')
    readonly_fields = ('balance', 'created_at')
    def get_urls(self):
        return [path('<int:pk>/adjust-balance/', self.admin_site.admin_view(self.adjust), name='marketplace_profile_adjust')] + super().get_urls()

    @admin.display(description='Корректировка')
    def balance_operation(self, obj):
        return format_html('<a href="{}">Открыть операцию</a>', reverse('admin:marketplace_profile_adjust', args=[obj.pk]))

    def adjust(self, request, pk):
        if not request.user.is_superuser:
            raise PermissionDenied
        profile = get_object_or_404(Profile, pk=pk)
        form = BalanceAdjustmentForm(request.POST or None, initial={'reference':uuid.uuid4()})
        if request.method == 'POST' and form.is_valid():
            try:
                adjust_balance(profile.user_id, form.cleaned_data['amount'], form.cleaned_data['reason'], form.cleaned_data['reference'], request.user)
            except ValidationError as error:
                form.add_error(None, str(error.detail))
            else:
                self.message_user(request, 'Корректировка проведена и записана в журнал.', messages.SUCCESS)
                return redirect('admin:marketplace_profile_change', pk)
        return TemplateResponse(request, 'admin/marketplace/balance_adjustment.html', {
            **self.admin_site.each_context(request), 'title':'Корректировка баланса: ' + profile.full_name,
            'profile':profile, 'form':form, 'opts':self.model._meta})
    def save_model(self, request, obj, form, change):
        if change:
            fields = [field for field in form.changed_data if field not in self.readonly_fields and field != 'skills']
            if fields:
                obj.save(update_fields=fields)
        else:
            obj.save()

class AuditAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        fields = tuple(f.name for f in self.model._meta.fields if f.name != 'file')
        return fields + ('protected_file',) if any(f.name == 'file' for f in self.model._meta.fields) else fields
    def get_exclude(self, request, obj=None):
        return ('file',) if any(f.name == 'file' for f in self.model._meta.fields) else ()
    @admin.display(description='Защищённый файл')
    def protected_file(self, obj):
        if not obj.file:
            return '—'
        return format_html('<a href="{}">{}</a>', reverse('admin-file-download', args=[obj._meta.model_name, obj.pk]), obj.filename)
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

class FeeCorrectionForm(forms.Form):
    version = forms.IntegerField(widget=forms.HiddenInput)
    policy = forms.CharField(widget=forms.HiddenInput)
    reason = forms.CharField(label='Основание исправления', min_length=10, max_length=1000, widget=forms.Textarea)
    confirmed = forms.BooleanField(label='Подтверждаю расчёт и сброс прежних подтверждений. Обе стороны должны принять новую версию.')


@admin.register(Contract)
class ContractAdmin(AuditAdmin):
    list_display = ('id', 'project', 'customer', 'freelancer', 'amount', 'fee_percent', 'fee_amount', 'actual_fee_amount', 'actual_net', 'released_amount', 'refunded_amount', 'status')

    @admin.display(description='Чистая выплата')
    def actual_net(self, obj):
        return obj.released_amount - obj.actual_fee_amount if obj.actual_fee_amount is not None else None
    list_filter = ('status',)
    search_fields = ('project__title', 'customer__username', 'freelancer__username')
    def get_readonly_fields(self, request, obj=None):
        return super().get_readonly_fields(request, obj) + ('related_records', 'fee_correction')

    def get_urls(self):
        return [path('<int:pk>/revise-fee/', self.admin_site.admin_view(self.revise_fee),
                     name='marketplace_contract_revise_fee')] + super().get_urls()

    @admin.display(description='Исправление комиссии')
    def fee_correction(self, obj):
        from .contract_revisions import validate_fee_revision
        try:
            validate_fee_revision(obj)
        except ValidationError:
            return 'Недоступно после финансовых операций или закрытия договора.'
        return format_html('<a href="{}">Пересчитать и запросить новые подтверждения</a>',
                           reverse('admin:marketplace_contract_revise_fee', args=[obj.pk]))

    def revise_fee(self, request, pk):
        from .contract_revisions import revise_unfunded_fee, validate_fee_revision
        from .fees import current_policy, settlement
        if not request.user.is_superuser:
            raise PermissionDenied
        contract = get_object_or_404(Contract, pk=pk)
        policy = current_policy()
        estimate = settlement(contract.amount, contract.amount, policy['freelancer_fee_percent'])
        form = FeeCorrectionForm(request.POST or None, initial={
            'version': contract.version, 'policy': policy['policy_version']})
        allowed = True
        blocked_reason = ''
        try:
            validate_fee_revision(contract)
        except ValidationError as error:
            blocked_reason = str(error.detail)
            allowed = False
        if request.method == 'POST' and allowed and form.is_valid():
            try:
                revise_unfunded_fee(pk, request.user, reason=form.cleaned_data['reason'],
                                   expected_version=form.cleaned_data['version'],
                                   expected_policy=form.cleaned_data['policy'])
            except APIException as error:
                form.add_error(None, str(error.detail))
            else:
                self.message_user(request, 'Комиссия исправлена. Договор ожидает новых подтверждений обеих сторон.', messages.SUCCESS)
                return redirect('admin:marketplace_contract_change', pk)
        return TemplateResponse(request, 'admin/marketplace/fee_correction.html', {
            **self.admin_site.each_context(request), 'title': f'Исправление комиссии договора №{pk}',
            'opts': self.model._meta, 'contract': contract, 'form': form, 'policy': policy,
            'estimate': estimate, 'allowed': allowed, 'blocked_reason': blocked_reason})
    @admin.display(description='История и материалы сделки')
    def related_records(self, obj):
        return format_html_join(' | ', '<a href="{}?contract__id__exact={}">{}</a>',
            ((reverse('admin:marketplace_' + model + '_changelist'), obj.pk, label) for model, label in
             [('message','Сообщения и доказательства'), ('deliverable','Результаты работы'), ('contractevent','История статусов'),
              ('walletentry','Движение средств'), ('dispute','Спор'), ('review','Отзывы')]))

@admin.register(Deliverable)
class DeliverableAdmin(AuditAdmin):
    list_display = ('id', 'contract', 'filename', 'created_at')

@admin.register(Payment)
class PaymentAdmin(AuditAdmin):
    list_display = ('reference', 'user', 'contract', 'amount', 'provider', 'status')
    list_filter = ('provider', 'status')


@admin.register(ClickFiscalReceipt)
class ClickFiscalReceiptAdmin(AuditAdmin):
    list_display = ('payment', 'status', 'click_payment_id', 'attempts', 'last_error', 'updated_at')
    list_filter = ('status',)
    search_fields = ('payment__reference', 'click_payment_id')

@admin.register(WalletEntry)
class WalletEntryAdmin(AuditAdmin):
    list_display = ('user', 'kind', 'amount', 'created_at')

@admin.register(PasswordResetCode)
class PasswordResetCodeAdmin(AuditAdmin):
    list_display = ('user', 'expires_at', 'attempts', 'verified_at', 'used_at')

@admin.register(Withdrawal)
class WithdrawalAdmin(AuditAdmin):
    list_display = ('id', 'user', 'amount', 'destination', 'status', 'provider_reference')
    actions = ('mark_paid', 'reject')
    def save_model(self, request, obj, form, change):
        if change:
            Withdrawal.objects.filter(pk=obj.pk, status='pending').update(provider_reference=obj.provider_reference)
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return tuple(f for f in fields if f != 'provider_reference') if obj and obj.status == 'pending' else fields
    @admin.action(description='Подтвердить фактическую выплату (нужен номер перевода)')
    def mark_paid(self, request, queryset):
        for item in queryset:
            try:
                process_withdrawal(item.pk, 'paid', item.provider_reference, actor=request.user)
            except ValidationError as error:
                self.message_user(request, str(error.detail), messages.ERROR)

    @admin.action(description='Отклонить заявку и вернуть средства в кошелёк')
    def reject(self, request, queryset):
        for item in queryset:
            try:
                process_withdrawal(item.pk, 'rejected', actor=request.user)
            except ValidationError as error:
                self.message_user(request, str(error.detail), messages.ERROR)


class DisputeForm(forms.ModelForm):
    settlement_preview = forms.CharField(required=False, widget=forms.HiddenInput)
    confirm_settlement = forms.BooleanField(required=False, label='Подтверждаю показанные выплату, комиссию и возврат')
    class Meta:
        model = Dispute
        fields = '__all__'

    def clean(self):
        data = super().clean()
        if data.get('status') == 'resolved':
            amount = data.get('freelancer_amount')
            if amount is None or not Decimal('0') <= amount <= self.instance.contract.amount:
                raise forms.ValidationError('Укажите выплату исполнителю от 0 до суммы договора; остаток вернётся заказчику.')
            if len(data.get('resolution', '').strip()) < 10:
                raise forms.ValidationError('Укажите основание решения (не менее 10 символов).')
            from django.core import signing
            from .fees import settlement
            result = settlement(self.instance.contract.amount, amount, self.instance.contract.fee_percent)
            expected = {'dispute': self.instance.pk, 'gross': str(result['gross']),
                        'rate': str(self.instance.contract.fee_percent), 'reason': data['resolution']}
            try:
                preview = signing.loads(data.get('settlement_preview', ''), salt='dispute-settlement-preview', max_age=900)
            except signing.BadSignature:
                preview = None
            if preview != expected or not data.get('confirm_settlement'):
                self.data = self.data.copy()
                self.data['settlement_preview'] = signing.dumps(expected, salt='dispute-settlement-preview')
                raise forms.ValidationError(
                    f"Проверьте расчёт, отметьте подтверждение и сохраните повторно. "
                    f"Начислено: {result['gross']} UZS; комиссия: {result['fee']} UZS; "
                    f"исполнителю: {result['net']} UZS; возврат заказчику: {result['refund']} UZS.")
        return data


@admin.register(Dispute)
class DisputeAdmin(AuditAdmin):
    form = DisputeForm
    list_display = ('id', 'contract', 'opened_by', 'status', 'created_at')
    list_filter = ('status',)

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return tuple(f for f in fields if f not in {'status', 'resolution', 'freelancer_amount'}) if obj and obj.status != 'resolved' else fields

    def save_model(self, request, obj, form, change):
        if obj.status == 'resolved':
            resolve_dispute(obj.pk, request.user, obj.freelancer_amount, obj.resolution)
        else:
            from django.db import transaction
            with transaction.atomic():
                current = Dispute.objects.select_for_update().get(pk=obj.pk)
                if current.status == 'resolved':
                    return
                current.status = obj.status
                current.resolution = obj.resolution
                current.freelancer_amount = obj.freelancer_amount
                current.save()
                AuditLog.objects.create(actor=request.user, action='dispute_stage', object_type='dispute', object_id=str(obj.pk), detail={'status':obj.status})


class ReviewModerationForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = '__all__'
    def clean(self):
        data = super().clean()
        if data.get('published') is False and not data.get('moderation_reason', '').strip():
            raise forms.ValidationError('Для скрытия отзыва требуется основание.')
        return data


@admin.register(Review)
class ReviewAdmin(AuditAdmin):
    form = ReviewModerationForm
    list_display = ('id', 'contract', 'author', 'target', 'rating', 'published')
    def get_readonly_fields(self, request, obj=None):
        return tuple(f for f in super().get_readonly_fields(request, obj) if f not in {'published', 'moderation_reason'})
    def save_model(self, request, obj, form, change):
        if not obj.published and not obj.moderation_reason.strip():
            self.message_user(request, 'Для скрытия отзыва требуется основание.', messages.ERROR)
            return
        obj.save(update_fields=['published', 'moderation_reason'])
        AuditLog.objects.create(actor=request.user, action='review_moderation', object_type='review', object_id=str(obj.pk), detail={'published':obj.published, 'reason':obj.moderation_reason})


class DirectoryForm(forms.ModelForm):
    reason = forms.CharField(label='Основание изменения', min_length=3, max_length=500)


class DirectoryAdmin(admin.ModelAdmin):
    form = DirectoryForm
    list_display = ('name', 'active')
    list_filter = ('active',)
    search_fields = ('name',)
    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return ('slug',) if obj and hasattr(obj, 'slug') else ()

    def save_model(self, request, obj, form, change):
        from django.forms.models import model_to_dict
        from .taxonomy import audit
        before = model_to_dict(type(obj).objects.get(pk=obj.pk), exclude=['categories']) if change else {}
        obj.save()
        audit(obj, request.user, 'directory_change' if change else 'directory_create', before, form.cleaned_data['reason'])


@admin.register(Category)
class CategoryAdmin(DirectoryAdmin):
    list_display = ('name', 'slug', 'active', 'sort_order', 'icon_key')


class MergeSkillsForm(forms.Form):
    target = forms.ModelChoiceField(queryset=Skill.objects.filter(active=True, merged_into__isnull=True), label='Канонический навык')
    reason = forms.CharField(min_length=10, max_length=500, label='Основание объединения')
    confirmed = forms.BooleanField(label='Подтверждаю перенос показанных связей. Подтверждения навыков требуют отдельной проверки.')


@admin.register(Skill)
class SkillAdmin(DirectoryAdmin):
    list_display = ('name', 'slug', 'active', 'merged_into')
    search_fields = ('name', 'aliases__key')
    actions = ['merge_selected']

    def get_readonly_fields(self, request, obj=None):
        return super().get_readonly_fields(request, obj) + ('merged_into',)

    @admin.action(description='Объединить навыки с предпросмотром связей', permissions=['change'])
    def merge_selected(self, request, queryset):
        from django.core.exceptions import ValidationError as ModelValidationError
        from django.db import transaction
        from .taxonomy import merge_skills
        form = MergeSkillsForm(request.POST if request.POST.get('apply_merge') else None)
        form.fields['target'].queryset = Skill.objects.filter(active=True, merged_into__isnull=True).exclude(pk__in=queryset.values('pk'))
        if request.POST.get('apply_merge') and form.is_valid():
            try:
                with transaction.atomic():
                    for skill in queryset.order_by('pk'):
                        merge_skills(skill.pk, form.cleaned_data['target'].pk, actor=request.user, reason=form.cleaned_data['reason'])
            except ModelValidationError as exc:
                form.add_error(None, exc)
            else:
                self.message_user(request, 'Навыки объединены. Старые ID сохранены; верификация не присваивалась.')
                return None
        rows = [{'skill':s,'profiles':s.profiles.count(),'projects':s.projects.count(),'categories':s.categories.count()} for s in queryset]
        return TemplateResponse(request, 'admin/marketplace/merge_skills.html', {
            **self.admin_site.each_context(request), 'title':'Объединение навыков', 'form':form, 'rows':rows,
            'queryset':queryset, 'opts':self.model._meta})


@admin.register(SkillAlias)
class SkillAliasAdmin(DirectoryAdmin):
    list_display = ('key', 'skill')
    list_filter = ()
    search_fields = ('key', 'skill__name')
    readonly_fields = ()


@admin.register(CategorySkill)
class CategorySkillAdmin(DirectoryAdmin):
    list_display = ('category', 'skill', 'sort_order')
    list_filter = ('category',)
    search_fields = ('skill__name',)


@admin.register(PlatformFee)
class PlatformFeeAdmin(AuditAdmin):
    list_display = ('contract', 'gross_amount', 'fee_percent', 'fee_amount', 'currency', 'source', 'created_at')
    list_filter = ('source', 'currency')

admin.site.register(ContractEvent, AuditAdmin)
admin.site.register(Message, AuditAdmin)
admin.site.register(Notification, AuditAdmin)
admin.site.register(AuditLog, AuditAdmin)
admin.site.register(ProjectAttachment, AuditAdmin)
