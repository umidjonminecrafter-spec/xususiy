from decimal import Decimal
from django.db.models import Sum, Q
from django.contrib.auth import get_user_model
from rest_framework import permissions, status, generics, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import HasOrganizationPagePermission
from academics.models import Student, TeacherSalaryPayment
from academics.serializers import StudentSerializer
from finance.models import TeacherSalaryCalculation

User = get_user_model()


@extend_schema_view(
    get=extend_schema(
        summary="Qarzdor talabalar ro'yxati",
        description="Balansi 0 dan kichik (manfiy) bo'lgan barcha qarzdor talabalar ro'yxatini qaytaradi.",
        responses={200: StudentSerializer(many=True)},
        tags=["Finance Debts"],
    )
)
class StudentDebtsView(TenantViewSetMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Qarzdorlar'
    serializer_class = StudentSerializer

    def get_queryset(self):
        org_id = self.get_organization_id()
        if not org_id:
            return Student.objects.none()
        qs = Student.objects.filter(organization_id=org_id, balance__lt=0)
        branch_id = self.get_branch_id()
        if branch_id:
            qs = qs.filter(Q(branch_id=branch_id) | Q(branch__isnull=True))
        return qs


class StudentDebtsSummaryView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Qarzdorlar'

    @extend_schema(
        summary="Talabalar umumiy qarzdorligi statistikasi",
        description="Barcha qarzdor talabalarning umumiy qarz summasi va qarzdorlar sonini qaytaradi.",
        responses={
            200: inline_serializer(
                name="StudentDebtsSummaryResponse",
                fields={
                    "total_student_debts": serializers.DecimalField(max_digits=14, decimal_places=2),
                    "debtors_count": serializers.IntegerField(),
                }
            ),
            400: inline_serializer(name="StudentDebtsSummaryError", fields={"detail": serializers.CharField()}),
        },
        tags=["Finance Debts"],
    )
    def get(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        branch_id = self.get_branch_id()
        base_filter = Q(organization_id=org_id, balance__lt=0) & ~Q(is_archived=True)
        if branch_id:
            base_filter &= (Q(branch_id=branch_id) | Q(branch__isnull=True))

        total_debt = Student.objects.filter(base_filter).aggregate(total=Sum('balance'))['total'] or Decimal('0.00')
        return Response({
            "total_student_debts": abs(total_debt),
            "debtors_count": Student.objects.filter(base_filter).count()
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        summary="Qarzdor talaba tafsilotlari",
        description="Bitta qarzdor talabaning to'liq profili va balansi.",
        responses={200: StudentSerializer},
        tags=["Finance Debts"],
    )
)
class StudentDebtDetailView(TenantViewSetMixin, generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Qarzdorlar'
    serializer_class = StudentSerializer

    def get_queryset(self):
        org_id = self.get_organization_id()
        qs = Student.objects.filter(organization_id=org_id, balance__lt=0)
        branch_id = self.get_branch_id()
        if branch_id:
            qs = qs.filter(Q(branch_id=branch_id) | Q(branch__isnull=True))
        return qs


class TeacherDebtsView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Qarzdorlar'

    @extend_schema(
        summary="O'qituvchilarga to'lanmagan oylik qarzlari ro'yxati",
        description="Hisoblangan oyligi to'liq to'lab berilmagan har bir o'qituvchi bo'yicha to'lanishi kerak bo'lgan qarzdorlikni qaytaradi.",
        responses={
            200: inline_serializer(
                name="TeacherDebtItemResponse",
                many=True,
                fields={
                    "teacher_id": serializers.IntegerField(),
                    "teacher_name": serializers.CharField(),
                    "total_calculated": serializers.DecimalField(max_digits=12, decimal_places=2),
                    "total_paid": serializers.DecimalField(max_digits=12, decimal_places=2),
                    "outstanding_debt": serializers.DecimalField(max_digits=12, decimal_places=2),
                }
            ),
            400: inline_serializer(name="TeacherDebtsError", fields={"detail": serializers.CharField()}),
        },
        tags=["Finance Debts"],
    )
    def get(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        teachers = User.objects.filter(organization_id=org_id, role='teacher')
        debts = []

        for t in teachers:
            total_calc = TeacherSalaryCalculation.objects.filter(teacher=t).aggregate(total=Sum('calculated_amount'))[
                             'total'] or Decimal('0.00')
            total_paid = TeacherSalaryPayment.objects.filter(teacher=t).aggregate(total=Sum('amount'))[
                             'total'] or Decimal('0.00')

            diff = total_calc - total_paid
            if diff > 0:
                debts.append({
                    "teacher_id": t.id,
                    "teacher_name": t.get_full_name() or t.username,
                    "total_calculated": total_calc,
                    "total_paid": total_paid,
                    "outstanding_debt": diff
                })

        return Response(debts, status=status.HTTP_200_OK)


class TeacherDebtsSummaryView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Qarzdorlar'

    @extend_schema(
        summary="O'qituvchilarga oylik qarzdorligi umumiy xulosasi",
        description="Tashkilotning barcha o'qituvchilarga to'lashi lozim bo'lgan umumiy ish haqi qarzdorligi va oyligi to'lanmagan o'qituvchilar sonini qaytaradi.",
        responses={
            200: inline_serializer(
                name="TeacherDebtsSummaryResponse",
                fields={
                    "total_teacher_debts": serializers.DecimalField(max_digits=14, decimal_places=2),
                    "teachers_in_debt_count": serializers.IntegerField(),
                }
            ),
            400: inline_serializer(name="TeacherDebtsSummaryError", fields={"detail": serializers.CharField()}),
        },
        tags=["Finance Debts"],
    )
    def get(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        teachers = User.objects.filter(organization_id=org_id, role='teacher')
        total_teacher_debt = Decimal('0.00')
        count = 0
        for t in teachers:
            total_calc = TeacherSalaryCalculation.objects.filter(teacher=t).aggregate(total=Sum('calculated_amount'))[
                             'total'] or Decimal('0.00')
            total_paid = TeacherSalaryPayment.objects.filter(teacher=t).aggregate(total=Sum('amount'))[
                             'total'] or Decimal('0.00')
            diff = total_calc - total_paid
            if diff > 0:
                total_teacher_debt += diff
                count += 1

        return Response({
            "total_teacher_debts": total_teacher_debt,
            "teachers_in_debt_count": count
        }, status=status.HTTP_200_OK)


class AllDebtsView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Qarzdorlar'

    @extend_schema(
        summary="Umumiy qarzdorliklar svodkasi (Talabalar + O'qituvchilar)",
        description="O'quv markazining umumiy debitorlik (talabalardan tushishi kerak bo'lgan) va kreditorlik (o'qituvchilarga berilishi kerak bo'lgan oylik) qarzlarini jamlab ko'rsatadi.",
        responses={
            200: inline_serializer(
                name="AllDebtsSummaryResponse",
                fields={
                    "student_debts": serializers.DecimalField(max_digits=14, decimal_places=2),
                    "teacher_debts": serializers.DecimalField(max_digits=14, decimal_places=2),
                    "total_debts": serializers.DecimalField(max_digits=14, decimal_places=2),
                }
            ),
            400: inline_serializer(name="AllDebtsError", fields={"detail": serializers.CharField()}),
        },
        tags=["Finance Debts"],
    )
    def get(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        student_debt = Student.objects.filter(organization_id=org_id, balance__lt=0).aggregate(total=Sum('balance'))[
                           'total'] or Decimal('0.00')
        student_debt_abs = abs(student_debt)

        teachers = User.objects.filter(organization_id=org_id, role='teacher')
        teacher_debt_val = Decimal('0.00')
        for t in teachers:
            total_calc = TeacherSalaryCalculation.objects.filter(teacher=t).aggregate(total=Sum('calculated_amount'))[
                             'total'] or Decimal('0.00')
            total_paid = TeacherSalaryPayment.objects.filter(teacher=t).aggregate(total=Sum('amount'))[
                             'total'] or Decimal('0.00')
            diff = total_calc - total_paid
            if diff > 0:
                teacher_debt_val += diff

        return Response({
            "student_debts": student_debt_abs,
            "teacher_debts": teacher_debt_val,
            "total_debts": student_debt_abs + teacher_debt_val
        }, status=status.HTTP_200_OK)

