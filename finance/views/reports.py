import logging

from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import HasOrganizationPagePermission
from finance.serializers import PaymentSerializer, CashTransactionSerializer
from finance.services.reports import (
    get_finance_summary,
    get_advanced_payment_report,
    get_transaction_report,
    get_financial_analytics,
    get_financial_reports_data,
    get_cash_flow_report_data,
    get_pnl_report_data,
    get_employee_finance_balance_report,
    get_revenue_plan_report,
    get_unpaid_lessons_report,
    get_cancelled_payments_report,
    get_discounts_and_bonuses_report,
)
from .base import get_active_branch_id

logger = logging.getLogger(__name__)


@extend_schema(
    tags=['Finance - Reports'],
    summary="Moliya umumiy hisoboti va xulosasi",
    description="Tashkilot va filial bo'yicha umumiy moliyaviy ko'rsatkichlar, kassa qoldiqlari va xulosalarini qaytaradi.",
    responses={200: OpenApiTypes.OBJECT}
)
class FinanceReportView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Moliya'

    def get(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        branch_id = self.get_branch_id()
        data = get_finance_summary(org_id, branch_id)
        return Response(data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Finance - Reports'],
    summary="Kengaytirilgan to'lovlar hisoboti",
    description="To'lovlarni sana oralig'i, kassa, o'qituvchi va qidiruv so'zi bo'yicha filtrlangan ro'yxatini qaytaradi.",
    parameters=[
        OpenApiParameter('start_date', OpenApiTypes.DATE, description="Boshlanish sanasi (YYYY-MM-DD)"),
        OpenApiParameter('end_date', OpenApiTypes.DATE, description="Tugash sanasi (YYYY-MM-DD)"),
        OpenApiParameter('cashbox_id', OpenApiTypes.INT, description="Kassa ID raqami"),
        OpenApiParameter('teacher_id', OpenApiTypes.INT, description="O'qituvchi ID raqami"),
        OpenApiParameter('search', OpenApiTypes.STR, description="Qidiruv so'zi (talaba ismi, telefon)"),
        OpenApiParameter('page', OpenApiTypes.INT, description="Sahifa raqami"),
    ],
    responses={200: PaymentSerializer(many=True)}
)
class AdvancedPaymentReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """To'lovlar uchun o'qituvchi, sana va kassa bo'yicha filter"""
        try:
            org_id = getattr(request.user, 'organization_id', None) or request.query_params.get('org_id')
            branch_id = get_active_branch_id(request)
            start_date = request.query_params.get('start_date') or request.query_params.get('from_date')
            end_date = request.query_params.get('end_date') or request.query_params.get('to_date')
            cashbox_id = request.query_params.get('cashbox_id') or request.query_params.get('cashbox')
            teacher_id = request.query_params.get('teacher_id') or request.query_params.get('teacher')
            search_query = request.query_params.get('search') or request.query_params.get('q')

            queryset = get_advanced_payment_report(
                org_id=org_id,
                branch_id=branch_id,
                start_date=start_date,
                end_date=end_date,
                cashbox_id=cashbox_id,
                teacher_id=teacher_id,
                search_query=search_query
            )

            page = request.query_params.get('page')
            if page:
                paginator = PageNumberPagination()
                paginator.page_size = 20
                paginated_qs = paginator.paginate_queryset(queryset, request)
                serializer = PaymentSerializer(paginated_qs, many=True)
                return paginator.get_paginated_response(serializer.data)

            serializer = PaymentSerializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"AdvancedPaymentReportAPIView xatoligi: {e}")
            return Response({"error": "Hisobotni yuklashda xatolik", "detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Finance - Reports'],
    summary="Moliya va tranzaksiyalar hisoboti jadvali",
    description="Sana, kassa, to'lov usuli va o'qituvchi bo'yicha filtrlangan kassa tranzaksiyalari hisoboti.",
    parameters=[
        OpenApiParameter('cashbox_id', OpenApiTypes.INT, description="Kassa ID"),
        OpenApiParameter('payment_method', OpenApiTypes.STR, description="To'lov turi (CASH, CARD, CLICK, PAYME, va h.k.)"),
        OpenApiParameter('start_date', OpenApiTypes.DATE, description="Boshlanish sanasi"),
        OpenApiParameter('end_date', OpenApiTypes.DATE, description="Tugash sanasi"),
        OpenApiParameter('teacher_id', OpenApiTypes.INT, description="O'qituvchi ID"),
    ],
    responses={200: CashTransactionSerializer(many=True)}
)
class TransactionReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Moliya jadvali va filterlar (Sana, Kassa, O'qituvchi bo'yicha)"""
        branch_id = get_active_branch_id(request)
        cashbox_id = request.query_params.get('cashbox_id')
        payment_method = request.query_params.get('payment_method')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        teacher_id = request.query_params.get('teacher_id')

        queryset = get_transaction_report(
            organization=request.user.organization,
            branch_id=branch_id,
            cashbox_id=cashbox_id,
            payment_method=payment_method,
            start_date=start_date,
            end_date=end_date,
            teacher_id=teacher_id
        )

        serializer = CashTransactionSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)


@extend_schema(
    tags=['Finance - Reports'],
    summary="Moliyaviy tahlil / analitika hisoboti",
    description="Kirim, chiqim va balans dinamikasi bo'yicha davriy tahlil ma'lumotlari.",
    parameters=[
        OpenApiParameter('type', OpenApiTypes.STR, description="Hisobot turi: 'kirim' yoki 'chiqim' (default: kirim)"),
    ],
    responses={200: OpenApiTypes.OBJECT}
)
class FinancialAnalyticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        report_type = request.query_params.get('type', 'kirim')
        branch_id = get_active_branch_id(request)
        org_id = request.user.organization_id

        data = get_financial_analytics(
            organization_id=org_id,
            branch_id=branch_id,
            report_type=report_type,
            get_params=request.GET
        )
        return Response(data)


@extend_schema(
    tags=['Finance - Reports'],
    summary="Moliyaviy hisobotlar majmuasi",
    description="Sana oralig'i va kassa bo'yicha umumiy moliyaviy hisobot ma'lumotlari.",
    parameters=[
        OpenApiParameter('from_date', OpenApiTypes.DATE, description="Boshlanish sanasi"),
        OpenApiParameter('to_date', OpenApiTypes.DATE, description="Tugash sanasi"),
        OpenApiParameter('cashbox', OpenApiTypes.INT, description="Kassa ID"),
    ],
    responses={200: OpenApiTypes.OBJECT}
)
class FinancialReportsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        start_date_str = request.query_params.get('from_date')
        end_date_str = request.query_params.get('to_date')
        cashbox_id = request.query_params.get('kassa') or request.query_params.get('cashbox')

        org_id = getattr(request.user, 'organization_id', None)
        if not org_id and hasattr(request.user, 'organization') and request.user.organization:
            org_id = request.user.organization.id

        branch_id = get_active_branch_id(request)
        data = get_financial_reports_data(
            org_id=org_id,
            branch_id=branch_id,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            cashbox_id=cashbox_id
        )
        return Response(data)


@extend_schema(
    tags=['Finance - Reports'],
    summary="Pul oqimi (Cash Flow) hisoboti",
    description="Kassalar kesimida pul kirimi, chiqimi va qoldig'i bo'yicha Cash Flow hisoboti.",
    parameters=[
        OpenApiParameter('from_date', OpenApiTypes.DATE, description="Boshlanish sanasi"),
        OpenApiParameter('to_date', OpenApiTypes.DATE, description="Tugash sanasi"),
        OpenApiParameter('cashbox', OpenApiTypes.INT, description="Kassa ID"),
    ],
    responses={200: OpenApiTypes.OBJECT}
)
class CashFlowReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        cashbox_id = request.query_params.get('kassa') or request.query_params.get('cashbox')

        org_id = getattr(request.user, 'organization_id', None)
        if not org_id and hasattr(request.user, 'organization') and request.user.organization:
            org_id = request.user.organization.id

        branch_id = get_active_branch_id(request)
        data = get_cash_flow_report_data(
            org_id=org_id,
            branch_id=branch_id,
            from_date=from_date,
            to_date=to_date,
            cashbox_id=cashbox_id
        )
        return Response(data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Finance - Reports'],
    summary="Foyda va Zarar (PnL) hisoboti",
    description="Daromadlar, xarajatlar va sof foyda bo'yicha PnL hisoboti.",
    parameters=[
        OpenApiParameter('from_date', OpenApiTypes.DATE, description="Boshlanish sanasi"),
        OpenApiParameter('to_date', OpenApiTypes.DATE, description="Tugash sanasi"),
    ],
    responses={200: OpenApiTypes.OBJECT}
)
class PnLReportView(APIView):
    """
    Foyda va Zarar (PnL) hisoboti endpointi.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')

        org_id = getattr(request.user, 'organization_id', None)
        if not org_id and hasattr(request.user, 'organization') and request.user.organization:
            org_id = request.user.organization.id

        branch_id = get_active_branch_id(request)
        data = get_pnl_report_data(
            org_id=org_id,
            branch_id=branch_id,
            from_date=from_date,
            to_date=to_date
        )
        return Response(data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Finance - Reports'],
    summary="Xodimlar moliyaviy balansi hisoboti",
    description="Xodimlarga hisoblangan oylik, avans, jarima, bonus va to'lov qoldiqlari balansi.",
    responses={200: OpenApiTypes.OBJECT}
)
class EmployeeFinanceBalanceReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org_id = request.user.organization_id
        branch_id = get_active_branch_id(request)
        data = get_employee_finance_balance_report(org_id=org_id, branch_id=branch_id)
        return Response(data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Finance - Reports'],
    summary="Daromad rejasi (Revenue Plan) hisoboti",
    description="Kunlik, haftalik yoki oylik daromad rejasi va uning bajarilishi ko'rsatkichlari.",
    parameters=[
        OpenApiParameter('date', OpenApiTypes.STR, description="Davr filtri ('Bugun', 'Hafta', 'Oy')"),
    ],
    responses={200: OpenApiTypes.OBJECT}
)
class RevenuePlanReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org_id = request.user.organization_id
        branch_id = get_active_branch_id(request)
        date_str = request.query_params.get('date', 'Bugun')

        data = get_revenue_plan_report(
            org_id=org_id,
            branch_id=branch_id,
            date_str=date_str
        )
        return Response(data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Finance - Reports'],
    summary="To'lanmagan darslar hisoboti",
    description="Talabalar tomonidan qatnashilgan, ammo to'lovi amalga oshirilmagan darslar ro'yxati.",
    responses={200: OpenApiTypes.OBJECT}
)
class UnpaidLessonsReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org_id = request.user.organization_id
        branch_id = get_active_branch_id(request)
        data = get_unpaid_lessons_report(org_id=org_id, branch_id=branch_id)
        return Response(data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Finance - Reports'],
    summary="Bekor qilingan to'lovlar hisoboti",
    description="Bekor qilingan yoki qaytarilgan to'lovlar tarixi va tafsilotlari.",
    responses={200: OpenApiTypes.OBJECT}
)
class CancelledPaymentsReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org_id = request.user.organization_id
        branch_id = get_active_branch_id(request)
        data = get_cancelled_payments_report(org_id=org_id, branch_id=branch_id)
        return Response(data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Finance - Reports'],
    summary="Chegirmalar va bonuslar hisoboti",
    description="Talabalarga berilgan chegirmalar, bonuslar, guruh va kurslar kesimida hisobot.",
    parameters=[
        OpenApiParameter('start_date', OpenApiTypes.DATE, description="Boshlanish sanasi"),
        OpenApiParameter('end_date', OpenApiTypes.DATE, description="Tugash sanasi"),
        OpenApiParameter('search', OpenApiTypes.STR, description="Talaba ismi yoki telefoni bo'yicha qidiruv"),
        OpenApiParameter('group', OpenApiTypes.INT, description="Guruh ID"),
        OpenApiParameter('course', OpenApiTypes.INT, description="Kurs ID"),
    ],
    responses={200: OpenApiTypes.OBJECT}
)
class DiscountsAndBonusesReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org_id = request.user.organization_id
        branch_id = get_active_branch_id(request)
        start_date = request.query_params.get('start_date') or request.query_params.get('from_date')
        end_date = request.query_params.get('end_date') or request.query_params.get('to_date')
        student_search = (
            request.query_params.get('search') or
            request.query_params.get('student') or
            request.query_params.get('student_name') or
            request.query_params.get('name')
        )
        group_id = request.query_params.get('group') or request.query_params.get('group_id')
        course_id = request.query_params.get('course') or request.query_params.get('course_id')

        data = get_discounts_and_bonuses_report(
            org_id=org_id,
            branch_id=branch_id,
            start_date=start_date,
            end_date=end_date,
            student_search=student_search,
            group_id=group_id,
            course_id=course_id
        )
        return Response(data, status=status.HTTP_200_OK)

