from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, status, decorators
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import IsAdminOrOwnerOrReadOnly
from academics.models import Course, Room, CourseMaterial
from academics.serializers import CourseSerializer, RoomSerializer, CourseMaterialSerializer


@extend_schema_view(
    list=extend_schema(
        summary="Kurslar ro'yxatini olish",
        description="O'quv markazidagi barcha kurslar ro'yxatini (nomi, narxi, tavsifi) qaytaradi."
    ),
    create=extend_schema(
        summary="Yangi kurs yaratish",
        description="O'quv markaziga yangi o'quv kursi qo'shadi."
    ),
    retrieve=extend_schema(
        summary="Kurs tafsilotini olish",
        description="ID bo'yicha kursning to'liq ma'lumotlarini qaytaradi."
    ),
    update=extend_schema(
        summary="Kursni to'liq yangilash",
        description="Kursning barcha maydonlarini (nomi, narxi, davomiyligi va h.k.) yangilaydi."
    ),
    partial_update=extend_schema(
        summary="Kursni qisman yangilash",
        description="Kursning ayrim parametrlarini o'zgartiradi."
    ),
    destroy=extend_schema(
        summary="Kursni o'chirish",
        description="Kursni o'chiradi. Agar kursga biriktirilgan faol guruhlar mavjud bo'lsa, o'chirishni rad etadi."
    ),
)
class CourseViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Kurslar sozlamalari'
    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name', 'description']

    def destroy(self, request, *args, **kwargs):
        course = self.get_object()
        if course.groups.exists():
            return Response(
                {"detail": "Kursga biriktirilgan guruhlar mavjudligi sababli uni o'chirish mumkin emas."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)


@extend_schema_view(
    list=extend_schema(
        summary="Xonalar ro'yxatini olish",
        description="O'quv markazidagi barcha dars xonalari (nomi, sig'imi, filiali) ro'yxatini qaytaradi."
    ),
    create=extend_schema(
        summary="Yangi xona qo'shish",
        description="O'quv markaziga yangi dars xonasi parametrlarini saqlaydi."
    ),
    retrieve=extend_schema(
        summary="Xona tafsilotini ko'rish",
        description="ID bo'yicha dars xonasi ma'lumotlarini qaytaradi."
    ),
    update=extend_schema(
        summary="Xonani to'liq yangilash",
        description="Dars xonasining barcha parametrlarini yangilaydi."
    ),
    partial_update=extend_schema(
        summary="Xonani qisman yangilash",
        description="Dars xonasining ayrim maydonlarini o'zgartiradi."
    ),
    destroy=extend_schema(
        summary="Xonani o'chirish",
        description="Dars xonasini o'chiradi. Agar xonaga dars jadvali yoki guruhlar biriktirilgan bo'lsa, o'chirish rad etiladi."
    ),
)
class RoomViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Xonalar sozlamalari'
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name']

    def destroy(self, request, *args, **kwargs):
        room = self.get_object()
        if room.groups.exists():
            return Response(
                {"detail": "Xonaga biriktirilgan guruhlar mavjudligi sababli uni o'chirish mumkin emas."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        summary="Bo'sh xonalar ro'yxatini olish",
        description="Belgilangan dars kuni (day_type: even/odd) va dars vaqti (lesson_time_id) bo'yicha band bo'lmagan bo'sh xonalar ro'yxatini qaytaradi.",
        parameters=[
            OpenApiParameter('day_type', OpenApiTypes.STR, description="Hafta kunlari turi (even: juft, odd: toq)"),
            OpenApiParameter('lesson_time_id', OpenApiTypes.INT, description="Dars vaqti ID raqami"),
        ],
        responses={200: RoomSerializer(many=True)}
    )
    @decorators.action(detail=False, methods=['get'], url_path='available')
    def available(self, request):
        """Bo'sh xonalar ro'yxati (ixtiyoriy vaqt va kun bo'yicha filter)"""
        queryset = self.filter_queryset(self.get_queryset())
        day = request.query_params.get('day_type') or request.query_params.get('day')
        time_id = request.query_params.get('lesson_time') or request.query_params.get('time_id') or request.query_params.get('lesson_time_id')
        if day and time_id:
            from academics.models import Group
            occupied_room_ids = Group.objects.filter(
                organization_id=self.get_organization_id(),
                status='active',
                day_type=day,
                lesson_time_id=time_id
            ).values_list('room_id', flat=True)
            queryset = queryset.exclude(id__in=occupied_room_ids)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        summary="Kurs materiallari ro'yxati",
        description="Kursga biriktirilgan fayllar, video darsliklar va matnli materiallar ro'yxatini qaytaradi. Talaba roli uchun faqat o'zi o'qiydigan kurslarning e'lon qilingan materiallari ko'rsatiladi.",
        parameters=[
            OpenApiParameter('course', OpenApiTypes.INT, description="Kurs ID bo'yicha filter"),
            OpenApiParameter('material_type', OpenApiTypes.STR, description="Material turi (file, video, link, text)"),
            OpenApiParameter('is_published', OpenApiTypes.BOOL, description="E'lon qilinganlik holati"),
        ]
    ),
    create=extend_schema(
        summary="Yangi kurs materiali qo'shish",
        description="Kursga yangi o'quv qo'llanmasi, video havola yoki fayl yuklaydi."
    ),
    retrieve=extend_schema(
        summary="Kurs materiali tafsiloti",
        description="ID bo'yicha kurs materialini ko'rish."
    ),
    update=extend_schema(
        summary="Kurs materialini to'liq yangilash",
        description="Materialning barcha parametrlarini yangilaydi."
    ),
    partial_update=extend_schema(
        summary="Kurs materialini qisman yangilash",
        description="Materialning ayrim parametrlarini o'zgartiradi."
    ),
    destroy=extend_schema(
        summary="Kurs materialini o'chirish",
        description="Biriktirilgan kurs materialini o'chiradi."
    ),
)
class CourseMaterialViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Kurs materiallari: fayl, video, havola va boshqa materiallarni
    kursga bog'lash uchun CRUD endpoint.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Darslar hisoboti'
    queryset = CourseMaterial.objects.all().select_related('course')
    serializer_class = CourseMaterialSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['course', 'material_type', 'is_published']
    search_fields = ['title', 'description']
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        current_user = getattr(self.request, 'user', None)
        if current_user and getattr(current_user, 'role', None) == 'student':
            phone = getattr(current_user, 'phone', None) or getattr(current_user, 'username', None)
            if phone:
                qs = qs.filter(
                    course__groups__group_students__student__phone=phone,
                    is_published=True
                ).distinct()
            else:
                return qs.none()

        course_id = self.request.query_params.get('course') or self.request.query_params.get('course_id')
        if course_id:
            qs = qs.filter(course_id=course_id)

        material_type = self.request.query_params.get('material_type')
        if material_type:
            qs = qs.filter(material_type=material_type)

        is_published = self.request.query_params.get('is_published')
        if is_published is not None:
            if str(is_published).lower() in ['true', '1']:
                qs = qs.filter(is_published=True)
            elif str(is_published).lower() in ['false', '0']:
                if current_user and getattr(current_user, 'role', None) == 'student':
                    return qs.none()
                qs = qs.filter(is_published=False)

        return qs.order_by('order', 'id')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
