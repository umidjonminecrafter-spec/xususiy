from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, status, decorators
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import SearchFilter
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import IsAdminOrOwnerOrReadOnly
from academics.models import (
    LessonSchedule, LessonTime, OnlineLesson, Homework, GroupLesson, Group, Attendance, generate_group_lessons
)
from academics.serializers import (
    LessonScheduleSerializer, LessonTimeSerializer, OnlineLessonSerializer,
    HomeworkSerializer, SetLessonTopicSerializer, RescheduleLessonSerializer,
    GroupLessonListSerializer
)


@extend_schema_view(
    list=extend_schema(
        summary="Dars jadvallari ro'yxatini olish",
        description="Guruhlar, o'qituvchilar va kunlar bo'yicha shakllangan dars jadvallari ro'yxatini qaytaradi.",
        parameters=[
            OpenApiParameter('type', OpenApiTypes.STR, description="Jadval turi ('juft' yoki 'toq')"),
        ]
    ),
    create=extend_schema(
        summary="Yangi dars jadvali yaratish",
        description="Guruh va o'qituvchi uchun haftalik dars vaqtini kiritadi."
    ),
    retrieve=extend_schema(
        summary="Dars jadvali tafsiloti",
        description="ID bo'yicha dars jadvalini ko'rish."
    ),
    update=extend_schema(
        summary="Dars jadvalini to'liq yangilash",
        description="Dars vaqtlari yoki xona ma'lumotlarini yangilash."
    ),
    partial_update=extend_schema(
        summary="Dars jadvalini qisman yangilash",
        description="Dars jadvali parametrlarini qisman tahrirlash."
    ),
    destroy=extend_schema(
        summary="Dars jadvalini o'chirish",
        description="Dars jadvali yozuvini bazadan o'chirish."
    ),
)
class LessonScheduleViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    queryset = LessonSchedule.objects.all()
    serializer_class = LessonScheduleSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['group', 'teacher', 'day_type']

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'group', 'group__course', 'teacher'
        )
        schedule_type = self.request.query_params.get('type')
        if schedule_type == 'juft':
            queryset = queryset.filter(day_type='even')
        elif schedule_type == 'toq':
            queryset = queryset.filter(day_type='odd')
        return queryset


@extend_schema_view(
    list=extend_schema(
        summary="Dars vaqtlari (smenalar) ro'yxati",
        description="O'quv markazidagi standart dars vaqtlari (masalan: 09:00-10:30, 14:00-15:30) ro'yxatini qaytaradi."
    ),
    create=extend_schema(
        summary="Yangi dars vaqti qo'shish",
        description="Standart dars boshlanish va tugash vaqtini kiritadi."
    ),
    retrieve=extend_schema(
        summary="Dars vaqti tafsiloti",
        description="ID bo'yicha dars vaqtini ko'rish."
    ),
    update=extend_schema(
        summary="Dars vaqtini yangilash",
        description="Dars vaqti parametrlarini o'zgartirish."
    ),
    partial_update=extend_schema(
        summary="Dars vaqtini qisman yangilash",
        description="Dars vaqtini qisman tahrirlash."
    ),
    destroy=extend_schema(
        summary="Dars vaqtini o'chirish",
        description="Dars vaqti slotini o'chirish."
    ),
)
class LessonTimeViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Darslar hisoboti'
    queryset = LessonTime.objects.all()
    serializer_class = LessonTimeSerializer


