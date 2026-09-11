from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from finance.models import Transaction, TransactionCategory, CashTransaction, Cashbox
from common.utils import normalize_payment_method, parse_flexible_date


class TransactionCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionCategory
        fields = ['id', 'name', 'type', 'created_at']
        read_only_fields = ['id', 'created_at']


class TransactionSerializer(serializers.ModelSerializer):
    cashbox_name = serializers.CharField(source='cashbox.name', read_only=True)
    student_name = serializers.CharField(source='student.full_name', read_only=True, default=None)
    employee_name = serializers.CharField(source='employee.username', read_only=True, default=None)
    
    payment_method = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    comment = serializers.SerializerMethodField()
    group_name = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField()
    lesson_date = serializers.SerializerMethodField()
    dars_sanasi = serializers.SerializerMethodField()
    old_balance = serializers.SerializerMethodField()
    new_balance = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            'id', 'cashbox', 'cashbox_name', 'amount', 'type',
            'category', 'student', 'student_name', 'employee',
            'employee_name', 'description', 'created_at',
            'payment_method', 'category_name', 'comment',
            'group_name', 'group', 'lesson_date', 'dars_sanasi',
            'old_balance', 'new_balance'
        ]

    @extend_schema_field(serializers.CharField)
    def get_payment_method(self, obj):
        if obj.source_payment:
            return obj.source_payment.payment_method
        if obj.source_cashtransaction:
            return obj.source_cashtransaction.payment_method
        return "naqd"

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_category_name(self, obj):
        if obj.source_expense:
            return obj.source_expense.category.name if obj.source_expense.category else "Xarajat"
        if obj.source_cashtransaction:
            return obj.source_cashtransaction.category_name
        if obj.source_payment:
            return "O'quvchi to'lovi"
        return obj.category

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_comment(self, obj):
        if obj.source_payment:
            return obj.source_payment.comment
        if obj.source_expense:
            return obj.source_expense.description
        if obj.source_cashtransaction:
            return obj.source_cashtransaction.comment
        return obj.description

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_group_name(self, obj):
        if obj.student:
            first_group = obj.student.student_groups.filter(group__status='active').first()
            if first_group:
                return first_group.group.name
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_group(self, obj):
        return self.get_group_name(obj)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_lesson_date(self, obj):
        if obj.student:
            return str(obj.student.payment_date) if obj.student.payment_date else None
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_dars_sanasi(self, obj):
        return self.get_lesson_date(obj)

    @extend_schema_field(serializers.FloatField)
    def get_old_balance(self, obj):
        if obj.student:
            try:
                amount = obj.amount or 0
                current_balance = obj.student.balance or 0
                if obj.type == 'INCOME':
                    return float(current_balance - amount)
                else:
                    return float(current_balance + amount)
            except Exception:
                return 0.0
        return 0.0

    @extend_schema_field(serializers.FloatField)
    def get_new_balance(self, obj):
        if obj.student:
            return float(obj.student.balance or 0)
        return 0.0


    def validate(self, attrs):
        tx_type = attrs.get('type') or (self.instance.type if self.instance else None)
        description = attrs.get('description') or ''
        student = attrs.get('student')
        amount = attrs.get('amount') if 'amount' in attrs else (self.instance.amount if self.instance else None)
        cashbox = attrs.get('cashbox') or (self.instance.cashbox if self.instance else None)

        if amount is not None and Decimal(str(amount)) <= 0:
            raise serializers.ValidationError({"amount": "Tranzaksiya summasi musbat (0 dan katta) bo'lishi shart! ⚠️"})

        if tx_type == 'INCOME':
            desc_lower = str(description).lower().strip()
            if any(x in desc_lower for x in ['o\'quvchi', 'oquvchi', 'talaba', 'student']):
                if not student:
                    raise serializers.ValidationError({
                        "student": "Ushbu tranzaksiya turi uchun o'quvchini tanlash majburiy!"
                    })
        elif tx_type == 'EXPENSE':
            if cashbox and amount is not None:
                amount_dec = Decimal(str(amount))
                cb_balance = Decimal(str(cashbox.balance or 0))
                if self.instance and self.instance.cashbox_id == cashbox.id and self.instance.type == 'EXPENSE':
                    available = cb_balance + Decimal(str(self.instance.amount or 0))
                else:
                    available = cb_balance

                if available < amount_dec:
                    bal_str = f"{int(cb_balance):,} UZS".replace(",", " ")
                    amt_str = f"{int(amount_dec):,} UZS".replace(",", " ")
                    raise serializers.ValidationError({
                        "cashbox": f"Kassada mablag' yetarli emas! Kassadagi joriy balans: {bal_str}. Chiqim summasi: {amt_str}. Kassa balansi manfiyga tushishi taqiqlanadi! ⚠️"
                    })

        return attrs


class CashTransactionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True, default=None)
    employee_name = serializers.SerializerMethodField(read_only=True)
    cashbox_name = serializers.CharField(source='cashbox.name', read_only=True, default=None)
    description = serializers.CharField(source='comment', required=False, allow_blank=True, allow_null=True)
    payment_method = serializers.CharField(required=False, default='naqd', allow_blank=True, allow_null=True)
    date = serializers.DateField(required=False, default=timezone.now)

    class Meta:
        model = CashTransaction
        fields = [
            'id', 'cashbox', 'cashbox_name', 'transaction_type',
            'payment_method', 'amount', 'date', 'student',
            'student_name', 'employee', 'employee_name',
            'category_name', 'comment', 'description'
        ]

    def to_internal_value(self, data):
        if hasattr(data, 'copy'):
            data = data.copy()
        elif hasattr(data, 'dict'):
            data = data.dict()
        else:
            data = dict(data) if data else {}

        pm = (
            data.get('payment_method') or
            data.get('payment_type') or
            data.get('paymentType') or
            data.get('to_lov_turi') or
            data.get('tolov_turi') or
            data.get('method')
        )
        data['payment_method'] = normalize_payment_method(pm)

        tt = data.get('transaction_type') or data.get('type') or data.get('action_type')
        if tt:
            data['transaction_type'] = str(tt).lower().strip()
        else:
            data['transaction_type'] = 'kirim'

        if not data.get('cashbox') and data.get('cashbox_id'):
            data['cashbox'] = data.get('cashbox_id')
        if not data.get('cashbox'):
            request = self.context.get('request')
            if request and getattr(request, 'user', None) and getattr(request.user, 'organization', None):
                cb = Cashbox.objects.filter(organization=request.user.organization).first()
                if cb:
                    data['cashbox'] = cb.id

        if not data.get('student') and data.get('student_id'):
            data['student'] = data.get('student_id')

        if not data.get('employee') and data.get('employee_id'):
            data['employee'] = data.get('employee_id')

        d = data.get('date') or data.get('sana')
        data['date'] = parse_flexible_date(d)

        if not data.get('category_name') and data.get('category'):
            data['category_name'] = str(data['category'])
        if not data.get('comment') and data.get('description'):
            data['comment'] = str(data['description'])

        return super().to_internal_value(data)

    def validate_payment_method(self, value):
        return normalize_payment_method(value)

    def validate_date(self, value):
        if not value:
            return timezone.now().date()
        return value

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_employee_name(self, obj):
        if obj.employee:
            parts = [obj.employee.first_name, obj.employee.last_name]
            full_name = " ".join([p for p in parts if p]).strip()
            return full_name if full_name else obj.employee.username
        return None

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.cashbox:
            ret['cashbox'] = instance.cashbox.name
        return ret

    def validate(self, attrs):
        tx_type = attrs.get('transaction_type')
        student = attrs.get('student')
        employee = attrs.get('employee')

        if tx_type == 'kirim':
            amount = attrs.get('amount') if 'amount' in attrs else (self.instance.amount if self.instance else None)
            if amount is not None and Decimal(str(amount)) <= 0:
                raise serializers.ValidationError({"amount": "Kirim summasi musbat (0 dan katta) bo'lishi shart! ⚠️"})

        elif tx_type == 'chiqim':
            amount = attrs.get('amount') if 'amount' in attrs else (self.instance.amount if self.instance else None)
            if amount is not None and Decimal(str(amount)) <= 0:
                raise serializers.ValidationError({"amount": "Chiqim summasi musbat (0 dan katta) bo'lishi shart! ⚠️"})

            comment_val = attrs.get('comment') or ''
            category_val = attrs.get('category_name') or ''
            combined_text = f"{comment_val} {category_val}".lower()

            employee_keywords = ['xodim', 'oylik', 'ish haqi', 'ish_haqi', 'salary', 'employee']
            if any(kw in combined_text for kw in employee_keywords):
                if not employee:
                    raise serializers.ValidationError({
                        "employee": "Xodim uchun chiqim qilinganda xodimni tanlash majburiy! ⚠️"
                    })

            if not student and not employee:
                raise serializers.ValidationError({
                    "non_field_errors": "Kassadan chiqim qilinganda kimga (xodim yoki o'quvchiga) chiqim bo'layotganini tanlash majburiy! ⚠️"
                })
            if student and employee:
                raise serializers.ValidationError({
                    "non_field_errors": "Chiqim amaliyotida bir vaqtning o'zida ham xodimni, ham o'quvchini tanlab bo'lmaydi!"
                })

            cashbox = attrs.get('cashbox') or (self.instance.cashbox if self.instance else None)
            if not cashbox:
                raise serializers.ValidationError({"cashbox": "Chiqim uchun kassa tanlanishi shart! ⚠️"})

            request = self.context.get('request')
            user = request.user if request else None
            if user and user.is_authenticated and not user.is_superuser and getattr(user, 'role', '') not in ('owner', 'admin'):
                user_branch_ids = set(user.branches.values_list('id', flat=True))
                if user.branch_id:
                    user_branch_ids.add(user.branch_id)
                if user_branch_ids and cashbox.branch_id and cashbox.branch_id not in user_branch_ids:
                    raise serializers.ValidationError({
                        "cashbox": "Siz faqat o'zingizga biriktirilgan filial kassasidan chiqim qila olasiz!"
                    })

            if amount is not None:
                amount_dec = Decimal(str(amount))
                cb_balance = Decimal(str(cashbox.balance or 0))

                if self.instance and self.instance.cashbox_id == cashbox.id and getattr(self.instance, 'transaction_type', '') == 'chiqim':
                    available = cb_balance + Decimal(str(self.instance.amount or 0))
                else:
                    available = cb_balance

                if available < amount_dec:
                    bal_str = f"{int(cb_balance):,} UZS".replace(",", " ")
                    amt_str = f"{int(amount_dec):,} UZS".replace(",", " ")
                    raise serializers.ValidationError({
                        "cashbox": f"Kassada mablag' yetarli emas! Kassadagi joriy balans: {bal_str}. Chiqim summasi: {amt_str}. Kassa balansi manfiyga tushishi taqiqlanadi! ⚠️"
                    })

        return attrs


