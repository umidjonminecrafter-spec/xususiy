import datetime
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import (
    IsAdminOrOwnerOrReadOnly, IsGroupAssignedTeacherForAttendance
)
from academics.models import Attendance, Student, StudentGroup, LeaveReason, Holiday
from academics.serializers import AttendanceSerializer, LeaveReasonSerializer, HolidaySerializer


@extend_schema_view(
    list=extend_schema(
        summary="Davomatlar ro'yxatini olish",
        description="Guruh, talaba va sana oralig'i (date_from, date_to) bo'yicha filtrlangan davomatlar ro'yxatini qaytaradi.",
        parameters=[
            OpenApiParameter('group', OpenApiTypes.INT, description="Guruh ID bo'yicha filter"),
            OpenApiParameter('student', OpenApiTypes.INT, description="Talaba ID bo'yicha filter"),
            OpenApiParameter('date_from', OpenApiTypes.DATE, description="Boshlang'ich sana"),
            OpenApiParameter('date_to', OpenApiTypes.DATE, description="Tugash sanasi"),
        ]
    ),
    create=extend_schema(
        summary="Yangi davomat yozuvi yaratish",
        description="Talabaning darsdagi davomatini belgilaydi. Agar ko'rsatilgan sana bayram/dam olish kuniga to'g'ri kelsa, xatolik qaytaradi."
    ),
    retrieve=extend_schema(
        summary="Davomat tafsilotini olish",
        description="ID bo'yicha bitta davomat yozuvining to'liq ma'lumotlarini (holat, baho, sabab) qaytaradi."
    ),
    update=extend_schema(
        summary="Davomatni to'liq yangilash",
        description="Mavjud davomat yozuvining barcha parametrlarini yangilaydi."
    ),
    partial_update=extend_schema(
        summary="Davomatni qisman yangilash",
        description="Davomat yozuvining ma'lum maydonlarini (masalan, faqat baho yoki status) o'zgartiradi."
    ),
    destroy=extend_schema(
        summary="Davomat yozuvini o'chirish",
        description="Tanlangan davomat yozuvini bazadan o'chiradi."
    ),
)
class AttendanceViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Guruhlar'
    permission_classes = [permissions.IsAuthenticated, IsGroupAssignedTeacherForAttendance]
    queryset = Attendance.objects.select_related('organization', 'branch', 'group', 'student')
    serializer_class = AttendanceSerializer
    pagination_class = None

    def perform_create(self, serializer):
        attendance_date = serializer.validated_data.get('date')
        org_id = self.get_organization_id()

        is_holiday = Holiday.objects.filter(
            organization_id=org_id,
            start_date__lte=attendance_date,
            end_date__gte=attendance_date,
            student_impact=True
        ).exists() or Holiday.objects.filter(
            organization_id=org_id,
            start_date=attendance_date,
            end_date__isnull=True,
            student_impact=True
        ).exists()

        if is_holiday:
            raise ValidationError({
                "detail": f"Ushbu sana ({attendance_date}) dam olish kuni (Bayram) deb e'lon qilingan! Davomat olib bo'lmaydi."
            })

        serializer.save()

    def get_queryset(self):
        queryset = super().get_queryset()
        group_id = self.request.query_params.get('group') or self.request.query_params.get('group_id')
        if group_id:
            queryset = queryset.filter(group_id=group_id)

        student_id = self.request.query_params.get('student') or self.request.query_params.get('student_id')
        if student_id:
            queryset = queryset.filter(student_id=student_id)

        date_from = self.request.query_params.get('date_from') or self.request.query_params.get('start_date')
        if date_from:
            queryset = queryset.filter(date__gte=date_from)

        date_to = self.request.query_params.get('date_to') or self.request.query_params.get('end_date')
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        return queryset


