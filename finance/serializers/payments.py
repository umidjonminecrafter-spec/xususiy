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
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        import re
        import datetime
        from decimal import Decimal
        from common.utils import parse_flexible_date, normalize_payment_method
        from finance.models import Cashbox
        from academics.models import Student

        request = self.context.get('request')
        user = request.user if request else None
        org = getattr(user, 'organization', None) if user else None

        # 1. Date normalization (date, sana, payment_date)
        raw_date = data.get('date') or data.get('sana') or data.get('payment_date')
        parsed_date = parse_flexible_date(raw_date, default=datetime.date.today())
        try:
            if isinstance(parsed_date, str):
                datetime.date.fromisoformat(parsed_date)
                data['date'] = parsed_date
            elif isinstance(parsed_date, (datetime.date, datetime.datetime)):
                data['date'] = parsed_date.strftime('%Y-%m-%d')
            else:
                data['date'] = datetime.date.today().isoformat()
        except ValueError:
            data['date'] = datetime.date.today().isoformat()

        # 2. Payment method normalization (payment_method, tolov_turi, to_lov_turi, type)
        raw_pm = data.get('payment_method') or data.get('tolov_turi') or data.get('to_lov_turi') or data.get('type') or 'naqd'
        data['payment_method'] = normalize_payment_method(raw_pm)

        # 3. Amount normalization (amount, summa, yechib_olish_summasi, sum)
        raw_amount = data.get('amount') or data.get('summa') or data.get('yechib_olish_summasi') or data.get('sum')
        if raw_amount is not None:
            clean_amt = str(raw_amount).replace(' ', '').replace(',', '.')
            try:
                data['amount'] = str(Decimal(clean_amt))
            except Exception:
                pass

        # 4. Student normalization
        raw_student = data.get('student') or data.get('student_id') or data.get('oquvchi')
        if isinstance(raw_student, dict) and 'id' in raw_student:
            data['student'] = raw_student['id']
        elif raw_student is not None:
            if isinstance(raw_student, int) or (isinstance(raw_student, str) and str(raw_student).isdigit()):
                data['student'] = int(raw_student)
            elif isinstance(raw_student, str) and raw_student.strip():
                st_str = raw_student.strip().lower()
                if st_str in ['tanlang', 'tanlang (noma\'lum / umumiy)', 'noma\'lum', 'umumiy', 'none', 'null', '0']:
                    data['student'] = None
                else:
                    st_qs = Student.objects.all()
                    if org:
                        st_qs = st_qs.filter(organization=org)
                    parts = raw_student.strip().split()
                    if len(parts) >= 2:
                        st_obj = st_qs.filter(first_name__icontains=parts[0], last_name__icontains=parts[1]).first()
                    else:
                        st_obj = st_qs.filter(first_name__icontains=parts[0]).first()
                    if st_obj:
                        data['student'] = st_obj.id
                    else:
                        data['student'] = None
            else:
                data['student'] = None
        else:
            data['student'] = None

        # 5. Cashbox normalization (cashbox, kassa, kassa_id, payment_type)
        raw_cb = data.get('cashbox') or data.get('kassa') or data.get('kassa_id')
        if isinstance(raw_cb, dict) and 'id' in raw_cb:
            data['cashbox'] = raw_cb['id']
        elif raw_cb is not None:
            if isinstance(raw_cb, int) or (isinstance(raw_cb, str) and str(raw_cb).isdigit()):
                data['cashbox'] = int(raw_cb)
            elif isinstance(raw_cb, str) and raw_cb.strip():
                match = re.match(r'^(\d+)', raw_cb.strip())
                if match:
                    data['cashbox'] = int(match.group(1))
                else:
                    cb_qs = Cashbox.objects.filter(name__icontains=raw_cb.strip(), is_archived=False)
                    if org:
                        cb_qs = cb_qs.filter(organization=org)
                    cb_obj = cb_qs.first()
                    if cb_obj:
                        data['cashbox'] = cb_obj.id

        if not data.get('cashbox') and org:
            default_cb = Cashbox.objects.filter(organization=org, is_archived=False).first()
            if default_cb:
                data['cashbox'] = default_cb.id

        # 6. Comment / Note normalization
        raw_comment = data.get('comment') or data.get('izoh') or data.get('qaytarish_sababi') or data.get('note')
        if raw_comment:
            data['comment'] = str(raw_comment).strip()

        # 7. Employee
        if user and user.is_authenticated:
            data['employee'] = user.id

        return super().to_internal_value(data)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        amount = attrs.get('amount')
        cashbox = attrs.get('cashbox')
        if amount and amount < 0 and cashbox:
            abs_amount = abs(amount)
            if cashbox.balance < abs_amount:
                bal_str = f"{int(cashbox.balance):,} UZS".replace(",", " ")
                amt_str = f"{int(abs_amount):,} UZS".replace(",", " ")
                raise serializers.ValidationError({
                    "detail": f"Kassada mablag' yetarli emas! Kassadagi joriy balans: {bal_str}. Yechib olinadigan summa: {amt_str}.",
                    "cashbox": f"Kassada mablag' yetarli emas! Joriy balans: {bal_str}.",
                    "amount": f"Kassada yetarli mablag' mavjud emas (Mavjud: {bal_str})."
                })
        return attrs

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
