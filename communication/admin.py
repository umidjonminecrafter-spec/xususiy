from django.contrib import admin

from communication.models import Notification, NotificationSchedule


@admin.register(NotificationSchedule)
class NotificationScheduleAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'delivery_mode', 'send_at', 'status', 'organization', 'sent_at', 'total_sent', 'total_failed')
    list_filter = ('delivery_mode', 'status', 'send_at')
    search_fields = ('title', 'message')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'type', 'organization', 'user', 'is_read', 'created_at')
    list_filter = ('type', 'is_read', 'created_at')
    search_fields = ('title', 'message')
