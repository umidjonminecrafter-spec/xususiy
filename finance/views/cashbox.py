from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view

from organizations.mixins import TenantViewSetMixin
from finance.models import Cashbox
from finance.serializers import CashboxSerializer
from .base import get_active_branch_id, sync_cashbox_balance


@extend_schema_view(
    list=extend_schema(summary="Kassalar ro'yxati (ViewSet)", description="Tashkilot va filialga tegishli barcha kassalar (naqd, plastik, bank hisobi) ro'yxatini qaytaradi.", tags=["Finance Cashbox"]),
    retrieve=extend_schema(summary="Kassa tafsiloti", description="Bitta kassaning joriy balansi va sozlamalarini ko'rish.", tags=["Finance Cashbox"]),
    create=extend_schema(summary="Yangi kassa ochish", description="Tashkilot uchun yangi kassa hisobini yaratadi.", tags=["Finance Cashbox"]),
    update=extend_schema(summary="Kassani to'liq yangilash", description="Kassa nomi va sozlamalarini to'liq yangilash.", tags=["Finance Cashbox"]),
    partial_update=extend_schema(summary="Kassani qisman yangilash", description="Kassa parametrlarini qisman yangilash.", tags=["Finance Cashbox"]),
    destroy=extend_schema(summary="Kassani o'chirish", description="Mavjud kassa hisobini o'chirish.", tags=["Finance Cashbox"]),
)
class CashboxViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Moliya'
    queryset = Cashbox.objects.all()
    serializer_class = CashboxSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        for cb in qs:
            sync_cashbox_balance(cb)
        return qs


class CashboxListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="cashbox_list_create_get",
        summary="Faol kassalar ro'yxati (APIView)",
        description="Filial bo'yicha arxivlanmagan faol kassalar ro'yxatini qaytaradi.",
        responses={200: CashboxSerializer(many=True)},
        tags=["Finance Cashbox"],
    )
    def get(self, request):
        org_id = getattr(request.user, 'organization_id', None)
        branch_id = get_active_branch_id(request)
        
        queryset = Cashbox.objects.filter(organization_id=org_id, is_archived=False)
        if branch_id:
            queryset = queryset.filter(branch_id=branch_id)
            
        serializer = CashboxSerializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(
        operation_id="cashbox_list_create_post",
        summary="Yangi kassa yaratish (APIView)",
        description="Joriy filial va tashkilotga yangi kassa qo'shadi.",
        request=CashboxSerializer,
        responses={
            201: CashboxSerializer,
            400: CashboxSerializer,
        },
        tags=["Finance Cashbox"],
    )
    def post(self, request):
        serializer = CashboxSerializer(data=request.data)
        if serializer.is_valid():
            branch_id = get_active_branch_id(request)
            serializer.save(
                organization=request.user.organization,
                branch_id=branch_id
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

