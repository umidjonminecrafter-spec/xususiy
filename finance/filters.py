import django_filters
from .models import Transaction, Bonus, Fine


class FinancialReportFilter(django_filters.FilterSet):
    # Sanalar bo'yicha filter (Sizda skrinshotda turgan kalendar uchun)
    start_date = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    end_date = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    # Kassa va to'lov turi bo'yicha filter
    kassa = django_filters.NumberFilter(field_name="cashbox_id")

    class Meta:
        model = Transaction
        fields = ['type', 'kassa', 'start_date', 'end_date']


class BonusFilter(django_filters.FilterSet):
    employee = django_filters.NumberFilter(field_name='employee_id')
    user = django_filters.NumberFilter(field_name='employee_id')  # Alias
    date = django_filters.DateFilter(field_name='date')
    date__gte = django_filters.DateFilter(field_name='date', lookup_expr='gte')
    date__lte = django_filters.DateFilter(field_name='date', lookup_expr='lte')
    start_date = django_filters.DateFilter(field_name='date', lookup_expr='gte')
    end_date = django_filters.DateFilter(field_name='date', lookup_expr='lte')

    class Meta:
        model = Bonus
        fields = ['employee', 'user', 'date']


class FineFilter(django_filters.FilterSet):
    employee = django_filters.NumberFilter(field_name='employee_id')
    user = django_filters.NumberFilter(field_name='employee_id')  # Alias
    date = django_filters.DateFilter(field_name='date')
    date__gte = django_filters.DateFilter(field_name='date', lookup_expr='gte')
    date__lte = django_filters.DateFilter(field_name='date', lookup_expr='lte')
    start_date = django_filters.DateFilter(field_name='date', lookup_expr='gte')
    end_date = django_filters.DateFilter(field_name='date', lookup_expr='lte')

    class Meta:
        model = Fine
        fields = ['employee', 'user', 'date']