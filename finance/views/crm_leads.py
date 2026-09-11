import os
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from rest_framework import permissions, status, generics, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer, OpenApiParameter

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import HasOrganizationPagePermission
from crm.models import Lead, Pipeline, Source
from crm.serializers import LeadSerializer


class ConversionReportsFunnelView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Konversiya hisoboti'

    @extend_schema(
        summary="Sotuv voronkasi konversiya hisoboti (Funnel Report)",
        description="Sotuv voronkalari bo'yicha lidlar soni, sinov darsiga yozilish, to'lov qilish va bosqichlararo o'tish ko'rsatkichlarini qaytaradi.",
        parameters=[
            OpenApiParameter(name="start_date", type=str, required=False, description="Boshlanish sanasi (YYYY-MM-DD)"),
            OpenApiParameter(name="end_date", type=str, required=False, description="Tugash sanasi (YYYY-MM-DD)"),
            OpenApiParameter(name="marketing", type=int, required=False, description="Marketing kampaniyasi ID"),
            OpenApiParameter(name="course", type=int, required=False, description="Kurs yoki bo'lim ID"),
            OpenApiParameter(name="moderator", type=int, required=False, description="Moderator ID"),
            OpenApiParameter(name="teacher", type=int, required=False, description="O'qituvchi ID"),
            OpenApiParameter(name="source", type=int, required=False, description="Manba ID"),
        ],
        responses={
            200: inline_serializer(
                name="ConversionFunnelReportResponse",
                fields={
                    "table_data": serializers.ListField(child=serializers.DictField()),
                    "funnel_chart": serializers.ListField(child=serializers.DictField()),
                    "linear_chart": serializers.DictField(),
                    "course_chart": serializers.DictField(),
                }
            ),
            400: inline_serializer(name="ConversionFunnelError", fields={"detail": serializers.CharField()}),
        },
        tags=["Finance Conversion Reports"],
    )
    def get(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        marketing_id = request.query_params.get('marketing')
        section_id = request.query_params.get('course')
        moderator_id = request.query_params.get('moderator')
        teacher_id = request.query_params.get('teacher')
        source_id = request.query_params.get('source')

        pipelines = Pipeline.objects.filter(organization_id=org_id).order_by('order')

        if not pipelines.exists():
            return Response({
                "table_data": [],
                "funnel_chart": [],
                "linear_chart": {"labels": [], "total_leads": [], "lost_leads": [], "sales_count": []},
                "course_chart": {"labels": [], "values": []}
            }, status=status.HTTP_200_OK)

        base_filter = Q(organization_id=org_id, is_archived=False)

        if start_date:
            base_filter &= Q(created_at__date__gte=start_date)
        if end_date:
            base_filter &= Q(created_at__date__lte=end_date)
        if marketing_id:
            base_filter &= Q(marketing_id=marketing_id)
        if section_id:
            base_filter &= Q(section_id=section_id)
        if moderator_id:
            base_filter &= Q(moderator_id=moderator_id)
        if teacher_id:
            base_filter &= Q(group__teacher_id=teacher_id)
        if source_id:
            base_filter &= Q(source_id=source_id)

        funnel_chart_data = []
        for pl in pipelines:
            lead_count = Lead.objects.filter(base_filter & Q(pipeline=pl)).count()
            funnel_chart_data.append({
                "pipeline_id": pl.id,
                "pipeline_name": pl.name,
                "total_leads": lead_count
            })

        stats = Lead.objects.filter(base_filter).aggregate(
            total_orders=Count('id'),
            left_before_trial=Count('id', filter=Q(status='LEFT_BEFORE_TRIAL')),
            trial_registered=Count('id', filter=Q(status='TRIAL_REGISTERED')),
            trial_missed=Count('id', filter=Q(status='TRIAL_MISSED')),
            trial_attended=Count('id', filter=Q(status='TRIAL_ATTENDED')),
            converted_to_group=Count('id', filter=Q(status='CONVERTED')),
            first_payment=Count('id', filter=Q(status='PAID')),
            first_payment_left=Count('id', filter=Q(status='PAID_BUT_LEFT')),
            finished=Count('id', filter=Q(status='FINISHED')),
            moved_to_branch=Count('id', filter=Q(status='MOVED_BRANCH')),
        )

        table_data = [
            {"id": 1, "status_name": "Barcha buyurtmalar soni", "count": stats['total_orders']},
            {"id": 2, "status_name": "Buyurtmadan ketganlar", "count": stats['left_before_trial']},
            {"id": 3, "status_name": "Sinov darsiga yozilganlar", "count": stats['trial_registered']},
            {"id": 4, "status_name": "Sinov darsiga kelmay ketganlar", "count": stats['trial_missed']},
            {"id": 5, "status_name": "Sinov darsiga kelganlar", "count": stats['trial_attended']},
            {"id": 6, "status_name": "Sinov darsiga kelib ketganlar", "count": stats['converted_to_group']},
            {"id": 7, "status_name": "Birinchi to'lovni qilganlar", "count": stats['first_payment']},
            {"id": 8, "status_name": "Birinchi to'lovni qibly ketganlar", "count": stats['first_payment_left']},
            {"id": 9, "status_name": "Tugatganlar", "count": stats['finished']},
            {"id": 10, "status_name": "Boshqa filialdan ko'chirilgan", "count": stats['moved_to_branch']},
        ]

        daily_leads = (
            Lead.objects.filter(base_filter)
            .annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(
                total=Count('id'),
                lost=Count('id', filter=Q(status__in=['LEFT_BEFORE_TRIAL', 'TRIAL_MISSED'])),
                sales=Count('id', filter=Q(status='PAID'))
            )
            .order_by('date')
        )

        linear_chart_data = {
            "labels": [str(d['date']) for d in daily_leads],
            "total_leads": [d['total'] for d in daily_leads],
            "lost_leads": [d['lost'] for d in daily_leads],
            "sales_count": [d['sales'] for d in daily_leads]
        }

        course_data = (
            Lead.objects.filter(base_filter & Q(section__isnull=False))
            .values('section__name')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        course_chart_data = {
            "labels": [c['section__name'] for c in course_data],
            "values": [c['count'] for c in course_data]
        }

        return Response({
            "table_data": table_data,
            "funnel_chart": funnel_chart_data,
            "linear_chart": linear_chart_data,
            "course_chart": course_chart_data
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        summary="CRM lidlar ro'yxati (Moliya doirasida)",
        description="Filtrlar (voronka, sana, manba) bo'yicha saralangan CRM lidlari ro'yxati.",
        responses={200: LeadSerializer(many=True)},
        tags=["Finance Conversion Reports"],
    )
)
class CRMLeadsListView(TenantViewSetMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Konversiya hisoboti'
    serializer_class = LeadSerializer

    def get_queryset(self):
        org_id = self.get_organization_id()
        if not org_id:
            return Lead.objects.none()

        pipeline_name = self.request.query_params.get('pipeline_name')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        source_id = self.request.query_params.get('source')

        leads_qs = Lead.objects.filter(organization_id=org_id, is_archived=False)
        branch_id = self.get_branch_id()
        if branch_id:
            leads_qs = leads_qs.filter(Q(branch_id=branch_id) | Q(branch__isnull=True))

        if pipeline_name:
            leads_qs = leads_qs.filter(pipeline__name=pipeline_name)
        if start_date:
            leads_qs = leads_qs.filter(created_at__date__gte=start_date)
        if end_date:
            leads_qs = leads_qs.filter(created_at__date__lte=end_date)
        if source_id:
            leads_qs = leads_qs.filter(source_id=source_id)

        return leads_qs.order_by('-created_at')


class ConversionReportsOverviewView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Konversiya hisoboti'

    @extend_schema(
        summary="Konversiya umumiy ko'rinishi (Overview)",
        description="Konversiya umumiy ko'rsatkichlari.",
        responses={200: inline_serializer(name="ConversionOverviewResponse", fields={"detail": serializers.CharField()})},
        tags=["Finance Conversion Reports"],
    )
    def get(self, request):
        return Response({"detail": "Stub endpoint"}, status=status.HTTP_200_OK)


class ConversionReportsLostReasonsView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Konversiya hisoboti'

    @extend_schema(
        summary="Lidlarni yo'qotish sabablari hisoboti",
        description="Konversiyada mijozlar nima sababdan rad etganligi tahlili.",
        responses={200: inline_serializer(name="ConversionLostReasonsResponse", fields={"detail": serializers.CharField()})},
        tags=["Finance Conversion Reports"],
    )
    def get(self, request):
        return Response({"detail": "Stub endpoint"}, status=status.HTTP_200_OK)


class ConversionReportsPipelineTransitionsView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Konversiya hisoboti'

    @extend_schema(
        summary="Voronka bosqichlari o'tish hisoboti",
        description="Lidlarning bir voronkadan ikkinchisiga o'tish ko'rsatkichlari.",
        responses={200: inline_serializer(name="ConversionPipelineTransitionsResponse", fields={"detail": serializers.CharField()})},
        tags=["Finance Conversion Reports"],
    )
    def get(self, request):
        return Response({"detail": "Stub endpoint"}, status=status.HTTP_200_OK)


class LeadsReportPieChartView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Lidlar hisoboti'

    @extend_schema(
        summary="Lidlar manbalari bo'yicha doiraviy diagramma (Pie Chart)",
        description="Manbalar (Instagram, Telegram, Sayt va h.k.) bo'yicha lidlar taqsimoti diagrammasi.",
        parameters=[
            OpenApiParameter(name="start_date", type=str, required=False, description="Boshlanish sanasi"),
            OpenApiParameter(name="end_date", type=str, required=False, description="Tugash sanasi"),
        ],
        responses={
            200: inline_serializer(
                name="LeadsPieChartResponse",
                many=True,
                fields={
                    "name": serializers.CharField(),
                    "count": serializers.IntegerField(),
                }
            ),
            400: inline_serializer(name="LeadsPieChartError", fields={"detail": serializers.CharField()}),
        },
        tags=["Finance Lead Reports"],
    )
    def get(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        leads_qs = Lead.objects.filter(organization_id=org_id)
        if start_date:
            leads_qs = leads_qs.filter(created_at__date__gte=start_date)
        if end_date:
            leads_qs = leads_qs.filter(created_at__date__lte=end_date)

        sources_data = leads_qs.values('source__name').annotate(count=Count('id'))
        result = []
        for item in sources_data:
            name = item['source__name'] or "Noma'lum"
            result.append({"name": name, "count": item['count']})
        return Response(result, status=status.HTTP_200_OK)


class LeadsReportBarChartView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Lidlar hisoboti'

    @extend_schema(
        summary="Oylik lidlar dinamikasi ustunli diagramma (Bar Chart)",
        description="Oylar kesimida kelib tushgan lidlar dinamikasi.",
        parameters=[
            OpenApiParameter(name="start_date", type=str, required=False, description="Boshlanish sanasi"),
            OpenApiParameter(name="end_date", type=str, required=False, description="Tugash sanasi"),
        ],
        responses={
            200: inline_serializer(
                name="LeadsBarChartResponse",
                many=True,
                fields={
                    "month": serializers.CharField(),
                    "count": serializers.IntegerField(),
                }
            ),
            400: inline_serializer(name="LeadsBarChartError", fields={"detail": serializers.CharField()}),
        },
        tags=["Finance Lead Reports"],
    )
    def get(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        leads_qs = Lead.objects.filter(organization_id=org_id)
        if start_date:
            leads_qs = leads_qs.filter(created_at__date__gte=start_date)
        if end_date:
            leads_qs = leads_qs.filter(created_at__date__lte=end_date)

        monthly_counts = {}
        for lead in leads_qs:
            month_str = lead.created_at.strftime('%Y-%m')
            monthly_counts[month_str] = monthly_counts.get(month_str, 0) + 1

        result = []
        for month in sorted(monthly_counts.keys()):
            result.append({"month": month, "count": monthly_counts[month]})
        return Response(result, status=status.HTTP_200_OK)


class LeadsReportStatisticsView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Lidlar hisoboti'

    @extend_schema(
        summary="Lidlar umumiy soni statistikasi",
        description="Belgilangan davrdagi lidlarning umumiy miqdori.",
        parameters=[
            OpenApiParameter(name="start_date", type=str, required=False, description="Boshlanish sanasi"),
            OpenApiParameter(name="end_date", type=str, required=False, description="Tugash sanasi"),
        ],
        responses={
            200: inline_serializer(
                name="LeadsStatsResponse",
                fields={
                    "total_leads": serializers.IntegerField(),
                    "total_count": serializers.IntegerField(),
                }
            ),
            400: inline_serializer(name="LeadsStatsError", fields={"detail": serializers.CharField()}),
        },
        tags=["Finance Lead Reports"],
    )
    def get(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        leads_qs = Lead.objects.filter(organization_id=org_id)
        if start_date:
            leads_qs = leads_qs.filter(created_at__date__gte=start_date)
        if end_date:
            leads_qs = leads_qs.filter(created_at__date__lte=end_date)

        total_leads = leads_qs.count()
        return Response({
            "total_leads": total_leads,
            "total_count": total_leads
        }, status=status.HTTP_200_OK)


class LeadsReportDetailedView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Lidlar hisoboti'

    @extend_schema(
        summary="Lidlar bo'yicha batafsil analitik hisobot",
        description="Yutilgan, yo'qotilgan, faol lidlar soni, konversiya foizi va manbalar kesimidagi tahlil.",
        parameters=[
            OpenApiParameter(name="start_date", type=str, required=False, description="Boshlanish sanasi"),
            OpenApiParameter(name="end_date", type=str, required=False, description="Tugash sanasi"),
        ],
        responses={
            200: inline_serializer(
                name="LeadsDetailedReportResponse",
                fields={
                    "total_leads": serializers.IntegerField(),
                    "won_leads": serializers.IntegerField(),
                    "lost_leads": serializers.IntegerField(),
                    "active_leads": serializers.IntegerField(),
                    "conversion_rate": serializers.FloatField(),
                    "sources": serializers.ListField(child=serializers.DictField()),
                    "results": serializers.ListField(child=serializers.DictField()),
                }
            ),
            400: inline_serializer(name="LeadsDetailedError", fields={"detail": serializers.CharField()}),
        },
        tags=["Finance Lead Reports"],
    )
    def get(self, request):
        org_id = self.get_organization_id() or getattr(request.user, 'organization_id', None)
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        start_date = request.query_params.get('start_date') or request.query_params.get('from_date')
        end_date = request.query_params.get('end_date') or request.query_params.get('to_date')

        leads_qs = Lead.objects.filter(organization_id=org_id)
        if start_date:
            leads_qs = leads_qs.filter(created_at__date__gte=start_date)
        if end_date:
            leads_qs = leads_qs.filter(created_at__date__lte=end_date)

        total_count = leads_qs.count()
        won_count = leads_qs.filter(status='won').count()
        lost_count = leads_qs.filter(status='lost').count()
        active_count = leads_qs.filter(status__in=['new', 'in_progress', 'contacted']).count()

        sources_summary = []
        for s in Source.objects.filter(organization_id=org_id):
            s_leads = leads_qs.filter(source=s)
            s_count = s_leads.count()
            if s_count > 0:
                s_won = s_leads.filter(status='won').count()
                sources_summary.append({
                    "id": s.id,
                    "name": s.name,
                    "total": s_count,
                    "won": s_won,
                    "conversion_rate": round((s_won / s_count * 100), 1)
                })

        conversion_rate = round((won_count / total_count * 100), 1) if total_count > 0 else 0.0

        return Response({
            "total_leads": total_count,
            "won_leads": won_count,
            "lost_leads": lost_count,
            "active_leads": active_count,
            "conversion_rate": conversion_rate,
            "sources": sources_summary,
            "results": list(leads_qs.values('id', 'name', 'phone', 'status', 'created_at')[:100])
        }, status=status.HTTP_200_OK)


def temp_log_view(request):
    log_path = "/var/log/musojon1995.pythonanywhere.com.error.log"
    if not os.path.exists(log_path):
        return HttpResponse(f"Log path {log_path} not found. Current dirs: {os.listdir('/var') if os.path.exists('/var') else 'No var'}")
    
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()[-150:]
    return HttpResponse("<pre>" + "".join(lines) + "</pre>")
