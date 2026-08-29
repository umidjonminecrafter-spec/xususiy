from django.contrib import admin
from academics.models import (
    Course, Room, Student, Group, StudentGroup, GroupTeacher, TeacherSalaryPayment, Attendance, Homework,
    StudentFieldSetting, CourseMaterial, Building, SchoolClass, ClassStudent, Parent, StudentAddress
)
from .models import BotMessageTemplate, LessonSchedule

# khsrfbksazgfnhakrsgnvksdrzjvnds
@admin.register(BotMessageTemplate)
class BotMessageTemplateAdmin(admin.ModelAdmin):
    list_display = ('title', 'template_type', 'is_active', 'organization')
    list_filter = ('template_type', 'is_active', 'organization')
    search_fields = ('title', 'text')
@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'price', 'duration_weeks', 'color', 'is_active', 'organization')
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
    list_display = ('id', 'first_name', 'last_name', 'phone', 'school_class', 'balance', 'is_archived', 'organization')
    list_filter = ('school_class', 'is_archived', 'organization', 'branch')
    search_fields = ('first_name', 'last_name', 'phone', 'school_class__grade_level', 'school_class__section')
    raw_id_fields = ('school_class',)

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
    list_display = ('id', 'title', 'group', 'teacher', 'deadline', 'due_date', 'organization')
    list_filter = ('deadline', 'due_date')
    search_fields = ('title', 'description', 'text', 'group__name')

@admin.register(LessonSchedule)
class LessonScheduleAdmin(admin.ModelAdmin):
    list_display = ('id','group', 'teacher')
    list_filter = ('start_time', 'end_time')


@admin.register(CourseMaterial)
class CourseMaterialAdmin(admin.ModelAdmin):
    list_display = ('id', 'course', 'title', 'material_type', 'is_published', 'order', 'organization')
    list_filter = ('material_type', 'is_published', 'organization')
    search_fields = ('title', 'description', 'course__name')


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'branch', 'capacity', 'organization')
    search_fields = ('name', 'address')
    list_filter = ('branch', 'organization')


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'grade_level', 'section', 'language', 'teacher', 'room', 'academic_year', 'organization')
    search_fields = ('grade_level', 'section', 'teacher__username')
    list_filter = ('language', 'academic_year', 'branch', 'organization')


@admin.register(ClassStudent)
class ClassStudentAdmin(admin.ModelAdmin):
    list_display = ('id', 'school_class', 'student', 'is_active', 'joined_at', 'organization')
    list_filter = ('is_active', 'school_class')


@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
    list_display = ('id', 'full_name', 'relation', 'phone', 'student', 'organization')
    search_fields = ('full_name', 'phone', 'student__first_name', 'student__last_name')
    list_filter = ('relation', 'organization')


@admin.register(StudentAddress)
class StudentAddressAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'region', 'district', 'parent_name', 'parent_phone', 'organization')
    search_fields = ('student__first_name', 'student__last_name', 'district', 'address')
    list_filter = ('region', 'organization')


