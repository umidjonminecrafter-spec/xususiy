from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from academics.models import (
    LessonSchedule, LessonTime, OnlineLesson, Homework, GroupLesson
)
from accounts.serializers import UserSerializer


class LessonScheduleSerializer(serializers.ModelSerializer):
    teacher_detail = UserSerializer(source='teacher', read_only=True)
    teacher_name = serializers.CharField(source='teacher.get_full_name', read_only=True, default='')
    group_name = serializers.CharField(source='group.name', read_only=True)
    course_name = serializers.CharField(source='group.course.name', read_only=True, default='')
    day_type_display = serializers.CharField(source='get_day_type_display', read_only=True)
    group_days = serializers.JSONField(source='group.days', read_only=True, default=list)

    class Meta:
        model = LessonSchedule
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


class LessonTimeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonTime
        fields = '__all__'
        read_only_fields = ('organization',)


class OnlineLessonSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source='group.name', read_only=True)
    course_name = serializers.CharField(source='group.course.name', read_only=True, default='')
    has_video = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = OnlineLesson
        fields = '__all__'
        read_only_fields = ('organization',)

    @extend_schema_field(serializers.BooleanField())
    def get_has_video(self, obj):
        return bool(obj.video_url)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['group_name'] = instance.group.name if instance.group else None
        rep['course_name'] = instance.group.course.name if instance.group and instance.group.course else None
        rep['has_video'] = bool(instance.video_url)
        return rep


class HomeworkSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source='group.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True, default='')

    class Meta:
        model = Homework
        fields = '__all__'
        read_only_fields = ('organization', 'created_by', 'created_at', 'updated_at')


class SetLessonTopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupLesson
        fields = ['title', 'description']
        extra_kwargs = {
            'title': {'required': True, 'allow_blank': False}
        }


class RescheduleLessonSerializer(serializers.Serializer):
    new_date = serializers.DateField(required=True)

    def validate_new_date(self, value):
        if value < timezone.now().date():
            raise serializers.ValidationError("Darsni o'tgan sanaga ko'chirish mumkin emas!")
        return value


class GroupLessonListSerializer(serializers.ModelSerializer):
    has_online_material = serializers.SerializerMethodField()

    class Meta:
        model = GroupLesson
        fields = [
            'id', 'group', 'date', 'title', 'description',
            'is_canceled', 'original_date', 'has_online_material'
        ]

    @extend_schema_field(serializers.BooleanField())
    def get_has_online_material(self, obj):
        return OnlineLesson.objects.filter(
            group=obj.group,
            attendance_date=obj.date
        ).exclude(video_url="").exists()
