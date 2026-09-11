from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from academics.models import Attendance


class GlobalAttendanceSerializer(serializers.ModelSerializer):
    student_id = serializers.IntegerField(source='student.id', read_only=True)
    student_name = serializers.SerializerMethodField()
    phone = serializers.CharField(source='student.phone', read_only=True)
    balance = serializers.IntegerField(source='student.balance', default=0, read_only=True)
    group_name = serializers.CharField(source='group.name', read_only=True)
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = Attendance
        fields = ['id', 'student_id', 'student_name', 'phone', 'balance', 'group_name', 'teacher_name', 'status', 'date']

    @extend_schema_field(serializers.CharField())
    def get_student_name(self, obj):
        if obj.student:
            return f"{obj.student.first_name} {obj.student.last_name or ''}".strip()
        return "Noma'lum o'quvchi"

    @extend_schema_field(serializers.CharField())
    def get_teacher_name(self, obj):
        if obj.group and obj.group.teacher:
            teacher = obj.group.teacher
            return f"{teacher.first_name or ''} {teacher.last_name or ''}".strip() or teacher.username
        return "O'qituvchi biriktirilmagan"