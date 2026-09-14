import json
import datetime
from decimal import Decimal
from rest_framework import serializers

from finance.models import ExpenseCategory, ExpenseSubcategory, Expense
from common.utils import normalize_payment_method


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


class ExpenseSubcategorySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = ExpenseSubcategory
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    subcategory_name = serializers.CharField(source='subcategory.name', default='', read_only=True)
    cashbox_name = serializers.CharField(source='cashbox.name', read_only=True)

    class Meta:
        model = Expense
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)

        # Frontend fields mapping
        if 'expense_date' in data and 'date' not in data:
            data['date'] = data['expense_date']

        if 'date' in data and data['date']:
            try:
                datetime.date.fromisoformat(str(data['date']))
            except ValueError:
                raise serializers.ValidationError(
                    {"expense_date": "Sana formati noto'g'ri (YYYY-MM-DD bo'lishi kerak)."})

        request = self.context.get('request')
        user = request.user if request else None

        if user and user.is_authenticated:
            full_name = user.get_full_name().strip()
            created_by = full_name if full_name else user.username

            if hasattr(user, 'organization') and user.organization:
                data['organization'] = user.organization.id
        else:
            created_by = "Tizim"

        # Frontend yuborgan payment_type (Kassa ID) ni cashbox maydoniga o'giramiz
        payment_type = data.get('payment_type')
        if payment_type:
            data['cashbox'] = payment_type

        recipient = data.get('recipient', '')
        comment = data.get('comment', '') or data.get('izoh', '')
        name = data.get('name', '') or data.get('title', '') or data.get('nomi', '')

        packed_data = {
            'recipient': recipient,
            'payment_type': payment_type,
            'comment': comment,
            'name': name,
            'created_by': created_by
        }
        data['description'] = json.dumps(packed_data, ensure_ascii=False)

        return super().to_internal_value(data)

    def validate(self, attrs):
        if 'payment_method' in attrs:
            attrs['payment_method'] = normalize_payment_method(attrs.get('payment_method'))

        cashbox = attrs.get('cashbox') or (self.instance.cashbox if self.instance else None)
        amount = attrs.get('amount') if 'amount' in attrs else (self.instance.amount if self.instance else None)

        request = self.context.get('request')
        user = request.user if request else None

        if amount is not None:
            amount_dec = Decimal(str(amount))
            if amount_dec <= 0:
                raise serializers.ValidationError({"amount": "Xarajat summasi musbat (0 dan katta) bo'lishi shart! ⚠️"})

        if cashbox:
            # 1. Filial mosligi tekshiruvi: Menejer faqat o'z filialidagi kassadan foydalana oladi
            if user and user.is_authenticated and not user.is_superuser and getattr(user, 'role', '') not in ('owner', 'admin'):
                user_branch_ids = set(user.branches.values_list('id', flat=True))
                if user.branch_id:
                    user_branch_ids.add(user.branch_id)
                if user_branch_ids and cashbox.branch_id and cashbox.branch_id not in user_branch_ids:
                    raise serializers.ValidationError({
                        "cashbox": "Siz faqat o'zingizga biriktirilgan filial kassasidan xarajat qila olasiz! Boshqa filial kassasidan pul sarflash taqiqlanadi."
                    })

            # 2. Kassa balansi tekshiruvi: Xarajat uchun kassada yetarli pul bo'lishi shart!
            if amount is not None:
                amount_dec = Decimal(str(amount))
                cb_balance = Decimal(str(cashbox.balance or 0))

                # Agar mavjud xarajat o'sha kassada tahrirlanayotgan bo'lsa, mavjud summani inobatga olamiz
                if self.instance and self.instance.cashbox_id == cashbox.id:
                    available = cb_balance + Decimal(str(self.instance.amount or 0))
                else:
                    available = cb_balance

                if available < amount_dec:
                    bal_str = f"{int(cb_balance):,} UZS".replace(",", " ")
                    amt_str = f"{int(amount_dec):,} UZS".replace(",", " ")
                    raise serializers.ValidationError({
                        "cashbox": f"Kassada mablag' yetarli emas! Kassadagi joriy balans: {bal_str}. Xarajat summasi: {amt_str}. Kassa balansi manfiyga tushishi taqiqlanadi! ⚠️"
                    })

        return attrs

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        # Default fallbacks
        rep['recipient'] = ''
        rep['payment_type'] = instance.cashbox_id if instance.cashbox else None
        rep['comment'] = instance.description or ''
        rep['izoh'] = instance.description or ''
        rep['name'] = instance.description or ''
        rep['title'] = instance.description or ''
        rep['created_by'] = 'Admin'
        rep['expense_date'] = instance.date.isoformat() if instance.date else None

        if instance.description:
            try:
                unpacked = json.loads(instance.description)
                if isinstance(unpacked, dict):
                    rep['recipient'] = unpacked.get('recipient', '')
                    rep['payment_type'] = unpacked.get('payment_type') or instance.cashbox_id
                    rep['comment'] = unpacked.get('comment', '')
                    rep['izoh'] = unpacked.get('comment', '')
                    rep['name'] = unpacked.get('name') or unpacked.get('comment') or (
                        instance.category.name if instance.category else 'Xarajat')
                    rep['title'] = rep['name']
                    rep['created_by'] = unpacked.get('created_by') or 'Admin'
            except json.JSONDecodeError:
                pass

        return rep
