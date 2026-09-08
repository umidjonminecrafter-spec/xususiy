from django.contrib import admin
from finance.models import (
    ExpenseCategory, ExpenseSubcategory, Expense, MonthlyIncome,
    Payment, Sale, Bonus, Fine, Salary, TeacherSalaryRule, TeacherSalaryCalculation, StaffSalaryPercent,
    TeacherWorkLog
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


@admin.register(TeacherWorkLog)
class TeacherWorkLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'date', 'teacher', 'branch', 'group', 'hours', 'hourly_rate', 'total_amount', 'is_substitution', 'original_teacher')
    list_filter = ('date', 'branch', 'is_substitution')
    search_fields = ('teacher__first_name', 'teacher__last_name', 'note', 'substitution_reason')