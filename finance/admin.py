from django.contrib import admin
from finance.models import (
    ExpenseCategory, ExpenseSubcategory, Expense, MonthlyIncome,
    Payment, Sale, Bonus, Fine, Salary, TeacherSalaryRule, TeacherSalaryCalculation, StaffSalaryPercent,
    Cashbox, CashTransaction, Transaction, FinanceAction, FinanceSetting, TransactionCategory
)


@admin.register(StaffSalaryPercent)
class StaffSalaryPercentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'percent', 'organization', 'comment')
    search_fields = ('name', 'comment')
    list_filter = ('percent', 'organization')
    fields = ('name', 'percent', 'organization', 'comment')

    def save_model(self, request, obj, form, change):
        if not obj.organization_id and not change:
            user_org_id = getattr(request.user, 'organization_id', None)
            if user_org_id:
                obj.organization_id = user_org_id
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        user_org_id = getattr(request.user, 'organization_id', None)
        if user_org_id:
            return qs.filter(organization_id=user_org_id)
        return qs.none()


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'organization')
    search_fields = ('name',)


@admin.register(ExpenseSubcategory)
class ExpenseSubcategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'category', 'name', 'organization')
    list_filter = ('category',)
    search_fields = ('name',)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('id', 'category', 'subcategory', 'amount', 'date', 'organization')
    list_filter = ('category', 'date')
    search_fields = ('description',)


@admin.register(MonthlyIncome)
class MonthlyIncomeAdmin(admin.ModelAdmin):
    list_display = ('id', 'amount', 'date', 'organization')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'amount', 'date', 'payment_method', 'organization')
    list_filter = ('date', 'payment_method')


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('id', 'product_or_course', 'amount', 'date', 'organization')
    list_filter = ('date',)


@admin.register(Bonus)
class BonusAdmin(admin.ModelAdmin):
    list_display = ('id', 'employee', 'amount', 'date', 'organization')
    list_filter = ('date', 'organization')
    search_fields = ('employee__first_name', 'employee__last_name', 'reason')


@admin.register(Fine)
class FineAdmin(admin.ModelAdmin):
    list_display = ('id', 'employee', 'amount', 'date', 'organization')
    list_filter = ('date', 'organization')
    search_fields = ('employee__first_name', 'employee__last_name', 'reason')


@admin.register(Salary)
class SalaryAdmin(admin.ModelAdmin):
    list_display = ('id', 'employee', 'amount', 'date', 'status', 'organization')
    list_filter = ('status', 'date')


@admin.register(TeacherSalaryRule)
class TeacherSalaryRuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'teacher', 'rule_type', 'rate', 'period', 'is_active', 'organization')
    list_filter = ('rule_type', 'is_active', 'period')


@admin.register(TeacherSalaryCalculation)
class TeacherSalaryCalculationAdmin(admin.ModelAdmin):
    list_display = ('id', 'teacher', 'calculated_amount', 'period', 'organization')
    list_filter = ('period',)


@admin.register(Cashbox)
class CashboxAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'branch', 'balance', 'is_archived', 'organization')
    list_filter = ('is_archived', 'branch', 'organization')
    search_fields = ('name',)
    readonly_fields = ('balance',)

    def save_model(self, request, obj, form, change):
        if not obj.organization_id and not change:
            user_org_id = getattr(request.user, 'organization_id', None)
            if user_org_id:
                obj.organization_id = user_org_id
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        user_org_id = getattr(request.user, 'organization_id', None)
        if user_org_id:
            return qs.filter(organization_id=user_org_id)
        return qs.none()


@admin.register(CashTransaction)
class CashTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'transaction_type', 'cashbox', 'amount', 'payment_method', 'date', 'employee', 'student', 'category_name', 'organization')
    list_filter = ('transaction_type', 'payment_method', 'date', 'organization', 'cashbox')
    search_fields = ('comment', 'category_name', 'employee__first_name', 'employee__last_name', 'student__first_name', 'student__last_name')

    def save_model(self, request, obj, form, change):
        if not obj.organization_id and not change:
            user_org_id = getattr(request.user, 'organization_id', None)
            if user_org_id:
                obj.organization_id = user_org_id
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        user_org_id = getattr(request.user, 'organization_id', None)
        if user_org_id:
            return qs.filter(organization_id=user_org_id)
        return qs.none()


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'category', 'cashbox', 'amount', 'student', 'employee', 'created_at', 'organization')
    list_filter = ('type', 'category', 'cashbox', 'created_at', 'organization')
    search_fields = ('description', 'student__first_name', 'student__last_name', 'employee__username')
    readonly_fields = ('created_at',)

    def save_model(self, request, obj, form, change):
        if not obj.organization_id and not change:
            user_org_id = getattr(request.user, 'organization_id', None)
            if user_org_id:
                obj.organization_id = user_org_id
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        user_org_id = getattr(request.user, 'organization_id', None)
        if user_org_id:
            return qs.filter(organization_id=user_org_id)
        return qs.none()


@admin.register(FinanceAction)
class FinanceActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'action_type', 'target_type', 'amount', 'student', 'employee', 'created_at', 'organization')
    list_filter = ('action_type', 'target_type', 'created_at', 'organization')
    search_fields = ('reason', 'student__first_name', 'student__last_name', 'employee__first_name', 'employee__last_name')
    readonly_fields = ('created_at',)

    def save_model(self, request, obj, form, change):
        if not obj.organization_id and not change:
            user_org_id = getattr(request.user, 'organization_id', None)
            if user_org_id:
                obj.organization_id = user_org_id
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        user_org_id = getattr(request.user, 'organization_id', None)
        if user_org_id:
            return qs.filter(organization_id=user_org_id)
        return qs.none()


@admin.register(FinanceSetting)
class FinanceSettingAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'is_count_bonus_enabled', 'is_auto_discount_enabled')
    list_filter = ('is_count_bonus_enabled', 'is_auto_discount_enabled', 'organization')

    def save_model(self, request, obj, form, change):
        if not obj.organization_id and not change:
            user_org_id = getattr(request.user, 'organization_id', None)
            if user_org_id:
                obj.organization_id = user_org_id
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        user_org_id = getattr(request.user, 'organization_id', None)
        if user_org_id:
            return qs.filter(organization_id=user_org_id)
        return qs.none()


@admin.register(TransactionCategory)
class TransactionCategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'type')
    list_filter = ('type',)
    search_fields = ('name',)