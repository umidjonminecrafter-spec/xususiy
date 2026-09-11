from rest_framework import serializers
from finance.models import Cashbox


class CashboxSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cashbox
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')
