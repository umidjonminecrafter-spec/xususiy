from rest_framework import serializers
from academics.models import BotMessageTemplate


class BotMessageTemplateSerializer(serializers.ModelSerializer):
    template_type_display = serializers.CharField(source='get_template_type_display', read_only=True)

    class Meta:
        model = BotMessageTemplate
        fields = ['id', 'title', 'template_type', 'template_type_display', 'text', 'is_active']


class BirthdayCalendarSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    birth_date = serializers.DateField()
    day = serializers.IntegerField()
    type = serializers.CharField()
    role_display = serializers.CharField()
