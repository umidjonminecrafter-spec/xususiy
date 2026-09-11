from decimal import Decimal
from datetime import datetime
from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone
from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, status, decorators, exceptions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from organizations.mixins import TenantViewSetMixin
from organizations.permissions import HasOrganizationPagePermission
from organizations.models import Organization
from academics.models import (
    Student, TeacherSalaryPayment
)
from academics.serializers import TeacherSalaryPaymentSerializer
from finance.models import (
    Salary, TeacherSalaryRule, TeacherSalaryCalculation,
    StaffSalaryPercent, Bonus, Fine, Payment, Transaction, Cashbox, FinanceSetting
)
from finance.serializers import (
    SalarySerializer, TeacherSalaryRuleSerializer,
    TeacherSalaryCalculationSerializer, StaffSalaryPercentSerializer
)
from .base import sync_cashbox_balance

User = get_user_model()


@extend_schema_view(
    list=extend_schema(summary="Xodimlar oylik foiz stavkalari ro'yxati", tags=['Finance - Salary']),
    create=extend_schema(summary="Yangi xodim oylik foiz stavkasi biriktirish", tags=['Finance - Salary']),
    retrieve=extend_schema(summary="Xodim oylik foiz stavkasi tafsiloti", tags=['Finance - Salary']),
    update=extend_schema(summary="Oylik foiz stavkasini yangilash", tags=['Finance - Salary']),
    partial_update=extend_schema(summary="Oylik foiz stavkasini qisman yangilash", tags=['Finance - Salary']),
    destroy=extend_schema(summary="Oylik foiz stavkasini o'chirish", tags=['Finance - Salary']),
)
class StaffSalaryPercentViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = StaffSalaryPercentSerializer
    queryset = StaffSalaryPercent.objects.all()

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)