@extend_schema_view(
    list=extend_schema(
        summary="Onlayn darslar ro'yxati",
        description="Guruhlar bo'yicha biriktirilgan video darsliklar va onlayn materiallar ro'yxatini qaytaradi."
    ),
    create=extend_schema(
        summary="Yangi onlayn dars qo'shish",
        description="Guruh uchun yangi video darslik yoki havola joylaydi."
    ),
    retrieve=extend_schema(
        summary="Onlayn dars tafsiloti",
        description="ID bo'yicha onlayn dars ma'lumotlarini olish."
    ),
    update=extend_schema(
        summary="Onlayn darsni yangilash",
        description="Onlayn dars sarlavhasi yoki videosini yangilash."
    ),
    partial_update=extend_schema(
        summary="Onlayn darsni qisman yangilash",
        description="Onlayn darsni qisman tahrirlash."
    ),
    destroy=extend_schema(
        summary="Onlayn darsni o'chirish",
        description="Onlayn darsni o'chirish."
    ),
)
class OnlineLessonViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Darslar hisoboti'
    queryset = OnlineLesson.objects.all().select_related('group', 'group__course')
    serializer_class = OnlineLessonSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['group', 'is_published']
    search_fields = ['title']
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        current_user = getattr(self.request, 'user', None)
        if current_user and getattr(current_user, 'role', None) == 'student':
            phone = getattr(current_user, 'phone', None) or getattr(current_user, 'username', None)
            if phone:
                qs = qs.filter(
                    group__group_students__student__phone=phone,
                    is_published=True
                ).distinct()
            else:
                return qs.none()

        group_id = self.request.query_params.get('group') or self.request.query_params.get('group_id')
        if group_id:
            qs = qs.filter(group_id=group_id)

        attendance_date = self.request.query_params.get('attendance_date') or self.request.query_params.get('date')
        if attendance_date:
            qs = qs.filter(attendance_date=attendance_date)

        is_published = self.request.query_params.get('is_published')
        if is_published is not None:
            if str(is_published).lower() in ['true', '1']:
                qs = qs.filter(is_published=True)
            elif str(is_published).lower() in ['false', '0']:
                qs = qs.filter(is_published=False)

        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    @extend_schema(
        summary="Onlayn darsni e'lon qilish (Publish)",
        description="Onlayn darsni o'quvchilarga ko'rinadigan qilib faollashtiradi (`is_published=True`).",
        responses={200: inline_serializer(name='OnlineLessonPublishResponse', fields={'status': serializers.CharField(), 'detail': serializers.CharField()})}
    )
    @decorators.action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        lesson = self.get_object()
        lesson.is_published = True
        lesson.save()
        return Response({"status": "success", "detail": "Lesson published."}, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Onlayn darsni bekor qilish (Unpublish)",
        description="Onlayn darsni o'quvchilarga ko'rinmaydigan qilib yashiradi (`is_published=False`).",
        responses={200: inline_serializer(name='OnlineLessonUnpublishResponse', fields={'status': serializers.CharField(), 'detail': serializers.CharField()})}
    )
    @decorators.action(detail=True, methods=['post'], url_path='unpublish')
    def unpublish(self, request, pk=None):
        lesson = self.get_object()
        lesson.is_published = False
        lesson.save()
        return Response({"status": "success", "detail": "Lesson unpublished."}, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        summary="Uy vazifalari ro'yxati",
        description="Guruhlar bo'yicha berilgan barcha uy vazifalari va topshiriqlar ro'yxatini qaytaradi."
    ),
    create=extend_schema(
        summary="Yangi uy vazifasi yaratish",
        description="Guruh o'quvchilari uchun yangi uy vazifasi matni va topshirig'ini kiritadi."
    ),
    retrieve=extend_schema(
        summary="Uy vazifasi tafsiloti",
        description="ID bo'yicha uy vazifasi ma'lumotlarini olish."
    ),
    update=extend_schema(
        summary="Uy vazifasini yangilash",
        description="Uy vazifasi matni va muddatini tahrirlash."
    ),
    partial_update=extend_schema(
        summary="Uy vazifasini qisman yangilash",
        description="Uy vazifasi parametrlarini qisman o'zgartirish."
    ),
    destroy=extend_schema(
        summary="Uy vazifasini o'chirish",
        description="Uy vazifasini tizimdan o'chirish."
    ),
)
class HomeworkViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    permission_page_name = 'Guruhlar'
    queryset = Homework.objects.select_related('group', 'created_by').all()
    serializer_class = HomeworkSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['title', 'text', 'group__name']
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        group_id = self.request.query_params.get('group') or self.request.query_params.get('group_id')
        if group_id:
            queryset = queryset.filter(group_id=group_id)

        current_user = getattr(self.request, 'user', None)
        if current_user and getattr(current_user, 'role', None) == 'student':
            phone = getattr(current_user, 'phone', None) or getattr(current_user, 'username', None)
            if phone:
                queryset = queryset.filter(group__group_students__student__phone=phone).distinct()
            else:
                queryset = queryset.none()
        return queryset

    def perform_create(self, serializer):
        current_user = getattr(self.request, 'user', None)
        if current_user and getattr(current_user, 'role', None) == 'student':
            raise PermissionDenied("Talaba uy vazifasi qo'sha olmaydi.")
        org_id = self.get_organization_id()
        if not org_id:
            raise PermissionDenied("Organization context is required.")

        branch_id = self.get_branch_id()
        serializer.save(
            organization_id=org_id,
            branch_id=branch_id,
            created_by=self.request.user if self.request.user.is_authenticated else None
        )

    def update(self, request, *args, **kwargs):
        if getattr(request.user, 'role', None) == 'student':
            raise PermissionDenied("Talaba uy vazifasini o'zgartira olmaydi.")
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if getattr(request.user, 'role', None) == 'student':
            raise PermissionDenied("Talaba uy vazifasini o'zgartira olmaydi.")
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if getattr(request.user, 'role', None) == 'student':
            raise PermissionDenied("Talaba uy vazifasini o'chira olmaydi.")
        return super().destroy(request, *args, **kwargs)


