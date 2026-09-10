from django.contrib import admin
from academics.models import Course, Room, Student, Group, StudentGroup, GroupTeacher, TeacherSalaryPayment, Attendance, Homework,StudentFieldSetting, CourseMaterial
from .models import BotMessageTemplate, LessonSchedule

# khsrfbksazgfnhakrsgnvksdrzjvnds
@admin.register(BotMessageTemplate)
class BotMessageTemplateAdmin(admin.ModelAdmin):
    list_display = ('title', 'template_type', 'is_active', 'organization')
    list_filter = ('template_type', 'is_active', 'organization')
    search_fields = ('title', 'text')
@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'price', 'duration_weeks', 'organization')
    search_fields = ('name',)

@admin.register(StudentFieldSetting)
class StudentFieldSettingAdmin(admin.ModelAdmin):
    list_display = ('field_name', 'is_required', 'organization')
    search_fields = ('field_name',)
    list_filter = ('is_required',)

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'capacity', 'organization')
    search_fields = ('name',)

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('id', 'first_name', 'last_name', 'phone', 'balance', 'organization')
    search_fields = ('first_name', 'last_name', 'phone')

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'course', 'room', 'teacher', 'status', 'organization')
    list_filter = ('status', 'course', 'room')
    search_fields = ('name',)

@admin.register(StudentGroup)
class StudentGroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'group', 'joined_at', 'organization')

@admin.register(GroupTeacher)
class GroupTeacherAdmin(admin.ModelAdmin):
    list_display = ('id', 'group', 'teacher', 'organization')

@admin.register(TeacherSalaryPayment)
class TeacherSalaryPaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'teacher', 'amount', 'paid_at', 'period', 'organization')
    list_filter = ('period', 'paid_at')

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'group', 'student', 'date', 'status', 'organization')
    list_filter = ('status', 'date')


@admin.register(Homework)
class HomeworkAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'group', 'due_date', 'organization')
    list_filter = ('due_date',)
    search_fields = ('title', 'text', 'group__name')

@admin.register(LessonSchedule)
class LessonScheduleAdmin(admin.ModelAdmin):
    list_display = ('id','group', 'teacher')
    list_filter = ('start_time', 'end_time')


@admin.register(CourseMaterial)
class CourseMaterialAdmin(admin.ModelAdmin):
    list_display = ('id', 'course', 'title', 'material_type', 'is_published', 'order', 'organization')
    list_filter = ('material_type', 'is_published', 'organization')
    search_fields = ('title', 'description', 'course__name')