class CashTransferSerializer(serializers.Serializer):
    from_cashbox = serializers.PrimaryKeyRelatedField(queryset=Cashbox.objects.all())
    to_cashbox = serializers.PrimaryKeyRelatedField(queryset=Cashbox.objects.all())
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    comment = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')
    izoh = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')

    def validate(self, attrs):
        from_cashbox = attrs.get('from_cashbox')
        to_cashbox = attrs.get('to_cashbox')
        amount = attrs.get('amount')

        request = self.context.get('request')
        if request and request.user and request.user.organization:
            org = request.user.organization
            if from_cashbox.organization != org or to_cashbox.organization != org:
                raise serializers.ValidationError("Kassa sizning tashkilotingizga tegishli emas!")

        if from_cashbox == to_cashbox:
            raise serializers.ValidationError({"to_cashbox": "Bir xil kassaga pul o'tkazib bo'lmaydi! ⚠️"})
        if amount <= 0:
            raise serializers.ValidationError({"amount": "O'tkazma summasi 0 dan katta bo'lishi kerak!"})

        if from_cashbox.balance < amount:
            bal_str = f"{int(from_cashbox.balance):,} UZS".replace(",", " ")
            amt_str = f"{int(amount):,} UZS".replace(",", " ")
            raise serializers.ValidationError({
                "from_cashbox": f"'{from_cashbox.name}' kassasida yetarli mablag' mavjud emas! (Balans: {bal_str}, O'tkazma: {amt_str}). Kassa manfiyga tushishi taqiqlanadi! ⚠️"
            })
        return attrs
