from decimal import Decimal
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from drf_spectacular.utils import extend_schema_field
from finance.models import Bonus, Fine, FinanceSetting, FinanceAction, Transaction, Cashbox


class BonusSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)

    class Meta:
        model = Bonus
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


class FineSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)

    class Meta:
        model = Fine
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


class FinanceSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinanceSetting
        fields = '__all__'
        read_only_fields = ('organization', 'branch', 'created_at', 'updated_at')

    def validate(self, attrs):
        is_bonus = attrs.get('is_bonus_enabled', getattr(self.instance, 'is_bonus_enabled', True))
        is_auto_discount = attrs.get('is_auto_discount_enabled',
                                     getattr(self.instance, 'is_auto_discount_enabled', False))

        if not is_bonus and is_auto_discount:
            raise serializers.ValidationError({
                "is_auto_discount_enabled": "Bonus turlari o'chirilgan holatda avtochegirmani yoqish taqiqlanadi!"
            })
        return attrs


class FinanceActionSerializer(serializers.ModelSerializer):
    cashbox = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    student_name = serializers.SerializerMethodField()
    employee_name = serializers.SerializerMethodField()
    cashbox_name = serializers.SerializerMethodField()

    class Meta:
        model = FinanceAction
        fields = [
            'id', 'action_type', 'target_type', 'student', 'student_name',
            'employee', 'employee_name', 'cashbox', 'cashbox_name',
            'amount', 'reason', 'created_at'
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_student_name(self, obj):
        if obj.student:
            first_name = getattr(obj.student, 'first_name', '')
            last_name = getattr(obj.student, 'last_name', '')
            return f"{first_name} {last_name or ''}".strip()
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_employee_name(self, obj):
        if obj.employee:
            first_name = getattr(obj.employee, 'first_name', '')
            last_name = getattr(obj.employee, 'last_name', '')
            return f"{first_name} {last_name or ''}".strip()
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_cashbox_name(self, obj):
        if obj.action_type == 'PENALTY':
            return None

        if obj.transaction and obj.transaction.cashbox:
            return obj.transaction.cashbox.name

        t = Transaction.objects.filter(
            organization=obj.organization,
            amount=obj.amount,
            type='EXPENSE'
        ).filter(description__icontains=str(obj.reason or '')).first()

        if t and t.cashbox:
            return t.cashbox.name

        request = self.context.get('request')
        if request and request.data:
            cashbox_id = request.data.get('cashbox')
            if cashbox_id:
                try:
                    return Cashbox.objects.get(id=cashbox_id).name
                except Cashbox.DoesNotExist:
                    return None

        return None

    def validate(self, attrs):
        action_type = attrs.get('action_type')
        cashbox = attrs.get('cashbox')

        if action_type == 'BONUS' and not cashbox:
            raise ValidationError({"cashbox": "Bonus yozish uchun kassa (cashbox) tanlanishi shart!"})

        if action_type == 'PENALTY':
            if 'cashbox' in attrs:
                attrs.pop('cashbox')

        if action_type == 'PENALTY' and attrs.get('target_type') == 'STUDENT':
            student = attrs.get('student')
            amount = attrs.get('amount')
            if student and amount:
                student_balance = Decimal(str(student.balance))
                if student_balance < Decimal(str(amount)):
                    raise ValidationError({
                        "amount": f"Mablag' yetarli emas! Talabaning joriy balansi: "
                                  f"{int(student_balance):,} UZS. "
                                  f"Jarima summasi ({int(amount):,} UZS) balansdan oshib ketdi.".replace(",", " ")
                    })

        return attrs

    def create(self, validated_data):
        validated_data.pop('cashbox', None)
        return super().create(validated_data)
