from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers

from organizations.mixins import TenantViewSetMixin
from academics.models import Course, Group, StudentGroup, Attendance, StudentArchive

User = get_user_model()


class CoursesReportAPIView(TenantViewSetMixin, APIView):
    """Kurslar bo'yicha tahliliy hisobot (/api/v1/academics/reports/courses/)"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Kurslar bo'yicha statistik hisobot",
        description="Har bir kurs bo'yicha faol guruhlar soni, jami talabalar soni va kutilayotgan oylik tushumni (narx * talabalar soni) hisoblab beradi.",
        responses={
            200: inline_serializer(
                name='CourseReportResponse',
                many=True,
                fields={
                    'id': serializers.IntegerField(),
                    'name': serializers.CharField(),
                    'price': serializers.FloatField(),
                    'active_groups_count': serializers.IntegerField(),
                    'students_count': serializers.IntegerField(),
                    'estimated_monthly_revenue': serializers.FloatField(),
                }
            )
        }
    )
    def get(self, request):
        org_id = self.get_organization_id() or getattr(request.user, 'organization_id', None)
        courses = Course.objects.filter(organization_id=org_id)
        report = []
        for c in courses:
            groups = Group.objects.filter(course=c, organization_id=org_id, status='active')
            students_count = StudentGroup.objects.filter(group__course=c, organization_id=org_id).exclude(student__is_archived=True).count()
            report.append({
                "id": c.id,
                "name": c.name,
                "price": float(c.price) if c.price else 0.0,
                "active_groups_count": groups.count(),
                "students_count": students_count,
                "estimated_monthly_revenue": float(c.price or 0) * students_count
            })
        return Response(report, status=status.HTTP_200_OK)


class LeaveReasonsReportAPIView(TenantViewSetMixin, APIView):
    """Ketish sabablari hisoboti (/api/v1/academics/reports/leave-reasons/)"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="O'quvchilarning ketish sabablari tahlili",
        description="Arxivlangan o'quvchilarning kursdan/markazdan ketish sabablari bo'yicha guruhlangan statistikasi va foiz taqsimotini qaytaradi.",
        parameters=[
            OpenApiParameter('start_date', OpenApiTypes.DATE, OpenApiParameter.QUERY, description="Boshlanish sanasi (YYYY-MM-DD)"),
            OpenApiParameter('end_date', OpenApiTypes.DATE, OpenApiParameter.QUERY, description="Tugash sanasi (YYYY-MM-DD)"),
        ],
        responses={
            200: inline_serializer(
                name='LeaveReasonsReportResponse',
                fields={
                    'total_leaves': serializers.IntegerField(),
                    'breakdown': inline_serializer(
                        name='LeaveReasonItem',
                        many=True,
                        fields={
                            'reason': serializers.CharField(),
                            'count': serializers.IntegerField(),
                            'percentage': serializers.FloatField(),
                        }
                    )
                }
            )
        }
    )
    def get(self, request):
        org_id = self.get_organization_id() or getattr(request.user, 'organization_id', None)
        archives = StudentArchive.objects.filter(organization_id=org_id)
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date:
            archives = archives.filter(archived_at__date__gte=start_date)
        if end_date:
            archives = archives.filter(archived_at__date__lte=end_date)

        total_leaves = archives.count()
        breakdown = archives.values('reason').annotate(count=Count('id')).order_by('-count')

        results = []
        for b in breakdown:
            r_name = b['reason'] or "Noma'lum sabab"
            cnt = b['count']
            percent = round((cnt / total_leaves * 100), 1) if total_leaves > 0 else 0.0
            results.append({
                "reason": r_name,
                "count": cnt,
                "percentage": percent
            })

        return Response({
            "total_leaves": total_leaves,
            "breakdown": results
        }, status=status.HTTP_200_OK)


class TeachersReportAPIView(TenantViewSetMixin, APIView):
    """O'qituvchilar hisoboti (/api/v1/academics/reports/teachers/)"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="O'qituvchilar faoliyati hisoboti",
        description="Tashkilotdagi har bir o'qituvchining faol guruhlari, o'quvchilari soni va darslardagi o'rtacha davomat ko'rsatkichini (attendance_rate) qaytaradi.",
        responses={
            200: inline_serializer(
                name='TeacherReportResponse',
                many=True,
                fields={
                    'id': serializers.IntegerField(),
                    'name': serializers.CharField(),
                    'phone': serializers.CharField(),
                    'active_groups_count': serializers.IntegerField(),
                    'students_count': serializers.IntegerField(),
                    'attendance_rate': serializers.FloatField(),
                }
            )
        }
    )
    def get(self, request):
        org_id = self.get_organization_id() or getattr(request.user, 'organization_id', None)
        teachers = User.objects.filter(organization_id=org_id).filter(
            Q(role__iexact='teacher') |
            Q(position__icontains="o'qituvchi") |
            Q(position__icontains="oqituvchi") |
            Q(position__icontains="teacher") |
            Q(position__icontains="ustoz")
        ).exclude(is_superuser=True).distinct()

        report = []
        for t in teachers:
            groups_count = Group.objects.filter(teacher=t, organization_id=org_id, status='active').count()
            students_count = StudentGroup.objects.filter(group__teacher=t, organization_id=org_id).exclude(student__is_archived=True).count()
            atts = Attendance.objects.filter(group__teacher=t, organization_id=org_id)
            total_atts = atts.count()
            present_atts = atts.filter(status__in=['present', 'late']).count()
            att_rate = round((present_atts / total_atts * 100), 1) if total_atts > 0 else 0.0

            report.append({
                "id": t.id,
                "name": t.get_full_name() or t.username,
                "phone": t.phone,
                "active_groups_count": groups_count,
                "students_count": students_count,
                "attendance_rate": att_rate
            })

        return Response(report, status=status.HTTP_200_OK)

