from django.contrib import admin, messages
from rest_framework.exceptions import ValidationError
from .models import Contract, Deliverable, PasswordResetCode, Payment, Profile, Project, Proposal, WalletEntry, Withdrawal
from .services import process_withdrawal
from .models import Category, Skill, ContractEvent, Message, Dispute, Review, Notification, AuditLog, ProjectAttachment
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

@admin.register(Contract)
class ContractAdmin(AuditAdmin):
    list_display = ('id', 'project', 'customer', 'freelancer', 'amount', 'status')
    list_filter = ('status',)
    search_fields = ('project__title', 'customer__username', 'freelancer__username')
    def get_readonly_fields(self, request, obj=None):
        return super().get_readonly_fields(request, obj) + ('related_records',)
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


@admin.register(Category, Skill)
class DirectoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'active')
    list_filter = ('active',)
    search_fields = ('name',)
    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register(ContractEvent, AuditAdmin)
admin.site.register(Message, AuditAdmin)
admin.site.register(Notification, AuditAdmin)
admin.site.register(AuditLog, AuditAdmin)
admin.site.register(ProjectAttachment, AuditAdmin)
