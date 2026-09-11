from rest_framework import serializers
from organizations.models import Organization, Branch, Tariff, Subscription, ExamSetting, ReceiptSetting, BackupSetting, TelegramNotificationSetting,LessonNotificationTemplate
class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'address', 'phone', 'latitude', 'longitude', 'role_permissions', 'available_roles']
        read_only_fields = ('id', 'created_at', 'updated_at')

class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ('id', 'organization', 'name', 'address', 'phone', 'created_at', 'updated_at')
        read_only_fields = ('id', 'organization', 'created_at', 'updated_at')

class TariffSerializer(serializers.ModelSerializer):
    discount_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    final_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Tariff
        fields = (
            'id', 'name', 'price', 'old_price', 'months', 'student_limit',
            'discount_enabled', 'discount_percent', 'discount_amount', 'final_price',
            'discount_badge', 'features', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'discount_amount', 'final_price', 'created_at', 'updated_at')

    def validate_discount_percent(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Chegirma foizi 0 dan 100 gacha bo'lishi kerak.")
        return value

class SubscriptionSerializer(serializers.ModelSerializer):
    tariff_name = serializers.CharField(source='tariff.name', read_only=True)
    
    class Meta:
        model = Subscription
        fields = '__all__'
        read_only_fields = ('id', 'organization', 'created_at', 'updated_at')


class ExamSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamSetting
        fields = '__all__'
        read_only_fields = ('organization',)


class ReceiptSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptSetting
        fields = '__all__'
        read_only_fields = ('organization',)


class BackupSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupSetting
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at', 'last_run_at')


class TelegramNotificationSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramNotificationSetting
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

class LessonNotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonNotificationTemplate
        fields = '__all__'
        read_only_fields = ('organization',)

class GlobalSearchSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    type = serializers.CharField()         # 'student', 'staff', 'group'
    type_display = serializers.CharField() # "O'quvchi", "Xodim/O'qituvchi", "Guruh"
    additional_info = serializers.CharField()


