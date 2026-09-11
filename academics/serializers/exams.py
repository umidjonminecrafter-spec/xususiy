from rest_framework import serializers
from academics.models import Exam, ExamResult, Group


class ExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exam
        fields = '__all__'
        read_only_fields = ('organization',)

    def to_internal_value(self, data):
        data = data.copy()
        if 'title' in data and 'name' not in data:
            data['name'] = data['title']
        if 'exam_date' in data and 'date' not in data:
            data['date'] = data['exam_date']

        if 'group' in data and 'course' not in data and data['group']:
            try:
                group_obj = Group.objects.get(id=data['group'])
                data['course'] = group_obj.course_id
            except Group.DoesNotExist:
                pass

        return super().to_internal_value(data)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['title'] = instance.name
        rep['exam_date'] = instance.date

        if instance.group:
            rep['group'] = {
                'id': instance.group.id,
                'name': instance.group.name
            }
        else:
            rep['group'] = None

        return rep


class ExamResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamResult
        fields = '__all__'
        read_only_fields = ('organization',)