class GroupAttendanceView(TenantViewSetMixin, APIView):
    """
    Guruh davomatlarini boshqarish (olish, saqlash, yangilash, o'chirish).
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Guruhlar'

    def get_serializer_context(self):
        return {'request': self.request}

    @extend_schema(
        summary="Guruh davomatlarini olish",
        description="Guruh ID yoki davomat ID bo'yicha guruhning barcha davomat yozuvlari ro'yxatini qaytaradi.",
        responses={200: AttendanceSerializer(many=True)}
    )
    def get(self, request, group_id):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        if Attendance.objects.filter(id=group_id, organization_id=org_id).exists():
            attendances = Attendance.objects.filter(id=group_id, organization_id=org_id)
        else:
            attendances = Attendance.objects.filter(group_id=group_id, organization_id=org_id)
        serializer = AttendanceSerializer(attendances, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Guruh davomatini saqlash yoki yangilash",
        description="Darsda qatnashgan/qatnashmagan talabalar davomatini va baholarini ommaviy (bulk) yoki yakka tarzda saqlaydi.",
        request=AttendanceSerializer(many=True),
        responses={201: AttendanceSerializer(many=True)}
    )
    def post(self, request, group_id):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        if isinstance(data, dict) and 'id' in data and isinstance(data['id'], dict):
            data = data['id']

        if not isinstance(data, list):
            data = [data]

        attendance_obj = None
        real_group_id = group_id
        if request.method in ('PATCH', 'PUT') and Attendance.objects.filter(id=group_id, organization_id=org_id).exists():
            attendance_obj = Attendance.objects.get(id=group_id, organization_id=org_id)
            real_group_id = attendance_obj.group_id

        created_records = []
        for item in data:
            if attendance_obj:
                student_id = attendance_obj.student_id
                real_group_id = attendance_obj.group_id
            else:
                student_id = item.get('student')
                student_group_id = item.get('student_group')
                if not student_id and student_group_id:
                    sg = StudentGroup.objects.filter(id=student_group_id).first()
                    if sg:
                        student_id = sg.student_id

            if not student_id:
                return Response({"detail": "Student ID is required."}, status=status.HTTP_400_BAD_REQUEST)

            if not Student.objects.filter(id=student_id).exists():
                return Response({
                    "error": "Talaba topilmadi",
                    "detail": f"ID: {student_id} bo'lgan talaba bazada topilmadi. U o'chirilgan bo'lishi mumkin."
                }, status=status.HTTP_400_BAD_REQUEST)

            date = item.get('date') or item.get('lesson_date')
            if isinstance(date, str):
                try:
                    date = datetime.date.fromisoformat(date)
                except ValueError:
                    pass
            if not date:
                if attendance_obj:
                    date = attendance_obj.date
                else:
                    date = timezone.now().date()

            status_val = item.get('status')
            if not status_val:
                is_present = item.get('is_present')
                reason = item.get('reason')
                if is_present is True:
                    status_val = 'present'
                elif is_present is False:
                    if reason:
                        status_val = 'excused'
                    else:
                        status_val = 'absent'
                else:
                    status_val = 'present'

            grade = item.get('grade') or item.get('score') or item.get('points')
            reason_val = item.get('reason') or ""

            if status_val == 'excused' and not str(reason_val).strip():
                raise ValidationError({
                    "reason": "Talaba darsda sababli qatnashmagan bo'lsa, sababini ko'rsatish majburiy!"
                })

            if attendance_obj:
                attendance_obj.date = date
                attendance_obj.status = status_val
                attendance_obj.grade = grade
                attendance_obj.reason = reason_val
                attendance_obj.save()
                attendance = attendance_obj
            else:
                attendance, created = Attendance.objects.update_or_create(
                    organization_id=org_id,
                    group_id=real_group_id,
                    student_id=student_id,
                    date=date,
                    defaults={
                        'status': status_val,
                        'grade': grade,
                        'reason': reason_val
                    }
                )
            created_records.append(attendance)

        serializer = AttendanceSerializer(created_records, many=True)
        if len(serializer.data) == 1 and not isinstance(request.data, list):
            return Response(serializer.data[0], status=status.HTTP_201_CREATED)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Guruh davomatini qisman yangilash",
        description="Guruh davomat yozuvlarini qisman o'zgartiradi.",
        request=AttendanceSerializer(many=True),
        responses={201: AttendanceSerializer(many=True)}
    )
    def patch(self, request, group_id):
        return self.post(request, group_id)

    @extend_schema(
        summary="Guruh davomat yozuvlarini o'chirish",
        description="Ko'rsatilgan guruh, sana yoki talaba bo'yicha davomat yozuvlarini o'chiradi.",
        parameters=[
            OpenApiParameter('date', OpenApiTypes.DATE, description="O'chiriladigan davomat sanasi"),
            OpenApiParameter('student', OpenApiTypes.INT, description="Talaba ID"),
            OpenApiParameter('id', OpenApiTypes.INT, description="Aniq davomat yozuvi ID"),
        ],
        responses={200: inline_serializer(name='AttendanceDeleteResponse', fields={'detail': serializers.CharField()})}
    )
    def delete(self, request, group_id):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        date = request.query_params.get('date')
        student_id = request.query_params.get('student')
        attendance_id = request.query_params.get('id')
        if not attendance_id and isinstance(request.data, dict):
            attendance_id = request.data.get('id') or request.data.get('attendanceId')

        if Attendance.objects.filter(id=group_id, organization_id=org_id).exists():
            count, _ = Attendance.objects.filter(id=group_id, organization_id=org_id).delete()
            return Response({"detail": f"Successfully deleted {count} attendance records."}, status=status.HTTP_200_OK)

        queryset = Attendance.objects.filter(group_id=group_id, organization_id=org_id)
        if attendance_id:
            queryset = queryset.filter(id=attendance_id)
        if date:
            queryset = queryset.filter(date=date)
        if student_id:
            queryset = queryset.filter(student_id=student_id)

        count, _ = queryset.delete()
        return Response({"detail": f"Successfully deleted {count} attendance records."}, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        summary="Guruhdan ketish sabablari ro'yxati",
        description="Talabalarning guruh yoki o'quv markazini tark etish sabablari lug'atini qaytaradi."
    ),
    create=extend_schema(
        summary="Yangi ketish sababini qo'shish",
        description="O'quvchilar guruhdan chiqish sabablari ro'yxatiga yangi sabab nomini kiritadi."
    ),
    retrieve=extend_schema(
        summary="Ketish sababi tafsiloti",
        description="ID bo'yicha ketish sababini ko'rish."
    ),
    update=extend_schema(
        summary="Ketish sababini yangilash",
        description="Ketish sababi ma'lumotlarini o'zgartirish."
    ),
    partial_update=extend_schema(
        summary="Ketish sababini qisman yangilash",
        description="Ketish sababi nomini qisman tahrirlash."
    ),
    destroy=extend_schema(
        summary="Ketish sababini o'chirish",
        description="Ketish sababini ro'yxatdan o'chirish."
    ),
)
class LeaveReasonViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Guruhni tark etganlar'
    queryset = LeaveReason.objects.all()
    serializer_class = LeaveReasonSerializer


@extend_schema_view(
    list=extend_schema(
        summary="Bayram va dam olish kunlari ro'yxati",
        description="O'quv markazi bo'yicha e'lon qilingan barcha rasmiy bayramlar va ta'til kunlarini qaytaradi."
    ),
    create=extend_schema(
        summary="Yangi bayram/dam olish kunini qo'shish",
        description="Kalendarga yangi bayram yoki ta'til sanalarini kiritadi (dars va davomat hisobiga ta'sir qilishi mumkin)."
    ),
    retrieve=extend_schema(
        summary="Bayram tafsilotini olish",
        description="ID bo'yicha bayram kuni ma'lumotlarini ko'rish."
    ),
    update=extend_schema(
        summary="Bayram ma'lumotlarini yangilash",
        description="Bayram sanalari yoki ta'sir doirasini o'zgartirish."
    ),
    partial_update=extend_schema(
        summary="Bayram ma'lumotlarini qisman yangilash",
        description="Bayram nomini yoki sanasini qisman tahrirlash."
    ),
    destroy=extend_schema(
        summary="Bayram kunini o'chirish",
        description="Kiritilgan bayram/dam olish kunini tizimdan o'chirish."
    ),
)
class HolidayViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Ofis sozlamalari'
    queryset = Holiday.objects.all()
    serializer_class = HolidaySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name']
    pagination_class = None
