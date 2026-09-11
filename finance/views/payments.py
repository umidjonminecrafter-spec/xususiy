from decimal import Decimal
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import viewsets, status, decorators
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from django.http import HttpResponse

from organizations.mixins import TenantViewSetMixin
from organizations.models import ReceiptSetting
from academics.models import StudentGroup
from finance.models import MonthlyIncome, Payment, Sale, Expense
from finance.serializers import MonthlyIncomeSerializer, PaymentSerializer, SaleSerializer


@extend_schema_view(
    list=extend_schema(summary="Oylik tushumlar ro'yxati", tags=['Finance - Payments']),
    create=extend_schema(summary="Yangi oylik tushum yozuvi yaratish", tags=['Finance - Payments']),
    retrieve=extend_schema(summary="Oylik tushum tafsiloti", tags=['Finance - Payments']),
    update=extend_schema(summary="Oylik tushumni yangilash", tags=['Finance - Payments']),
    partial_update=extend_schema(summary="Oylik tushumni qisman yangilash", tags=['Finance - Payments']),
    destroy=extend_schema(summary="Oylik tushumni o'chirish", tags=['Finance - Payments']),
    net_profit=extend_schema(
        summary="Oylik sof foyda hisob-kitobi (Tushum - Xarajatlar)",
        tags=['Finance - Payments'],
        responses={200: OpenApiTypes.OBJECT}
    ),
)
class MonthlyIncomeViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Barcha to\'lovlar'
    queryset = MonthlyIncome.objects.all()
    serializer_class = MonthlyIncomeSerializer

    @decorators.action(detail=True, methods=['get'], url_path='net-profit')
    def net_profit(self, request, pk=None):
        income = self.get_object()
        org_id = self.get_organization_id()

        start_date = income.date.replace(day=1)
        if income.date.month == 12:
            end_date = income.date.replace(year=income.date.year + 1, month=1, day=1)
        else:
            end_date = income.date.replace(month=income.date.month + 1, day=1)

        total_expenses = Expense.objects.filter(
            organization_id=org_id,
            date__gte=start_date,
            date__lt=end_date
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        net = income.amount - total_expenses
        return Response({
            "month": income.date.strftime('%Y-%m'),
            "income": income.amount,
            "expenses": total_expenses,
            "net_profit": net
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(summary="Talabalar to'lovlari ro'yxati", tags=['Finance - Payments']),
    create=extend_schema(summary="Talaba to'lovini qabul qilish", tags=['Finance - Payments']),
    retrieve=extend_schema(summary="To'lov tafsilotlari", tags=['Finance - Payments']),
    update=extend_schema(summary="To'lovni yangilash", tags=['Finance - Payments']),
    partial_update=extend_schema(summary="To'lovni qisman yangilash", tags=['Finance - Payments']),
    destroy=extend_schema(summary="To'lovni bekor qilish/o'chirish", tags=['Finance - Payments']),
    receipt=extend_schema(
        summary="To'lov kvitansiyasi (HTML chek chop etish)",
        tags=['Finance - Payments'],
        responses={200: OpenApiTypes.STR}
    ),
)
class PaymentViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Barcha to\'lovlar'
    queryset = Payment.objects.all().select_related('student', 'employee')
    serializer_class = PaymentSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['student', 'payment_method']
    search_fields = ['student__first_name', 'student__last_name', 'comment']

    @decorators.action(detail=True, methods=['get'], url_path='receipt')
    def receipt(self, request, pk=None):
        payment = self.get_object()
        org_id = self.get_organization_id()
        org = payment.organization

        try:
            r_setting = ReceiptSetting.objects.get(organization=org)
        except ReceiptSetting.DoesNotExist:
            r_setting = None

        student = payment.student
        student_name = str(student) if student else "Noma'lum"
        student_phone = getattr(student, 'phone', '-') if student else '-'
        student_balance = f"{int(student.balance):,} UZS" if student else '-'

        employee_name = ''
        if payment.employee:
            employee_name = payment.employee.get_full_name() or payment.employee.username

        group_name = '-'
        if student:
            sg = StudentGroup.objects.filter(student=student, organization_id=org_id).select_related('group').first()
            if sg:
                group_name = sg.group.name

        amount_display = f"{int(payment.amount):,} UZS"
        hide_receipt_number = r_setting.hide_receipt_number if r_setting else False
        hide_org_name = r_setting.hide_organization_name if r_setting else False
        hide_student = r_setting.hide_student_name if r_setting else False
        hide_phone = r_setting.hide_phone_number if r_setting else False
        hide_balance = r_setting.hide_balance if r_setting else False

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Kvitansiya #{payment.id}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Courier New', monospace;
    width: 72mm;
    margin: 0 auto;
    padding: 2mm;
    font-size: 12px;
    color: #000;
  }}
  .center {{ text-align: center; }}
  .bold {{ font-weight: bold; }}
  .divider {{
    border-top: 1px dashed #000;
    margin: 4px 0;
  }}
  .row {{
    display: flex;
    justify-content: space-between;
    padding: 1px 0;
  }}
  .row .label {{ color: #555; }}
  .row .value {{ font-weight: bold; text-align: right; }}
  .amount-row {{
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    font-size: 14px;
    font-weight: bold;
  }}
  .footer {{
    text-align: center;
    margin-top: 8px;
    font-size: 10px;
    color: #777;
  }}
  @media print {{
    body {{ width: 72mm; }}
    @page {{
      size: 80mm auto;
      margin: 0;
    }}
  }}
</style>
</head>
<body>
  {'<h2 class="center bold">' + org.name + '</h2>' if not hide_org_name else ''}
  {'<p class="center" style="margin-bottom:4px;">Kvitansiya №' + str(payment.id) + '</p>' if not hide_receipt_number else ''}
  <div class="divider"></div>

  {'<div class="row"><span class="label">Talaba:</span><span class="value">' + student_name + '</span></div>' if not hide_student else ''}
  {'<div class="row"><span class="label">Telefon:</span><span class="value">' + student_phone + '</span></div>' if not hide_phone else ''}
  <div class="row"><span class="label">Guruh:</span><span class="value">{group_name}</span></div>
  <div class="row"><span class="label">To'lov turi:</span><span class="value">{payment.payment_method}</span></div>
  <div class="row"><span class="label">Sana:</span><span class="value">{payment.date}</span></div>
  <div class="row"><span class="label">Xodim:</span><span class="value">{employee_name}</span></div>

  <div class="divider"></div>

  <div class="amount-row">
    <span>TO'LOV:</span>
    <span>{amount_display}</span>
  </div>

  {'<div class="row"><span class="label">Balans:</span><span class="value">' + student_balance + '</span></div>' if not hide_balance else ''}

  <div class="divider"></div>

  <div class="footer">
    <p>{org.name} &bull; SmartTa'lim</p>
    <p>{payment.date} &bull; #{payment.id}</p>
  </div>

  <script>
    window.onload = function() {{
      window.print();
    }};
  </script>
</body>
</html>"""

        return HttpResponse(html, content_type='text/html; charset=utf-8')


@extend_schema_view(
    list=extend_schema(summary="Sotuvlar / Savdo ro'yxati", tags=['Finance - Payments']),
    retrieve=extend_schema(summary="Sotuv tafsiloti", tags=['Finance - Payments']),
    statistics=extend_schema(
        summary="Sotuvlar umumiy statistikasi (Jami summa, soni, o'rtacha qiymat)",
        tags=['Finance - Payments'],
        responses={200: OpenApiTypes.OBJECT}
    ),
    active_count=extend_schema(
        summary="Joriy oydagi faol sotuvlar soni",
        tags=['Finance - Payments'],
        responses={200: OpenApiTypes.OBJECT}
    ),
)
class SaleViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    permission_page_name = 'Moliya'
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer

    @decorators.action(detail=False, methods=['get'])
    def statistics(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        sales = Sale.objects.filter(organization_id=org_id)
        stats = sales.aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        total = stats['total'] or Decimal('0.00')
        count = stats['count'] or 0
        avg = total / count if count > 0 else Decimal('0.00')

        return Response({
            "total_sales_amount": total,
            "total_sales_count": count,
            "average_sale_value": avg
        }, status=status.HTTP_200_OK)

    @decorators.action(detail=False, methods=['get'], url_path='active-count')
    def active_count(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)
        count = Sale.objects.filter(organization_id=org_id, date__month=timezone.now().date().month).count()
        return Response({"active_sales_count_current_month": count}, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(summary="Mablag'ni qaytarish / yechib olishlar ro'yxati (Manfiy to'lovlar)", tags=['Finance - Payments']),
    create=extend_schema(summary="Mablag'ni yechib olish / qaytarish (Talabaga pul qaytarish)", tags=['Finance - Payments']),
    retrieve=extend_schema(summary="Yechib olish tafsiloti", tags=['Finance - Payments']),
    update=extend_schema(summary="Yechib olishni yangilash", tags=['Finance - Payments']),
    partial_update=extend_schema(summary="Yechib olishni qisman yangilash", tags=['Finance - Payments']),
    destroy=extend_schema(summary="Yechib olish yozuvini o'chirish", tags=['Finance - Payments']),
)
class WithdrawalViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Yechib olish'
    serializer_class = PaymentSerializer
    pagination_class = None

    def get_queryset(self):
        org_id = self.get_organization_id()
        if not org_id:
            return Payment.objects.none()
        qs = Payment.objects.filter(organization_id=org_id, amount__lt=0)
        branch_id = self.get_branch_id()
        if branch_id:
            qs = qs.filter(Q(branch_id=branch_id) | Q(branch__isnull=True))
        return qs

    def perform_create(self, serializer):
        amount = serializer.validated_data.get('amount')
        if amount and amount > 0:
            serializer.validated_data['amount'] = -amount

        serializer.save(organization_id=self.get_organization_id(), branch_id=self.get_branch_id())
