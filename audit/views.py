from rest_framework import viewsets, permissions
from drf_spectacular.utils import extend_schema, extend_schema_view
from organizations.mixins import TenantViewSetMixin
from organizations.permissions import IsAdminOrOwnerOrReadOnly
from audit.models import AuditLog
from audit.serializers import AuditLogSerializer


@extend_schema_view(
    list=extend_schema(
        summary="Audit loglari ro'yxati",
        description="Tashkilotda foydalanuvchilar tomonidan amalga oshirilgan barcha harakatlar (yaratish, o'chirish, tahrirlash kabi hodisalar) audit jurnali ro'yxatini qaytaradi."
    ),
    retrieve=extend_schema(
        summary="Audit qaydi tafsiloti",
        description="Tanlangan audit yozuvining batafsil ma'lumotlarini (foydalanuvchi, amal turi, ob'yekt ID va vaqti) qaytaradi."
    ),
)
class AuditLogViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Audit'
    queryset = AuditLog.objects.select_related('user', 'organization').order_by('-timestamp')
    serializer_class = AuditLogSerializer

