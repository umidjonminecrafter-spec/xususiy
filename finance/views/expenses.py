from decimal import Decimal
from django.db import transaction as db_transaction
from django.db.models import Sum
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import viewsets, status, decorators
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from organizations.mixins import TenantViewSetMixin
from organizations.models import Branch
from finance.models import ExpenseCategory, ExpenseSubcategory, Expense, Cashbox
from finance.serializers import ExpenseCategorySerializer, ExpenseSubcategorySerializer, ExpenseSerializer


@extend_schema_view(
    list=extend_schema(summary="Xarajat kategoriyalari ro'yxati", tags=['Finance - Expenses']),
    create=extend_schema(summary="Yangi xarajat kategoriyasi yaratish", tags=['Finance - Expenses']),
    retrieve=extend_schema(summary="Xarajat kategoriyasi tafsiloti", tags=['Finance - Expenses']),
    update=extend_schema(summary="Xarajat kategoriyasini yangilash", tags=['Finance - Expenses']),
    partial_update=extend_schema(summary="Xarajat kategoriyasini qisman yangilash", tags=['Finance - Expenses']),
    destroy=extend_schema(summary="Xarajat kategoriyasini o'chirish", tags=['Finance - Expenses']),
)
class ExpenseCategoryViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Xarajatlar'
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer


@extend_schema_view(
    list=extend_schema(summary="Xarajat subkategoriyalari ro'yxati", tags=['Finance - Expenses']),
    create=extend_schema(summary="Yangi xarajat subkategoriyasi yaratish", tags=['Finance - Expenses']),
    retrieve=extend_schema(summary="Xarajat subkategoriyasi tafsiloti", tags=['Finance - Expenses']),
    update=extend_schema(summary="Xarajat subkategoriyasini yangilash", tags=['Finance - Expenses']),
    partial_update=extend_schema(summary="Xarajat subkategoriyasini qisman yangilash", tags=['Finance - Expenses']),
    destroy=extend_schema(summary="Xarajat subkategoriyasini o'chirish", tags=['Finance - Expenses']),
)
class ExpenseSubcategoryViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Xarajatlar'
    queryset = ExpenseSubcategory.objects.all()
    serializer_class = ExpenseSubcategorySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['category']


