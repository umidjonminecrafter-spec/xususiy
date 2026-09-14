from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import transaction as db_transaction
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import IsAdminOrOwnerOrReadOnly
from academics.models import TeacherSalaryPayment
from academics.serializers import TeacherSalaryPaymentSerializer
from accounts.serializers import EmployeeSerializer
from finance.models import Cashbox, Transaction, TeacherSalaryCalculation

User = get_user_model()


@extend_schema_view(
    list=extend_schema(
        summary="O'qituvchilar ro'yxati",
        description="Tashkilotdagi barcha o'qituvchi lavozimida faoliyat yuritayotgan xodimlarni filtrlangan holda qaytaradi."
    ),
    retrieve=extend_schema(
        summary="O'qituvchi tafsilotlari",
        description="Tanlangan o'qituvchining batafsil xodim profil ma'lumotlarini qaytaradi."
    ),
)
class TeacherViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Faqat o'qituvchilarni qaytaruvchi va boshqaruvchi endpoint (/api/v1/academics/teachers/)"""
    permission_classes = [permissions.IsAuthenticated]
    permission_page_name = 'O\'qituvchilar'
    serializer_class = EmployeeSerializer

    def get_queryset(self):
        return User.objects.filter(
            organization_id=self.get_organization_id()
        ).filter(
            Q(role__iexact='teacher') |
            Q(position__icontains="o'qituvchi") |
            Q(position__icontains="oqituvchi") |
            Q(position__icontains="teacher") |
            Q(position__icontains="ustoz")
        ).exclude(is_superuser=True).distinct()


@extend_schema_view(
    list=extend_schema(
        summary="O'qituvchilar maosh to'lovlari ro'yxati",
        description="O'qituvchilarga to'langan oylik va darsbay ish haqi to'lovlari tarixini qaytaradi."
    ),
    retrieve=extend_schema(
        summary="Maosh to'lovi tafsiloti",
        description="Tanlangan maosh to'lovi yozuvining batafsil ma'lumotlarini qaytaradi."
    ),
    create=extend_schema(
        summary="O'qituvchiga maosh to'lash",
        description="O'qituvchiga ish haqi to'langanligi to'g'risida yangi yozuv yaratadi."
    ),
    update=extend_schema(
        summary="Maosh to'lovini to'liq yangilash",
        description="O'qituvchining maosh to'lovi yozuvini to'liq yangilaydi."
    ),
    partial_update=extend_schema(
        summary="Maosh to'lovini qisman tahrirlash",
        description="O'qituvchining maosh to'lovi yozuvidagi ayrim maydonlarni o'zgartiradi."
    ),
    destroy=extend_schema(
        summary="Maosh to'lovi yozuvini o'chirish",
        description="Noto'g'ri kiritilgan maosh to'lovi yozuvini tizimdan o'chiradi."
    ),
)
class TeacherSalaryPaymentViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Ish haqi'
    queryset = TeacherSalaryPayment.objects.all()
    serializer_class = TeacherSalaryPaymentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['teacher']

    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        org_id = self.get_organization_id() or getattr(request.user, 'organization_id', None)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        with db_transaction.atomic():
            self.perform_create(serializer)
            instance = serializer.instance
            payout_amount = Decimal(str(instance.amount or 0))
            teacher_obj = instance.teacher
            period = instance.period

            cashbox_id = data.get('cashbox') or data.get('cashbox_id')
            if not cashbox_id:
                pm = str(data.get('payment_method') or data.get('payment_type') or '').lower()
                if any(k in pm for k in ['karta', 'card', 'humo', 'uzcard', 'plastik', 'bank']):
                    cb_match = Cashbox.objects.filter(
                        organization_id=org_id,
                        is_archived=False
                    ).filter(
                        Q(name__icontains='karta') | Q(name__icontains='card') | Q(name__icontains='plastik') | Q(name__icontains='bank')
                    ).first()
                    if cb_match:
                        cashbox_id = cb_match.id
                if not cashbox_id:
                    cb_default = Cashbox.objects.filter(organization_id=org_id, is_archived=False).first()
                    if cb_default:
                        cashbox_id = cb_default.id

            cashbox = Cashbox.objects.filter(id=cashbox_id).first() if cashbox_id else None

            if cashbox:
                tx = Transaction.objects.filter(description__endswith=f"(SglID: {instance.id})").first()
                if tx:
                    tx.cashbox = cashbox
                    tx.amount = payout_amount
                    tx.save(update_fields=['cashbox', 'amount'])
                else:
                    Transaction.objects.create(
                        organization_id=org_id,
                        cashbox=cashbox,
                        amount=payout_amount,
                        type='EXPENSE',
                        category='SALARY',
                        employee=teacher_obj,
                        description=f"O'qituvchi maosh to'lovi: {teacher_obj} (SglID: {instance.id})"
                    )

            if org_id and teacher_obj and period:
                calc = TeacherSalaryCalculation.objects.filter(
                    organization_id=org_id,
                    teacher=teacher_obj,
                    period=period
                ).first()
                if calc:
                    curr_paid = Decimal(str(calc.details.get('paid_amount', 0.0))) + payout_amount
                    calc.details['paid_amount'] = float(curr_paid)
                    calc.details['is_paid'] = True
                    calc.save(update_fields=['details'])

            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