@extend_schema_view(
    list=extend_schema(summary="Xodimlar maoshlari ro'yxati", tags=['Finance - Salary']),
    create=extend_schema(summary="Yangi maosh yozuvi yaratish", tags=['Finance - Salary']),
    retrieve=extend_schema(summary="Maosh tafsiloti", tags=['Finance - Salary']),
    update=extend_schema(summary="Maoshni to'liq yangilash", tags=['Finance - Salary']),
    partial_update=extend_schema(summary="Maoshni qisman yangilash", tags=['Finance - Salary']),
    destroy=extend_schema(summary="Maosh yozuvini o'chirish", tags=['Finance - Salary']),
    calculate=extend_schema(
        summary="Xodimlar oyligini hisoblash",
        description="Tanlangan oy (period) uchun barcha xodimlarning maoshini bonus va jarimalarni inobatga olgan holda hisoblaydi.",
        tags=['Finance - Salary'],
        responses={201: OpenApiTypes.OBJECT}
    ),
    summary=extend_schema(
        summary="Oyliklar xulosasi (To'langan / To'lanmagan)",
        description="Tashkilot bo'yicha jami to'langan va to'lanmagan oyliklar summasi.",
        tags=['Finance - Salary'],
        responses={200: OpenApiTypes.OBJECT}
    ),
)
class SalaryViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Ish haqi'
    queryset = Salary.objects.all().select_related('employee')
    serializer_class = SalarySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['employee', 'status']
    pagination_class = None

    @decorators.action(detail=False, methods=['post'])
    def calculate(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        period = request.data.get('period') or request.data.get('month')
        if not period:
            return Response({"detail": "Period (YYYY-MM) is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            year, month = map(int, period.split('-'))
            calc_date = datetime(year, month, 15).date()
        except ValueError:
            return Response({"detail": "Invalid period format. Use YYYY-MM."}, status=status.HTTP_400_BAD_REQUEST)

        setting = FinanceSetting.objects.filter(organization_id=org_id).first()
        employees = User.objects.filter(organization_id=org_id).exclude(is_superuser=True)
        calculated = []

        for emp in employees:
            bonuses = Bonus.objects.filter(
                employee=emp, date__year=year, date__month=month
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            fines = Fine.objects.filter(
                employee=emp, date__year=year, date__month=month
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

            base_salary = Decimal('0.00')
            if emp.salary_percentage:
                payments_sum = Payment.objects.filter(
                    employee=emp,
                    date__year=year,
                    date__month=month
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
                base_salary = payments_sum * (Decimal(str(emp.salary_percentage.percent)) / Decimal('100.00'))
                base_salary = round(base_salary, 2)
            else:
                base_salary = Decimal('1000.00')
                if emp.role == 'manager':
                    base_salary = Decimal('1500.00')
                elif emp.role == 'admin':
                    base_salary = Decimal('2000.00')

            total_salary = base_salary + bonuses - fines

            if setting and setting.is_count_bonus_enabled:
                active_count = Student.objects.filter(organization_id=org_id, balance__gte=0).count()
                debtor_count = Student.objects.filter(organization_id=org_id, balance__lt=0).count()

                if active_count > 0 and setting.has_money_students_amount > 0:
                    total_salary += Decimal(str(setting.has_money_students_amount))
                if debtor_count == 0 and setting.debtor_students_amount > 0:
                    total_salary += Decimal(str(setting.debtor_students_amount))

            if setting and setting.kpi_settings:
                target_revenue = Decimal(str(setting.kpi_settings.get('target_revenue', '0.00')))
                kpi_bonus = Decimal(str(setting.kpi_settings.get('kpi_bonus', '0.00')))
                if target_revenue > 0 and kpi_bonus > 0:
                    total_revenue = Payment.objects.filter(
                        organization_id=org_id,
                        date__year=year,
                        date__month=month
                    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
                    if total_revenue >= target_revenue:
                        total_salary += kpi_bonus

            sal, created = Salary.objects.update_or_create(
                organization_id=org_id,
                employee=emp,
                date=calc_date,
                defaults={'amount': total_salary, 'status': 'unpaid'}
            )
            calculated.append(sal)

        return Response({
            "detail": f"Salaries calculated successfully for {len(calculated)} employees.",
            "period": period
        }, status=status.HTTP_201_CREATED)

    @decorators.action(detail=False, methods=['get'])
    def summary(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        salaries = Salary.objects.filter(organization_id=org_id)
        paid = salaries.filter(status='paid').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        unpaid = salaries.filter(status='unpaid').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        return Response({
            "total_paid": paid,
            "total_unpaid": unpaid,
            "total_calculated": paid + unpaid
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(summary="O'qituvchilar maosh stavka qoidalari ro'yxati", tags=['Finance - Salary']),
    create=extend_schema(summary="Yangi maosh qoidasi yaratish", tags=['Finance - Salary']),
    retrieve=extend_schema(summary="Maosh qoidasi tafsiloti", tags=['Finance - Salary']),
    update=extend_schema(summary="Maosh qoidasini yangilash", tags=['Finance - Salary']),
    partial_update=extend_schema(summary="Maosh qoidasini qisman yangilash", tags=['Finance - Salary']),
    destroy=extend_schema(summary="Maosh qoidasini o'chirish", tags=['Finance - Salary']),
    bulk_create=extend_schema(
        summary="O'qituvchilar maosh qoidalarini ommaviy yaratish",
        description="Bir nechta o'qituvchi uchun oylik stavka qoidalarini bir vaqtda yaratish.",
        tags=['Finance - Salary'],
        responses={201: TeacherSalaryRuleSerializer(many=True)}
    ),
    get_by_period=extend_schema(
        summary="Davr bo'yicha maosh qoidalarini olish",
        parameters=[OpenApiParameter('period', OpenApiTypes.STR, description="Davr (YYYY-MM)")],
        tags=['Finance - Salary'],
        responses={200: TeacherSalaryRuleSerializer(many=True)}
    ),
    configure_period=extend_schema(
        summary="Davr qoidalarini boshqa davrdan nusxalash (Configure Period)",
        description="Oldingi oydagi barcha oylik qoidalarini yangi oyga ko'chirish.",
        tags=['Finance - Salary'],
        responses={201: OpenApiTypes.OBJECT}
    ),
    active_periods=extend_schema(
        summary="Mavjud faol davrlar ro'yxati",
        tags=['Finance - Salary'],
        responses={200: OpenApiTypes.OBJECT}
    ),
    period_summary=extend_schema(
        summary="Davr bo'yicha qoidalar statistikasi",
        parameters=[OpenApiParameter('period', OpenApiTypes.STR, description="Davr (YYYY-MM)")],
        tags=['Finance - Salary'],
        responses={200: OpenApiTypes.OBJECT}
    ),
)
class TeacherSalaryRuleViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Ish haqi'
    queryset = TeacherSalaryRule.objects.all()
    serializer_class = TeacherSalaryRuleSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['teacher', 'is_active']

    def perform_create(self, serializer):
        org_id = self.get_organization_id()
        if not org_id:
            raise exceptions.ValidationError({"detail": "Organization context is required."})

        branch_id = self.get_branch_id()
        instance = serializer.save(organization_id=org_id, branch_id=branch_id)

        override_all = self.request.data.get('override_all')
        if override_all is True or str(override_all).lower() == 'true':
            if instance.teacher is None:
                TeacherSalaryRule.objects.filter(
                    organization_id=org_id,
                    period=instance.period,
                    teacher__isnull=False
                ).delete()

    def perform_update(self, serializer):
        instance = serializer.save()

        override_all = self.request.data.get('override_all')
        if override_all is True or str(override_all).lower() == 'true':
            if instance.teacher is None:
                org_id = self.get_organization_id()
                TeacherSalaryRule.objects.filter(
                    organization_id=org_id,
                    period=instance.period,
                    teacher__isnull=False
                ).delete()

    @decorators.action(detail=False, methods=['post'], url_path='bulk-create')
    def bulk_create(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        rules_data = request.data.get('rules', [])
        created_rules = []
        for r_data in rules_data:
            teacher_id = r_data.get('teacher')
            rule_type = r_data.get('rule_type')
            rate = r_data.get('rate')
            period = r_data.get('period', '2026-05')

            rule = TeacherSalaryRule.objects.create(
                organization_id=org_id,
                branch_id=self.get_branch_id(),
                teacher_id=teacher_id,
                rule_type=rule_type,
                rate=Decimal(str(rate)),
                period=period,
                is_active=True
            )
            created_rules.append(rule)

        return Response(TeacherSalaryRuleSerializer(created_rules, many=True).data, status=status.HTTP_201_CREATED)

    @decorators.action(detail=False, methods=['get'], url_path='get-by-period')
    def get_by_period(self, request):
        org_id = self.get_organization_id() or getattr(request.user, 'organization_id', None)
        period = request.query_params.get('period') or timezone.now().strftime('%Y-%m')
        if not org_id:
            return Response({"detail": "Organization context is required."},
                            status=status.HTTP_400_BAD_REQUEST)

        rules = TeacherSalaryRule.objects.filter(organization_id=org_id, period=period)
        if not rules.exists():
            rules = TeacherSalaryRule.objects.filter(organization_id=org_id, is_active=True)
        return Response(TeacherSalaryRuleSerializer(rules, many=True).data, status=status.HTTP_200_OK)

    @decorators.action(detail=False, methods=['post'], url_path='configure-period')
    def configure_period(self, request):
        org_id = self.get_organization_id()
        source_period = request.data.get('source_period')
        target_period = request.data.get('target_period')

        if not org_id or not source_period or not target_period:
            return Response({"detail": "org_id, source_period, and target_period are required."},
                            status=status.HTTP_400_BAD_REQUEST)

        source_rules = TeacherSalaryRule.objects.filter(organization_id=org_id, period=source_period)
        copied = []
        for rule in source_rules:
            new_rule = TeacherSalaryRule.objects.create(
                organization_id=org_id,
                branch_id=self.get_branch_id(),
                teacher=rule.teacher,
                rule_type=rule.rule_type,
                rate=rule.rate,
                period=target_period,
                is_active=True
            )
            copied.append(new_rule)

        return Response({
            "detail": f"Successfully configured period {target_period} by copying {len(copied)} rules from {source_period}."
        }, status=status.HTTP_201_CREATED)

    @decorators.action(detail=False, methods=['get'], url_path='active-periods')
    def active_periods(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        periods = TeacherSalaryRule.objects.filter(organization_id=org_id).values_list('period', flat=True).distinct()
        return Response(list(periods), status=status.HTTP_200_OK)

    @decorators.action(detail=False, methods=['get'], url_path='period-summary')
    def period_summary(self, request):
        org_id = self.get_organization_id() or getattr(request.user, 'organization_id', None)
        period = request.query_params.get('period') or timezone.now().strftime('%Y-%m')
        if not org_id:
            return Response({"detail": "Organization context is required."},
                            status=status.HTTP_400_BAD_REQUEST)

        rules = TeacherSalaryRule.objects.filter(organization_id=org_id, period=period)
        if not rules.exists():
            rules = TeacherSalaryRule.objects.filter(organization_id=org_id, is_active=True)

        count = rules.count()
        avg_rate = rules.aggregate(avg=Sum('rate'))['avg'] or Decimal('0.00')
        if count > 0:
            avg_rate = avg_rate / count

        return Response({
            "period": period,
            "total_rules": count,
            "average_rate": avg_rate
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(summary="O'qituvchilar hisoblangan maoshlari ro'yxati", tags=['Finance - Salary']),
    retrieve=extend_schema(summary="Hisoblangan maosh tafsiloti", tags=['Finance - Salary']),
    update=extend_schema(summary="Hisoblangan maoshni yangilash", tags=['Finance - Salary']),
    partial_update=extend_schema(summary="Hisoblangan maoshni qisman yangilash", tags=['Finance - Salary']),
    destroy=extend_schema(summary="Hisoblangan maoshni o'chirish", tags=['Finance - Salary']),
    create=extend_schema(
        summary="O'qituvchiga maosh to'lash (Kassadan yechish)",
        description="O'qituvchiga qoldiq ish haqi bo'yicha to'lov qilish va kassadan chiqim tranzaksiyasini yaratish.",
        tags=['Finance - Salary'],
        responses={201: OpenApiTypes.OBJECT}
    ),
    monthly_report=extend_schema(
        summary="Oylik maoshlar hisoboti (O'qituvchilar kesimida)",
        parameters=[OpenApiParameter('period', OpenApiTypes.STR, description="Davr (YYYY-MM)")],
        tags=['Finance - Salary'],
        responses={200: OpenApiTypes.OBJECT}
    ),
)
class TeacherSalaryCalculationViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Ish haqi'
    queryset = TeacherSalaryCalculation.objects.all()
    serializer_class = TeacherSalaryCalculationSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['teacher', 'period']

    @decorators.action(detail=False, methods=['get'], url_path='monthly-report')
    def monthly_report(self, request):
        org_id = self.get_organization_id() or getattr(request.user, 'organization_id', None)
        period = request.query_params.get('period') or timezone.now().strftime('%Y-%m')
        if not org_id:
            return Response({"detail": "Organization context is required."},
                            status=status.HTTP_400_BAD_REQUEST)

        calcs = TeacherSalaryCalculation.objects.filter(organization_id=org_id, period=period)
        total_payout = calcs.aggregate(total=Sum('calculated_amount'))['total'] or Decimal('0.00')

        return Response({
            "period": period,
            "total_calculated_payout": total_payout,
            "teachers_count": calcs.count(),
            "calculations": TeacherSalaryCalculationSerializer(calcs, many=True).data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        org_id = self.get_organization_id()
        cashbox_id = request.data.get('cashbox') or request.data.get('cashbox_id')
        if not cashbox_id:
            return Response({
                "detail": "Oylik to'lash uchun kassa tanlanishi shart!",
                "cashbox": "Oylik to'lash uchun kassa tanlanishi shart!"
            }, status=status.HTTP_400_BAD_REQUEST)

        cashbox = Cashbox.objects.filter(id=cashbox_id, organization_id=org_id).first()
        if not cashbox:
            cashbox = Cashbox.objects.filter(id=cashbox_id).first()
        if not cashbox:
            return Response({
                "detail": "Tanlangan kassa topilmadi.",
                "cashbox": "Tanlangan kassa topilmadi."
            }, status=status.HTTP_404_NOT_FOUND)

        teachers_payload = request.data.get('teachers')
        teacher_id = request.data.get('teacher') or request.data.get('teacher_id')
        calc_id = request.data.get('id') or request.data.get('calculation_id')
        period = request.data.get('period') or '2026-07'

        teachers_list = []
        if isinstance(teachers_payload, list):
            teachers_list = teachers_payload
        elif teachers_payload:
            teachers_list = [teachers_payload]
        elif teacher_id:
            teachers_list = [teacher_id]

        if calc_id:
            calc = TeacherSalaryCalculation.objects.filter(id=calc_id).first()
            if calc:
                teachers_list = [calc.teacher_id]

        if not teachers_list:
            teacher_id_attr = request.data.get('teacher')
            if teacher_id_attr:
                teachers_list = [teacher_id_attr]

        if not teachers_list:
            return super().create(request, *args, **kwargs)

        created_payments = []

        with db_transaction.atomic():
            for t_id in teachers_list:
                teacher_obj = User.objects.filter(id=t_id).first()
                if not teacher_obj:
                    continue

                calc = TeacherSalaryCalculation.objects.filter(
                    organization_id=org_id,
                    teacher=teacher_obj,
                    period=period
                ).first()

                net_unpaid = Decimal('0.00')
                if calc:
                    serializer = TeacherSalaryCalculationSerializer(calc)
                    rep = serializer.data
                    net_unpaid = Decimal(str(rep.get('to_lanmagan') or rep.get('net_salary') or rep.get('final_payout') or 0))

                available_to_pay = net_unpaid

                payout_amount = Decimal('0.00')
                req_amount = request.data.get('amount')
                if req_amount is not None:
                    try:
                        payout_amount = Decimal(str(req_amount))
                    except (ValueError, TypeError):
                        payout_amount = Decimal('0.00')

                if payout_amount <= 0:
                    payout_amount = available_to_pay

                if available_to_pay <= 0:
                    teacher_name = f"{teacher_obj.first_name} {teacher_obj.last_name or ''}".strip()
                    paid_str = ""
                    if calc:
                        serializer = TeacherSalaryCalculationSerializer(calc)
                        p_val = serializer.data.get('to_langan') or 0
                        if p_val > 0:
                            paid_str = f" (Ushbu davr uchun {int(p_val):,} UZS allaqachon to'langan)".replace(",", " ")
                    return Response({
                        "detail": f"{teacher_name} uchun to'lanishi kerak bo'lgan ish haqi qoldig'i mavjud emas (0 UZS).{paid_str}",
                        "error": "To'lanmagan ish haqi mavjud emas"
                    }, status=status.HTTP_400_BAD_REQUEST)

                if payout_amount > available_to_pay:
                    p_str = f"{int(payout_amount):,} UZS".replace(",", " ")
                    u_str = f"{int(available_to_pay):,} UZS".replace(",", " ")
                    return Response({
                        "detail": f"To'lov summasi ({p_str}) to'lanmagan ish haqi qoldig'idan ({u_str}) ko'p bo'lishi mumkin emas!",
                        "error": "To'lov summasi qoldiqdan ko'p"
                    }, status=status.HTTP_400_BAD_REQUEST)

                cb_balance = Decimal(str(cashbox.balance or 0))
                if cb_balance < payout_amount:
                    bal_str = f"{int(cb_balance):,} UZS".replace(",", " ")
                    payout_str = f"{int(payout_amount):,} UZS".replace(",", " ")
                    return Response({
                        "detail": f"Kassada mablag' yetarli emas! Kassadagi joriy balans: {bal_str}. To'lanadigan oylik: {payout_str}",
                        "cashbox": f"Kassada mablag' yetarli emas! (Joriy balans: {bal_str})"
                    }, status=status.HTTP_400_BAD_REQUEST)

                org_obj = Organization.objects.filter(id=org_id).first() if org_id else cashbox.organization
                
                try:
                    pyear, pmonth = map(int, period.split('-'))
                    now_dt = timezone.now()
                    if pyear == now_dt.year and pmonth == now_dt.month:
                        pdate = now_dt
                    else:
                        import datetime as dt_module
                        pdate = dt_module.datetime(pyear, pmonth, 1, 12, 0, tzinfo=timezone.utc)
                except Exception:
                    pdate = timezone.now()

                payment = TeacherSalaryPayment.objects.create(
                    organization=org_obj,
                    teacher=teacher_obj,
                    amount=payout_amount,
                    period=period,
                    paid_at=pdate
                )

                tx = Transaction.objects.filter(
                    organization=org_obj,
                    description__endswith=f"(SglID: {payment.id})"
                ).first()
                if tx:
                    tx.cashbox = cashbox
                    tx.amount = payout_amount
                    tx.save()
                else:
                    Transaction.objects.create(
                        organization=org_obj,
                        cashbox=cashbox,
                        amount=payout_amount,
                        type='EXPENSE',
                        category='SALARY',
                        employee=teacher_obj,
                        description=f"O'qituvchi maosh to'lovi: {teacher_obj} (SglID: {payment.id})"
                    )

                sync_cashbox_balance(cashbox)

                if calc:
                    current_paid = Decimal(str(calc.details.get('paid_amount', 0.0))) + payout_amount
                    calc.details['paid_amount'] = float(current_paid)
                    if payout_amount >= available_to_pay:
                        calc.details['is_paid'] = True
                    calc.save(update_fields=['details'])

                created_payments.append({
                    "id": payment.id,
                    "teacher": teacher_obj.get_full_name() or teacher_obj.username,
                    "amount": float(payout_amount),
                    "cashbox": cashbox.name
                })

        return Response({
            "detail": f"O'qituvchiga oylik to'landi va {cashbox.name} kassasidan yechildi.",
            "payments": created_payments
        }, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=['Finance - Salary'],
    summary="O'qituvchilar maoshini hisoblash (Oylik / Darslar bo'yicha)",
    description="Berilgan davr (period) bo'yicha o'qituvchilarning dars soatlari yoki foiz stavkalariga ko'ra oyligini hisoblaydi yoki nollaydi.",
    parameters=[
        OpenApiParameter('period', OpenApiTypes.STR, description="Davr (YYYY-MM)"),
        OpenApiParameter('reset', OpenApiTypes.BOOL, description="Agar true bo'lsa hisob-kitoblarni 0 ga tushiradi"),
    ],
    request=OpenApiTypes.OBJECT,
    responses={201: OpenApiTypes.OBJECT, 200: OpenApiTypes.OBJECT}
)
class TeacherSalaryCalculateView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Ish haqi'

    def post(self, request):
        from finance.services.salary import calculate_teacher_salaries, reset_teacher_salary_calculations
        org_id = self.get_organization_id()
        period = request.data.get('period') or request.data.get('month') or request.query_params.get('period') or request.query_params.get('month')
        is_reset = request.data.get('reset') or request.query_params.get('reset')

        if not org_id or not period:
            return Response({"detail": "org_id and period are required in payload."},
                            status=status.HTTP_400_BAD_REQUEST)

        if is_reset:
            calcs = reset_teacher_salary_calculations(org_id, period)
            return Response({
                "detail": f"Teacher salary calculations reset to 0 UZS for period {period}.",
                "period": period,
                "results": TeacherSalaryCalculationSerializer(calcs, many=True).data
            }, status=status.HTTP_200_OK)

        try:
            calcs = calculate_teacher_salaries(org_id, period)
        except ValueError:
            return Response({"detail": "Invalid period format. Use YYYY-MM."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "detail": f"Teacher salaries calculated successfully for {len(calcs)} teachers.",
            "period": period,
            "results": TeacherSalaryCalculationSerializer(calcs, many=True).data
        }, status=status.HTTP_201_CREATED)



@extend_schema_view(
    list=extend_schema(summary="O'qituvchilarga to'langan oyliklar ro'yxati", tags=['Finance - Salary']),
    create=extend_schema(summary="O'qituvchiga oylik to'lovi yozish", tags=['Finance - Salary']),
    retrieve=extend_schema(summary="O'qituvchi oylik to'lovi tafsiloti", tags=['Finance - Salary']),
    update=extend_schema(summary="Oylik to'lovini yangilash", tags=['Finance - Salary']),
    partial_update=extend_schema(summary="Oylik to'lovini qisman yangilash", tags=['Finance - Salary']),
    destroy=extend_schema(summary="Oylik to'lovini o'chirish", tags=['Finance - Salary']),
    summary=extend_schema(
        summary="O'qituvchilar oylik to'lovlari umumiy xulosasi",
        tags=['Finance - Salary'],
        responses={200: OpenApiTypes.OBJECT}
    ),
)
class TeacherSalaryPaymentsView(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Ish haqi'
    queryset = TeacherSalaryPayment.objects.all()
    serializer_class = TeacherSalaryPaymentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['teacher']

    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        calc_id = data.get('calculation_id') or data.get('calculation')
        calc_obj = None
        if calc_id:
            calc_obj = TeacherSalaryCalculation.objects.filter(id=calc_id).first()
            if calc_obj:
                if not data.get('teacher'):
                    data['teacher'] = calc_obj.teacher_id
                if not data.get('period'):
                    data['period'] = calc_obj.period

        if not data.get('period'):
            data['period'] = '2026-09'

        cashbox_id = data.get('cashbox') or data.get('cashbox_id')
        amount = data.get('amount')
        org_id = self.get_organization_id() or getattr(request.user, 'organization_id', None)

        if not cashbox_id:
            cb_default = Cashbox.objects.filter(organization_id=org_id).first()
            if cb_default:
                cashbox_id = cb_default.id
                data['cashbox'] = cb_default.id

        cashbox = None
        if cashbox_id:
            cashbox = Cashbox.objects.filter(id=cashbox_id).first()

        if not cashbox:
            return Response({
                "detail": "Oylik to'lash uchun kassa tanlanishi shart!",
                "cashbox": "Oylik to'lash uchun kassa tanlanishi shart!"
            }, status=status.HTTP_400_BAD_REQUEST)

        payout_amount = Decimal('0.00')
        if amount is not None:
            try:
                payout_amount = Decimal(str(amount))
                if Decimal(str(cashbox.balance or 0)) < payout_amount:
                    bal_str = f"{int(cashbox.balance):,} UZS".replace(",", " ")
                    payout_str = f"{int(payout_amount):,} UZS".replace(",", " ")
                    return Response({
                        "detail": f"Kassada mablag' yetarli emas! Kassadagi joriy balans: {bal_str}. To'lanadigan oylik: {payout_str}",
                        "cashbox": f"Kassada mablag' yetarli emas! (Joriy balans: {bal_str})"
                    }, status=status.HTTP_400_BAD_REQUEST)
            except (ValueError, TypeError):
                return Response({"detail": "Noto'g'ri summa kiritildi."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        with db_transaction.atomic():
            self.perform_create(serializer)
            instance = serializer.instance
            payment_id = instance.id
            teacher_id = data.get('teacher') or getattr(instance, 'teacher_id', None)
            period = data.get('period') or getattr(instance, 'period', '2026-09')

            teacher_obj = User.objects.filter(id=teacher_id).first() if teacher_id else None

            tx = None
            if payment_id:
                tx = Transaction.objects.filter(description__endswith=f"(SglID: {payment_id})").first()

            if tx:
                tx.cashbox = cashbox
                tx.amount = payout_amount
                tx.save(update_fields=['cashbox', 'amount'])
            else:
                sgl_tag = f" (SglID: {payment_id})" if payment_id else ""
                Transaction.objects.create(
                    organization_id=org_id,
                    cashbox=cashbox,
                    amount=payout_amount,
                    type='EXPENSE',
                    category='SALARY',
                    employee=teacher_obj,
                    description=f"O'qituvchi maosh to'lovi: {teacher_obj}{sgl_tag}"
                )

            sync_cashbox_balance(cashbox)

            calc = calc_obj
            if not calc and teacher_id and period:
                calc = TeacherSalaryCalculation.objects.filter(
                    organization_id=org_id,
                    teacher_id=teacher_id,
                    period=period
                ).first()
            if calc:
                curr_paid = Decimal(str(calc.details.get('paid_amount', 0.0))) + payout_amount
                calc.details['paid_amount'] = float(curr_paid)
                calc.details['is_paid'] = True
                calc.save(update_fields=['details'])

            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @decorators.action(detail=False, methods=['get'])
    def summary(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        payments = TeacherSalaryPayment.objects.filter(organization_id=org_id)
        total = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        count = payments.count()
        return Response({
            "total_salary_paid": total,
            "payments_count": count
        }, status=status.HTTP_200_OK)
