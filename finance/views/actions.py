from django.db import transaction as db_transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer

from organizations.mixins import TenantViewSetMixin
from accounts.models import User
from academics.models import Student
from finance.models import Bonus, Fine, FinanceAction, FinanceSetting, Cashbox
from finance.serializers import BonusSerializer, FineSerializer, FinanceActionSerializer, FinanceSettingSerializer
from finance.filters import BonusFilter, FineFilter
from .base import get_active_branch_id


@extend_schema_view(
    list=extend_schema(summary="Xodimlar bonuslari ro'yxati", description="Oylikka qo'shiladigan bonuslar va mukofot pullari ro'yxati.", tags=["Finance Salaries"]),
    retrieve=extend_schema(summary="Bonus tafsiloti", description="Bitta bonus yozuvi tafsilotlari.", tags=["Finance Salaries"]),
    create=extend_schema(summary="Xodimga bonus yozish", description="Xodimga belgilangan sabab bilan yangi bonus tayinlaydi.", tags=["Finance Salaries"]),
    update=extend_schema(summary="Bonusni to'liq yangilash", description="Bonus summasi va sababini to'liq yangilash.", tags=["Finance Salaries"]),
    partial_update=extend_schema(summary="Bonusni qisman yangilash", description="Bonus ma'lumotlarini qisman yangilash.", tags=["Finance Salaries"]),
    destroy=extend_schema(summary="Bonusni o'chirish", description="Bonus yozuvini o'chirish.", tags=["Finance Salaries"]),
)
class BonusViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Ish haqi'
    queryset = Bonus.objects.all().order_by('-id')
    serializer_class = BonusSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = BonusFilter
    search_fields = ['reason', 'employee__first_name', 'employee__last_name']


@extend_schema_view(
    list=extend_schema(summary="Xodimlar jarimalari ro'yxati", description="Oylikdan ushlab qolinadigan jarimalar ro'yxati.", tags=["Finance Salaries"]),
    retrieve=extend_schema(summary="Jarima tafsiloti", description="Bitta jarima yozuvi tafsilotlari.", tags=["Finance Salaries"]),
    create=extend_schema(summary="Xodimga jarima belgilash", description="Xodimga belgilangan sabab bilan yangi jarima yozadi.", tags=["Finance Salaries"]),
    update=extend_schema(summary="Jarimani to'liq yangilash", description="Jarima summasi va sababini to'liq yangilash.", tags=["Finance Salaries"]),
    partial_update=extend_schema(summary="Jarimani qisman yangilash", description="Jarima ma'lumotlarini qisman yangilash.", tags=["Finance Salaries"]),
    destroy=extend_schema(summary="Jarimani o'chirish", description="Jarima yozuvini o'chirish.", tags=["Finance Salaries"]),
)
class FineViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Ish haqi'
    queryset = Fine.objects.all().order_by('-id')
    serializer_class = FineSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = FineFilter
    search_fields = ['reason', 'employee__first_name', 'employee__last_name']


@extend_schema_view(
    list=extend_schema(summary="Moliyaviy amallar (Finance Actions) ro'yxati", description="Tizimdagi moliyaviy avtomatlashtirish amallari jurnali.", tags=["Finance Actions"]),
    retrieve=extend_schema(summary="Moliyaviy amal tafsiloti", description="Bitta moliyaviy amal tafsilotlarini ko'rish.", tags=["Finance Actions"]),
    create=extend_schema(summary="Yangi moliyaviy amal bajarish", description="Kassa va hisoblar o'rtasida yangi moliyaviy amalni amalga oshiradi.", tags=["Finance Actions"]),
    update=extend_schema(summary="Moliyaviy amalni to'liq yangilash", description="Moliyaviy amalni to'liq yangilash.", tags=["Finance Actions"]),
    partial_update=extend_schema(summary="Moliyaviy amalni qisman yangilash", description="Moliyaviy amalni qisman yangilash.", tags=["Finance Actions"]),
    destroy=extend_schema(summary="Moliyaviy amalni o'chirish", description="Moliyaviy amalni o'chirish.", tags=["Finance Actions"]),
)
class FinanceActionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = FinanceAction.objects.all()
    serializer_class = FinanceActionSerializer

    def perform_create(self, serializer):
        with db_transaction.atomic():
            branch_id = self.get_branch_id()
            cashbox_id = self.request.data.get('cashbox')
            
            validated_data = serializer.validated_data.copy()
            validated_data.pop('cashbox', None)
            
            instance = FinanceAction(**validated_data)
            instance.organization = self.request.user.organization
            instance.branch_id = branch_id
            if cashbox_id:
                instance._cashbox_id = cashbox_id
            instance.save()
            serializer.instance = instance

    def perform_update(self, serializer):
        with db_transaction.atomic():
            cashbox_id = self.request.data.get('cashbox')
            instance = serializer.instance
            if cashbox_id:
                instance._cashbox_id = cashbox_id
            serializer.save()


class FinanceSettingAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self):
        setting, created = FinanceSetting.objects.get_or_create(
            organization=self.request.user.organization
        )
        return setting

    def get_response_data(self, setting):
        serializer = FinanceSettingSerializer(setting)
        
        roles_data = [{"id": key, "name": value} for key, value in User.ROLE_CHOICES]
        
        students_data = [
            {"id": s.id, "full_name": s.full_name} 
            for s in Student.objects.filter(organization=setting.organization)
        ]
        
        employees_data = [
            {"id": u.id, "full_name": f"{u.first_name} {u.last_name}".strip() or u.username, "role": u.role} 
            for u in User.objects.filter(organization=setting.organization)
        ]
        
        branch_id = get_active_branch_id(self.request)
        cashboxes_qs = Cashbox.objects.filter(organization=setting.organization, is_archived=False)
        if branch_id:
            cashboxes_qs = cashboxes_qs.filter(branch_id=branch_id)
            
        cashboxes_data = [
            {"id": c.id, "name": c.name} 
            for c in cashboxes_qs
        ]
        
        response_data = dict(serializer.data)
        response_data['choices'] = {
            'roles': roles_data,
            'students': students_data,
            'employees': employees_data,
            'cashboxes': cashboxes_data
        }
        return response_data

    @extend_schema(
        summary="Moliya sozlamalari va tanlov variantlari (Choices)",
        description="Tashkilotning moliya sozlamalari (standart kassa, foizlar, limitlar) va forma uchun kerakli tanlovlar (rollar, talabalar, xodimlar, kassalar)ni qaytaradi.",
        responses={
            200: inline_serializer(
                name="FinanceSettingDetailResponse",
                fields={
                    "id": serializers.IntegerField(),
                    "default_cashbox": serializers.IntegerField(allow_null=True),
                    "choices": serializers.DictField(),
                }
            )
        },
        tags=["Finance Settings"],
    )
    def get(self, request):
        setting = self.get_object()
        return Response(self.get_response_data(setting), status=status.HTTP_200_OK)

    @extend_schema(
        summary="Moliya sozlamalarini yangilash",
        description="Tashkilot moliya sozlamalarini yangilaydi.",
        request=FinanceSettingSerializer,
        responses={
            200: inline_serializer(
                name="FinanceSettingUpdateResponse",
                fields={
                    "id": serializers.IntegerField(),
                    "default_cashbox": serializers.IntegerField(allow_null=True),
                    "choices": serializers.DictField(),
                }
            ),
            400: FinanceSettingSerializer,
        },
        tags=["Finance Settings"],
    )
    def put(self, request):
        setting = self.get_object()
        serializer = FinanceSettingSerializer(setting, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(self.get_response_data(setting), status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

