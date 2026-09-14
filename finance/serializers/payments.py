from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from finance.models import MonthlyIncome, Payment, Sale


class MonthlyIncomeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonthlyIncome
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


class PaymentSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField(read_only=True)
    employee = serializers.SerializerMethodField(read_only=True)
    cashbox_name = serializers.CharField(source='cashbox.name', read_only=True, default="Noma'lum kassa")

    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else data
        if 'student_id' in data and 'student' not in data:
            data['student'] = data['student_id']
        elif 'student' in data and isinstance(data['student'], dict) and 'id' in data['student']:
            data['student'] = data['student']['id']
        return super().to_internal_value(data)

    @extend_schema_field(serializers.CharField)
    def get_student_name(self, obj):
        if obj.student:
            first = getattr(obj.student, 'first_name', '')
            last = getattr(obj.student, 'last_name', '')
            return f"{first} {last or ''}".strip()
        return "Talaba tanlanmadi"

    @extend_schema_field(serializers.CharField)
    def get_employee(self, obj):
        if obj.employee:
            parts = [obj.employee.first_name, obj.employee.last_name]
            full_name = " ".join([p for p in parts if p]).strip()
            return full_name if full_name else obj.employee.username
        return "Tizim"

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        method = instance.payment_method
        rep['type'] = method
        rep['payment_type'] = method
        rep['employee_name'] = rep.get('employee') or "Noma'lum"
        rep['note'] = instance.comment or ""
        rep['izoh'] = instance.comment or ""
        return rep


class SaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sale
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')
