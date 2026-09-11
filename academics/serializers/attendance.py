from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from academics.models import Attendance, LeaveReason, Holiday, StudentGroup


class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField(read_only=True)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_student_name(self, obj):
        return str(obj.student) if obj.student else None

    class Meta:
        model = Attendance
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def validate(self, attrs):
        status = attrs.get('status', getattr(self.instance, 'status', None))
        reason = attrs.get('reason', getattr(self.instance, 'reason', None))

        if status == 'excused' and (not reason or not str(reason).strip()):
            raise serializers.ValidationError({
                "reason": "Talaba darsda sababli qatnashmagan bo'lsa, sababini ko'rsatish majburiy!"
            })
        return attrs

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        sg = StudentGroup.objects.filter(student_id=instance.student_id, group_id=instance.group_id).first()
        rep['student_group'] = sg.id if sg else None
        if instance.date:
            rep['lesson_date'] = instance.date.isoformat() if hasattr(instance.date, 'isoformat') else str(instance.date)
        else:
            rep['lesson_date'] = None
        rep['is_present'] = instance.status == 'present'
        rep['is_excused'] = instance.status == 'excused'
        rep['grade'] = instance.grade
        rep['reason'] = instance.reason or ("sababli" if instance.status == 'excused' else "")
        return rep


class LeaveReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveReason
        fields = '__all__'
        read_only_fields = ('organization',)


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')
