from django.contrib import admin, messages
from rest_framework.exceptions import ValidationError
from .models import Contract, Deliverable, PasswordResetCode, Payment, Profile, Project, Proposal, WalletEntry, Withdrawal
from .services import process_withdrawal

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'category', 'budget_min', 'budget_max', 'status')
    list_filter = ('category', 'status')
    search_fields = ('title', 'description', 'client_name')
    readonly_fields = ('status', 'created_at', 'updated_at')

@admin.register(Proposal)
class ProposalAdmin(admin.ModelAdmin):
    list_display = ('freelancer_name', 'project', 'amount', 'status')
    readonly_fields = ('status', 'created_at')

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'role', 'created_at')
    list_filter = ('role',)
    search_fields = ('full_name', 'user__email', 'user__username')
    readonly_fields = ('balance', 'created_at')
    def save_model(self, request, obj, form, change):
        if change:
            fields = [field for field in form.changed_data if field not in self.readonly_fields]
            if fields:
                obj.save(update_fields=fields)
        else:
            obj.save()

class AuditAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(f.name for f in self.model._meta.fields)
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Contract)
class ContractAdmin(AuditAdmin):
    list_display = ('id', 'project', 'customer', 'freelancer', 'amount', 'status')
    list_filter = ('status',)

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
                process_withdrawal(item.pk, 'paid', item.provider_reference)
            except ValidationError as error:
                self.message_user(request, str(error.detail), messages.ERROR)
    @admin.action(description='Отклонить заявку и вернуть средства в кошелёк')
    def reject(self, request, queryset):
        for item in queryset:
            try:
                process_withdrawal(item.pk, 'rejected')
            except ValidationError as error:
                self.message_user(request, str(error.detail), messages.ERROR)
