from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_date
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, inline_serializer
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import IsAdminOrOwnerOrReadOnly
from .models import KPITemplate, KPIGoal, KPISubGoal, KPILog
from .serializers import KPITemplateSerializer, KPIGoalSerializer, KPISubGoalSerializer, KPILogSerializer

User = get_user_model()


@extend_schema_view(
    list=extend_schema(summary="KPI andozalari (shablonlari) ro'yxati", tags=['KPI - Settings & Goals']),
    create=extend_schema(summary="Yangi KPI andozasi yaratish", tags=['KPI - Settings & Goals']),
    retrieve=extend_schema(summary="KPI andozasi tafsiloti", tags=['KPI - Settings & Goals']),
    update=extend_schema(summary="KPI andozasini to'liq yangilash", tags=['KPI - Settings & Goals']),
    partial_update=extend_schema(summary="KPI andozasini qisman yangilash", tags=['KPI - Settings & Goals']),
    destroy=extend_schema(summary="KPI andozasini o'chirish", tags=['KPI - Settings & Goals']),
)
class KPITemplateViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Sozlamalar'
    queryset = KPITemplate.objects.all()
    serializer_class = KPITemplateSerializer


@extend_schema_view(
    list=extend_schema(summary="Xodimlarga biriktirilgan KPI maqsadlari ro'yxati", tags=['KPI - Settings & Goals']),
    create=extend_schema(summary="Yangi KPI maqsadi yaratish", tags=['KPI - Settings & Goals']),
    retrieve=extend_schema(summary="KPI maqsadi tafsiloti va progressi", tags=['KPI - Settings & Goals']),
    update=extend_schema(summary="KPI maqsadini to'liq yangilash", tags=['KPI - Settings & Goals']),
    partial_update=extend_schema(summary="KPI maqsadini qisman yangilash", tags=['KPI - Settings & Goals']),
    destroy=extend_schema(summary="KPI maqsadini o'chirish", tags=['KPI - Settings & Goals']),
    assign_template=extend_schema(
        summary="KPI andozasini bir nechta xodimga ommaviy biriktirish",
        description="Tanlangan KPI andozasi va davr (boshlanish/tugash sanasi) bo'yicha ko'rsatilgan xodimlarga avtomatik KPI va uning quyi maqsadlarini yaratadi.",
        tags=['KPI - Settings & Goals'],
        request=inline_serializer(
            name='AssignKPITemplateRequest',
            fields={
                'template_id': serializers.IntegerField(help_text="KPI andozasi ID raqami"),
                'employee_ids': serializers.ListField(child=serializers.IntegerField(), help_text="Xodimlar ID lari ro'yxati"),
                'start_date': serializers.DateField(help_text="Boshlanish sanasi (YYYY-MM-DD)"),
                'end_date': serializers.DateField(help_text="Tugash sanasi (YYYY-MM-DD)"),
                'name': serializers.CharField(help_text="KPI maqsad nomi (masalan: 'Avgust 2026 KPI')"),
            }
        ),
        responses={201: KPIGoalSerializer(many=True)}
    ),
)
class KPIGoalViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Sozlamalar'
    queryset = KPIGoal.objects.all()
    serializer_class = KPIGoalSerializer

    @action(detail=False, methods=['post'], url_path='assign-template')
    @transaction.atomic
    def assign_template(self, request):
        """
        Mass-assign a KPI Template to employees for a specific period.
        """
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        template_id = request.data.get('template_id')
        employee_ids = request.data.get('employee_ids', [])
        start_date_str = request.data.get('start_date')
        end_date_str = request.data.get('end_date')
        goal_name = request.data.get('name')

        if not template_id or not employee_ids or not start_date_str or not end_date_str or not goal_name:
            return Response({"detail": "template_id, employee_ids, start_date, end_date, and name are required fields."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            template = KPITemplate.objects.get(id=template_id, organization_id=org_id)
        except KPITemplate.DoesNotExist:
            return Response({"detail": "KPI Template not found in this organization."}, status=status.HTTP_404_NOT_FOUND)

        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)
        if not start_date or not end_date:
            return Response({"detail": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        created_goals = []
        for emp_id in employee_ids:
            try:
                employee = User.objects.get(id=emp_id, organization_id=org_id)
            except User.DoesNotExist:
                continue

            # Create the main goal
            goal = KPIGoal.objects.create(
                organization_id=org_id,
                employee=employee,
                name=goal_name,
                start_date=start_date,
                end_date=end_date
            )

            # Create sub-goals from config
            for sub_config in template.sub_goals_config:
                KPISubGoal.objects.create(
                    organization_id=org_id,
                    parent_goal=goal,
                    name=sub_config.get('name', 'Noma\'lum'),
                    metric_type=sub_config.get('metric_type', 'manual'),
                    system_event=sub_config.get('system_event'),
                    target_value=sub_config.get('target_value', 1.00),
                    weight=sub_config.get('weight', 0.00)
                )

            # Recalculate progress initially
            goal.calculate_progress()
            created_goals.append(goal)

        serializer = KPIGoalSerializer(created_goals, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(summary="KPI quyi maqsadlari (Sub-goals) ro'yxati", tags=['KPI - Settings & Goals']),
    create=extend_schema(summary="Yangi KPI quyi maqsadi yaratish", tags=['KPI - Settings & Goals']),
    retrieve=extend_schema(summary="KPI quyi maqsadi tafsiloti", tags=['KPI - Settings & Goals']),
    update=extend_schema(summary="KPI quyi maqsadini yangilash (manual progress)", tags=['KPI - Settings & Goals']),
    partial_update=extend_schema(summary="KPI quyi maqsadini qisman yangilash", tags=['KPI - Settings & Goals']),
    destroy=extend_schema(summary="KPI quyi maqsadini o'chirish", tags=['KPI - Settings & Goals']),
)
class KPISubGoalViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Sozlamalar'
    queryset = KPISubGoal.objects.all()
    serializer_class = KPISubGoalSerializer


@extend_schema_view(
    list=extend_schema(summary="KPI bajarilish loglari (tarixi) ro'yxati", tags=['KPI - Settings & Goals']),
    retrieve=extend_schema(summary="KPI log yozuvi tafsiloti", tags=['KPI - Settings & Goals']),
)
class KPILogViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Sozlamalar'
    queryset = KPILog.objects.all()
    serializer_class = KPILogSerializer

