from django.contrib import admin
from kpi.models import KPITemplate, KPIGoal, KPISubGoal, KPILog


@admin.register(KPITemplate)
class KPITemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'role', 'organization')
    list_filter = ('role', 'organization')
    search_fields = ('name', 'role')


@admin.register(KPIGoal)
class KPIGoalAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'employee', 'start_date', 'end_date', 'total_progress', 'status', 'organization')
    list_filter = ('status', 'start_date', 'end_date', 'organization')
    search_fields = ('name', 'employee__first_name', 'employee__last_name')


@admin.register(KPISubGoal)
class KPISubGoalAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'parent_goal', 'metric_type', 'system_event', 'target_value', 'current_value', 'weight', 'organization')
    list_filter = ('metric_type', 'system_event', 'organization')
    search_fields = ('name', 'parent_goal__name')


@admin.register(KPILog)
class KPILogAdmin(admin.ModelAdmin):
    list_display = ('id', 'sub_goal', 'changed_value', 'created_at', 'organization')
    list_filter = ('created_at', 'organization')
    search_fields = ('sub_goal__name', 'description')
