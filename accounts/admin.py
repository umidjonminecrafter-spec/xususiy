from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from accounts.models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('id', 'username', 'phone', 'first_name', 'last_name', 'role', 'organization', 'branch', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser', 'organization', 'branch')
    search_fields = ('username', 'phone', 'first_name', 'last_name', 'email')
    fieldsets = UserAdmin.fieldsets + (
        ('Tashkiliy maʼlumotlar', {'fields': ('role', 'organization', 'branch', 'branches', 'phone', 'position', 'birth_date', 'gender', 'photo')}),
        ('Oylik va Ish haqi (O\'qituvchilar)', {'fields': ('salary_type', 'hourly_rate', 'salary_percentage')}),
        ('Telegram', {'fields': ('telegram_chat_id', 'telegram_language')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Tashkiliy maʼlumotlar', {'fields': ('role', 'organization', 'branch', 'branches', 'phone', 'position', 'birth_date', 'gender', 'photo', 'salary_type', 'hourly_rate', 'salary_percentage')}),
    )