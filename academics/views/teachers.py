from django.contrib.auth import get_user_model
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions
from drf_spectacular.utils import extend_schema, extend_schema_view

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import IsAdminOrOwnerOrReadOnly
from academics.models import TeacherSalaryPayment
from academics.serializers import TeacherSalaryPaymentSerializer
from accounts.serializers import EmployeeSerializer

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