class SetLessonTopicAPIView(APIView):
    @extend_schema(
        summary="Dars mavzusini o'rnatish",
        description="Muayyan guruh darsi ID bo'yicha dars mavzusi sarlavhasini (`title`) dars taqvimiga kiritadi yoki yangilaydi.",
        parameters=[
            OpenApiParameter('lesson_id', OpenApiTypes.INT, location=OpenApiParameter.PATH, description="Dars ID raqami")
        ],
        request=SetLessonTopicSerializer,
        responses={
            200: inline_serializer(
                name='SetLessonTopicSuccessResponse',
                fields={
                    'success': serializers.BooleanField(),
                    'message': serializers.CharField(),
                    'data': serializers.DictField()
                }
            ),
            400: inline_serializer(name='SetLessonTopicErrorResponse', fields={'title': serializers.ListField(child=serializers.CharField())}),
            404: inline_serializer(name='SetLessonTopicNotFoundResponse', fields={'error': serializers.CharField()})
        }
    )
    def post(self, request, lesson_id):
        try:
            lesson = GroupLesson.objects.get(id=lesson_id)
        except GroupLesson.DoesNotExist:
            return Response({"error": "Dars kuni topilmadi!"}, status=status.HTTP_404_NOT_FOUND)

        serializer = SetLessonTopicSerializer(lesson, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "success": True,
                "message": "Mavzu dars kalendariga qo'shildi!",
                "data": serializer.data
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CancelOrRestoreLessonAPIView(APIView):
    @extend_schema(
        summary="Darsni bekor qilish yoki tiklash",
        description="Dars ID bo'yicha dars holatini o'zgartiradi (`is_canceled` holatini almashtiradi). O'tib ketgan darslarni bekor qilish taqiqlanadi.",
        request=None,
        parameters=[
            OpenApiParameter('lesson_id', OpenApiTypes.INT, location=OpenApiParameter.PATH, description="Dars ID raqami")
        ],
        responses={
            200: inline_serializer(
                name='CancelOrRestoreLessonResponse',
                fields={
                    'success': serializers.BooleanField(),
                    'is_canceled': serializers.BooleanField(),
                    'message': serializers.CharField()
                }
            ),
            400: inline_serializer(name='CancelOrRestoreLessonError', fields={'error': serializers.CharField()}),
            404: inline_serializer(name='CancelOrRestoreLessonNotFound', fields={'error': serializers.CharField()})
        }
    )
    def post(self, request, lesson_id):
        try:
            lesson = GroupLesson.objects.get(id=lesson_id)
        except GroupLesson.DoesNotExist:
            return Response({"error": "Dars topilmadi!"}, status=status.HTTP_404_NOT_FOUND)

        today = timezone.now().date()
        if lesson.date < today:
            return Response({"error": "O'tib ketgan darsni bekor qilib bo'lmaydi!"}, status=status.HTTP_400_BAD_REQUEST)

        lesson.is_canceled = not lesson.is_canceled
        lesson.save()
        return Response({
            "success": True,
            "is_canceled": lesson.is_canceled,
            "message": "Dars holati o'zgardi!"
        }, status=status.HTTP_200_OK)


class RescheduleLessonAPIView(APIView):
    @extend_schema(
        summary="Dars sanasini boshqa kunga ko'chirish",
        description="Kelgusi dars sanasini yangi kiritilgan sanaga ko'chiradi va asl sanani `original_date` sifatida saqlaydi.",
        parameters=[
            OpenApiParameter('lesson_id', OpenApiTypes.INT, location=OpenApiParameter.PATH, description="Dars ID raqami")
        ],
        request=RescheduleLessonSerializer,
        responses={
            200: inline_serializer(
                name='RescheduleLessonResponse',
                fields={
                    'success': serializers.BooleanField(),
                    'current_date': serializers.DateField(),
                    'original_date': serializers.DateField(allow_null=True)
                }
            ),
            400: inline_serializer(name='RescheduleLessonError', fields={'error': serializers.CharField()}),
            404: inline_serializer(name='RescheduleLessonNotFound', fields={'error': serializers.CharField()})
        }
    )
    def post(self, request, lesson_id):
        try:
            lesson = GroupLesson.objects.get(id=lesson_id)
        except GroupLesson.DoesNotExist:
            return Response({"error": "Dars topilmadi!"}, status=status.HTTP_404_NOT_FOUND)

        today = timezone.now().date()
        if lesson.date < today:
            return Response({"error": "O'tib ketgan darsni ko'chirish mumkin emas!"},
                            status=status.HTTP_400_BAD_REQUEST)

        serializer = RescheduleLessonSerializer(data=request.data)
        if serializer.is_valid():
            new_date = serializer.validated_data['new_date']
            if not lesson.original_date:
                lesson.original_date = lesson.date
            lesson.date = new_date
            lesson.save()

            return Response({
                "success": True,
                "current_date": lesson.date,
                "original_date": lesson.original_date
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Guruh darslari ro'yxati (Taqvim bo'yicha)",
    description="Guruh ID bo'yicha guruhning barcha dars kunlari va mavzularini qaytaradi. Agar darslar generatsiya qilinmagan bo'lsa, avtomatik generatsiya qiladi.",
    parameters=[
        OpenApiParameter('group', OpenApiTypes.INT, required=True, description="Guruh ID raqami"),
        OpenApiParameter('start_date', OpenApiTypes.DATE, description="Boshlang'ich sana"),
        OpenApiParameter('end_date', OpenApiTypes.DATE, description="Tugash sanasi"),
    ]
)
class GroupLessonListAPIView(ListAPIView):
    serializer_class = GroupLessonListSerializer
    pagination_class = None

    def get_queryset(self):
        group_id = self.request.query_params.get('group')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')

        if not group_id:
            return GroupLesson.objects.none()

        if not GroupLesson.objects.filter(group_id=group_id).exists():
            try:
                group = Group.objects.get(id=group_id)
                generate_group_lessons(group)
            except Group.DoesNotExist:
                return GroupLesson.objects.none()

        queryset = GroupLesson.objects.filter(group_id=group_id)
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        return queryset.order_by('date')


class LessonCalendarAPIView(APIView):
    """Darslar kalendari endpointi (/api/v1/academics/lessons/calendar/)"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="O'quv markazi darslar kalendari",
        description="Guruh, o'qituvchi, xona va sana oralig'i bo'yicha o'quv markazining umumiy dars taqvimini qaytaradi.",
        parameters=[
            OpenApiParameter('group', OpenApiTypes.INT, description="Guruh ID bo'yicha filter"),
            OpenApiParameter('teacher', OpenApiTypes.INT, description="O'qituvchi ID bo'yicha filter"),
            OpenApiParameter('room', OpenApiTypes.INT, description="Xona ID bo'yicha filter"),
            OpenApiParameter('start_date', OpenApiTypes.DATE, description="Boshlang'ich sana"),
            OpenApiParameter('end_date', OpenApiTypes.DATE, description="Tugash sanasi"),
        ],
        responses={200: GroupLessonListSerializer(many=True)}
    )
    def get(self, request):
        org_id = getattr(request.user, 'organization_id', None)
        qs = GroupLesson.objects.filter(group__organization_id=org_id).select_related(
            'group', 'group__teacher', 'group__room', 'group__course'
        )

        group_id = request.query_params.get('group') or request.query_params.get('group_id')
        teacher_id = request.query_params.get('teacher') or request.query_params.get('teacher_id')
        room_id = request.query_params.get('room') or request.query_params.get('room_id')
        start_date = request.query_params.get('start_date') or request.query_params.get('from_date')
        end_date = request.query_params.get('end_date') or request.query_params.get('to_date')

        if group_id and str(group_id).isdigit():
            qs = qs.filter(group_id=int(group_id))
        if teacher_id and str(teacher_id).isdigit():
            qs = qs.filter(group__teacher_id=int(teacher_id))
        if room_id and str(room_id).isdigit():
            qs = qs.filter(group__room_id=int(room_id))
        if start_date:
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)

        serializer = GroupLessonListSerializer(qs.order_by('date')[:500], many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class LessonStatisticsAPIView(APIView):
    """Dars davomat statistikasi (/api/v1/academics/lessons/{id}/statistics/)"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Dars davomat statistikasi",
        description="Tanlangan dars ID bo'yicha qatnashganlar, kelmaganlar, sababli qatnashmaganlar soni va umumiy qatnashish foizini hisoblab qaytaradi.",
        parameters=[
            OpenApiParameter('lesson_id', OpenApiTypes.INT, location=OpenApiParameter.PATH, description="Dars ID raqami")
        ],
        responses={
            200: inline_serializer(
                name='LessonStatisticsResponse',
                fields={
                    'lesson_id': serializers.IntegerField(),
                    'group_name': serializers.CharField(),
                    'date': serializers.CharField(),
                    'topic': serializers.CharField(),
                    'enrolled_count': serializers.IntegerField(),
                    'present_count': serializers.IntegerField(),
                    'late_count': serializers.IntegerField(),
                    'absent_count': serializers.IntegerField(),
                    'excused_count': serializers.IntegerField(),
                    'attended_total': serializers.IntegerField(),
                    'attendance_rate': serializers.FloatField(),
                }
            ),
            404: inline_serializer(name='LessonStatisticsNotFound', fields={'error': serializers.CharField()})
        }
    )
    def get(self, request, lesson_id=None):
        lesson = GroupLesson.objects.filter(id=lesson_id).select_related('group').first()
        if not lesson:
            return Response({"error": "Dars topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        group = lesson.group
        enrolled_count = group.group_students.exclude(student__is_archived=True).count()

        atts = Attendance.objects.filter(group=group, date=lesson.date)
        present_count = atts.filter(status='present').count()
        late_count = atts.filter(status='late').count()
        absent_count = atts.filter(status='absent').count()
        excused_count = atts.filter(status='excused').count()
        attended_total = present_count + late_count

        attendance_rate = round((attended_total / enrolled_count * 100), 1) if enrolled_count > 0 else 0.0

        return Response({
            "lesson_id": lesson.id,
            "group_name": group.name,
            "date": lesson.date.isoformat(),
            "topic": getattr(lesson, 'title', None) or getattr(lesson, 'topic', '') or "",
            "enrolled_count": enrolled_count,
            "present_count": present_count,
            "late_count": late_count,
            "absent_count": absent_count,
            "excused_count": excused_count,
            "attended_total": attended_total,
            "attendance_rate": attendance_rate
        }, status=status.HTTP_200_OK)