@extend_schema_view(
    list=extend_schema(
        summary="Barcha xarajatlar ro'yxati",
        parameters=[
            OpenApiParameter('start_date', OpenApiTypes.DATE, description="Boshlanish sanasi"),
            OpenApiParameter('end_date', OpenApiTypes.DATE, description="Tugash sanasi"),
            OpenApiParameter('expense_category', OpenApiTypes.INT, description="Kategoriya ID"),
            OpenApiParameter('payment_type', OpenApiTypes.INT, description="Kassa ID"),
            OpenApiParameter('search', OpenApiTypes.STR, description="Izoh bo'yicha qidiruv"),
        ],
        tags=['Finance - Expenses']
    ),
    create=extend_schema(summary="Yangi xarajat yaratish (Kassadan yechish)", tags=['Finance - Expenses']),
    retrieve=extend_schema(summary="Xarajat tafsiloti", tags=['Finance - Expenses']),
    update=extend_schema(summary="Xarajatni to'liq yangilash", tags=['Finance - Expenses']),
    partial_update=extend_schema(summary="Xarajatni qisman yangilash", tags=['Finance - Expenses']),
    destroy=extend_schema(summary="Xarajatni o'chirish", tags=['Finance - Expenses']),
    monthly_summary=extend_schema(
        summary="Oylik xarajatlar xulosasi",
        tags=['Finance - Expenses'],
        responses={200: OpenApiTypes.OBJECT}
    ),
)
class ExpenseViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Xarajatlar'
    queryset = Expense.objects.all().select_related('category', 'subcategory', 'cashbox')
    serializer_class = ExpenseSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['category', 'subcategory', 'cashbox']
    search_fields = ['description']
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()

        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(date__gte=start_date)

        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        category_id = self.request.query_params.get('expense_category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        search_query = self.request.query_params.get('search')
        if search_query:
            queryset = queryset.filter(description__icontains=search_query)

        payment_type = self.request.query_params.get('payment_type')
        if payment_type:
            queryset = queryset.filter(cashbox_id=payment_type)

        return queryset

    def perform_create(self, serializer):
        with db_transaction.atomic():
            user = self.request.user
            org = getattr(user, 'organization', None)

            if not org:
                raise ValidationError({"detail": "Sizda hech qanday tashkilot biriktirilmagan! Tizimga qayta kiring."})

            save_kwargs = {'organization': org}

            branch_id = self.get_branch_id()
            if branch_id:
                try:
                    save_kwargs['branch'] = Branch.objects.get(id=branch_id)
                except Branch.DoesNotExist:
                    pass

            cashbox = serializer.validated_data.get('cashbox')
            amount = serializer.validated_data.get('amount')
            if cashbox and amount:
                cb = Cashbox.objects.select_for_update().get(id=cashbox.id)
                if cb.balance < amount:
                    bal_str = f"{int(cb.balance):,} UZS".replace(",", " ")
                    amt_str = f"{int(amount):,} UZS".replace(",", " ")
                    raise ValidationError({"cashbox": f"Kassada mablag' yetarli emas! Kassadagi joriy balans: {bal_str}. Xarajat summasi: {amt_str}. Kassa balansi manfiyga tushishi taqiqlanadi! ⚠️"})

            serializer.save(**save_kwargs)

    def perform_update(self, serializer):
        with db_transaction.atomic():
            cashbox = serializer.validated_data.get('cashbox') or serializer.instance.cashbox
            amount = serializer.validated_data.get('amount') or serializer.instance.amount
            if cashbox and amount:
                cb = Cashbox.objects.select_for_update().get(id=cashbox.id)
                available = cb.balance + (serializer.instance.amount if serializer.instance.cashbox_id == cb.id else Decimal('0.00'))
                if available < amount:
                    bal_str = f"{int(cb.balance):,} UZS".replace(",", " ")
                    amt_str = f"{int(amount):,} UZS".replace(",", " ")
                    raise ValidationError({"cashbox": f"Kassada mablag' yetarli emas! Kassadagi joriy balans: {bal_str}. Xarajat summasi: {amt_str}. Kassa balansi manfiyga tushishi taqiqlanadi! ⚠️"})
            serializer.save()

    @decorators.action(detail=False, methods=['get'], url_path='monthly-summary')
    def monthly_summary(self, request):
        org_id = getattr(request.user, 'organization_id', None) or self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        expenses = Expense.objects.filter(organization_id=org_id)
        summary = {}
        for exp in expenses:
            if exp.date:
                month_key = exp.date.strftime('%Y-%m')
                summary[month_key] = summary.get(month_key, Decimal('0.00')) + exp.amount

        result = [{"month": k, "total_expense": v} for k, v in sorted(summary.items())]
        return Response(result, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(summary="Batafsil xarajatlar ro'yxati", tags=['Finance - Expenses']),
    retrieve=extend_schema(summary="Batafsil xarajat tafsiloti", tags=['Finance - Expenses']),
    chart_data=extend_schema(
        summary="Xarajatlar grafik ma'lumotlari (Kategoriya va oylar bo'yicha)",
        tags=['Finance - Expenses'],
        responses={200: OpenApiTypes.OBJECT}
    ),
    directors_summary=extend_schema(
        summary="Direktor uchun xarajatlar xulosasi",
        tags=['Finance - Expenses'],
        responses={200: OpenApiTypes.OBJECT}
    ),
)
class DetailedExpenseViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    permission_page_name = 'Xarajatlar'
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer

    @decorators.action(detail=False, methods=['get'], url_path='chart-data')
    def chart_data(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        expenses = Expense.objects.filter(organization_id=org_id)
        by_category = {}
        by_month = {}

        for exp in expenses:
            cat_name = exp.category.name
            month_name = exp.date.strftime('%B %Y')

            by_category[cat_name] = by_category.get(cat_name, Decimal('0.00')) + exp.amount
            by_month[month_name] = by_month.get(month_name, Decimal('0.00')) + exp.amount

        return Response({
            "category_data": [{"category": k, "amount": v} for k, v in by_category.items()],
            "monthly_data": [{"month": k, "amount": v} for k, v in by_month.items()]
        }, status=status.HTTP_200_OK)

    @decorators.action(detail=False, methods=['get'], url_path='directors-summary')
    def directors_summary(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        expenses = Expense.objects.filter(organization_id=org_id)
        total_exp = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        highest_expense = expenses.order_by('-amount').first()
        breakdown = expenses.values('category__name').annotate(total=Sum('amount')).order_by('-total')

        return Response({
            "total_expenses": total_exp,
            "highest_single_expense": {
                "description": highest_expense.description if highest_expense else "",
                "amount": highest_expense.amount if highest_expense else Decimal('0.00'),
                "date": highest_expense.date if highest_expense else None
            },
            "category_breakdown": breakdown
        }, status=status.HTTP_200_OK)
