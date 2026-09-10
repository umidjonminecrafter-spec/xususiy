from rest_framework import serializers
from crm.models import Pipeline, Source, LostReason, Section, LeadForm, Lead, CRMActivity, CRMLeadsHistory, CRMLeadLost

from academics.models import BotMessageTemplate


class SectionSerializer(serializers.ModelSerializer):
    leads_count = serializers.SerializerMethodField()
    lead_count = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def get_leads_count(self, obj):
        return obj.leads.filter(is_archived=False).count()

    def get_lead_count(self, obj):
        return self.get_leads_count(obj)


class PipelineSerializer(serializers.ModelSerializer):
    sections = SectionSerializer(many=True, read_only=True)
    leads_count = serializers.SerializerMethodField()
    lead_count = serializers.SerializerMethodField()

    class Meta:
        model = Pipeline
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def get_leads_count(self, obj):
        return obj.leads.filter(is_archived=False).count()

    def get_lead_count(self, obj):
        return self.get_leads_count(obj)


class SourceSerializer(serializers.ModelSerializer):
    leads_count = serializers.SerializerMethodField()
    lead_count = serializers.SerializerMethodField()

    class Meta:
        model = Source
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def get_leads_count(self, obj):
        return obj.leads.filter(is_archived=False).count()

    def get_lead_count(self, obj):
        return self.get_leads_count(obj)


class LostReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = LostReason
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

class LeadFormSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadForm
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

class LeadSerializer(serializers.ModelSerializer):
    pipeline_name = serializers.CharField(source='pipeline.name', read_only=True)
    source_name = serializers.CharField(source='source.name', default='', read_only=True)
    lost_reason_text = serializers.CharField(source='lost_reason.reason', default='', read_only=True)
    section_name = serializers.CharField(source='section.name', default='', read_only=True)

    class Meta:
        model = Lead
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at', 'created_by')

    def to_internal_value(self, data):
        # Support dynamic fields sent by the frontend
        data = data.copy()
        if 'full_name' in data and 'name' not in data:
            data['name'] = data['full_name']
        if 'phone_number' in data and 'phone' not in data:
            data['phone'] = data['phone_number']
        return super().to_internal_value(data)

    def validate(self, attrs):
        phone = attrs.get('phone')
        if phone:
            from academics.models import Student
            if Student.objects.filter(phone=phone, is_archived=True, balance__lt=0).exists():
                raise serializers.ValidationError({
                    "phone": "Ushbu telefon raqamli talaba arxivda qarzdorlik bilan turibdi. Uni lidga qaytarib bo'lmaydi!"
                })
        return attrs

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['full_name'] = instance.name
        rep['phone_number'] = instance.phone
        rep['pipeline'] = instance.pipeline_id
        
        # Format created_by as assigned_to object for frontend
        if instance.created_by:
            rep['assigned_to'] = {
                'id': instance.created_by.id,
                'username': instance.created_by.username,
                'first_name': instance.created_by.first_name,
                'last_name': instance.created_by.last_name,
                'full_name': instance.created_by.get_full_name() or instance.created_by.username,
            }
        else:
            rep['assigned_to'] = None
            
        return rep

class CRMActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = CRMActivity
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

class CRMLeadsHistorySerializer(serializers.ModelSerializer):
    # Sanani o'qishga qulay formatga o'giramiz (yil-oy-kun soat:daqiqa)
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = CRMLeadsHistory
        fields = ['id', 'change_details', 'created_at']

class CRMLeadLostSerializer(serializers.ModelSerializer):
    class Meta:
        model = CRMLeadLost
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')



class SMSBotTemplateSerializer(serializers.ModelSerializer):
    target_audience_display = serializers.CharField(source='get_target_audience_display', read_only=True)
    template_type_display = serializers.CharField(source='get_template_type_display', read_only=True)

    class Meta:
        model = BotMessageTemplate
        fields = ['id', 'title', 'target_audience', 'target_audience_display', 'template_type', 'template_type_display', 'text', 'is_active']


from .models import LeadForm, Lead


class LeadFormCRUDSerializer(serializers.ModelSerializer):
    """Adminlar uchun formani yaratish, ko'rish va o'zgartirish serializer-i"""

    class Meta:
        model = LeadForm
        fields = '__all__'


class PublicLeadSubmitSerializer(serializers.Serializer):
    """Tashqi foydalanuvchi formani to'ldirib yuborganda lid yaratuvchi serializer"""
    form_id = serializers.IntegerField(write_only=True)
    name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=50)

    # Qo'shimcha dinamik maydonlarni (masalan, Soat, Izoh) vaqtinchalik tutish uchun:
    additional_data = serializers.JSONField(required=False, default=dict)

    def save(self, **kwargs):
        form_id = self.validated_data['form_id']
        form_obj = LeadForm.objects.get(id=form_id)

        # Qo'shimcha kiritilgan ma'lumotlarni JSON ko'rinishida notes yoki commentga yozamiz
        notes_list = []
        if self.validated_data.get('additional_data'):
            for key, val in self.validated_data['additional_data'].items():
                notes_list.append({"field": key, "value": val})

        # Avtomatik Lid ochamiz
        lead = Lead.objects.create(
            organization=form_obj.organization,
            name=self.validated_data['name'],
            phone=self.validated_data['phone'],
            pipeline=form_obj.pipeline,
            section=form_obj.section,
            source=form_obj.source,
            notes=notes_list
        )
        return lead