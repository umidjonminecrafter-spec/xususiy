from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, status, decorators
from rest_framework.response import Response

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import IsGroupAssignedTeacherOrAdminOwnerForExam
from academics.models import Exam, ExamResult
from academics.serializers import ExamSerializer, ExamResultSerializer


@extend_schema_view(
    list=extend_schema(
        summary="Imtihonlar ro'yxatini olish",
        description="Guruh, kurs va sana bo'yicha filtrlangan imtihonlar ro'yxatini qaytaradi."
    ),
    create=extend_schema(
        summary="Yangi imtihon yaratish",
        description="Guruh uchun yangi imtihon (oraliq, yakuniy yoki sinov) jadvalini kiritadi."
    ),
    retrieve=extend_schema(
        summary="Imtihon tafsilotini ko'rish",
        description="ID bo'yicha imtihon ma'lumotlarini qaytaradi."
    ),
    update=extend_schema(
        summary="Imtihonni to'liq yangilash",
        description="Imtihon parametrlari va sanasini yangilaydi."
    ),
    partial_update=extend_schema(
        summary="Imtihonni qisman yangilash",
        description="Imtihonning ayrim maydonlarini tahrirlaydi."
    ),
    destroy=extend_schema(
        summary="Imtihonni o'chirish",
        description="Imtihonni va unga tegishli natijalarni bazadan o'chiradi."
    ),
)
class ExamViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsGroupAssignedTeacherOrAdminOwnerForExam]
    permission_page_name = 'Imtihon'
    queryset = Exam.objects.all()
    serializer_class = ExamSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['group', 'course', 'date']

    @extend_schema(
        summary="Imtihon baholarini ommaviy baholash (Grading)",
        description="Imtihon ID va talabalar ro'yxati (`results: [{student: id, score: val}, ...]`) bo'yicha baholarni saqlaydi yoki yangilaydi.",
        request=inline_serializer(
            name='ExamGradingRequest',
            fields={
                'exam': serializers.IntegerField(help_text="Imtihon ID raqami"),
                'results': serializers.ListField(
                    child=inline_serializer(
                        name='StudentExamScoreItem',
                        fields={
                            'student': serializers.IntegerField(help_text="Talaba ID"),
                            'score': serializers.DecimalField(max_digits=5, decimal_places=2, help_text="Talaba olgan ball"),
                        }
                    )
                )
            }
        ),
        responses={200: ExamResultSerializer(many=True)}
    )
    @decorators.action(detail=False, methods=['post'], url_path='grading')
    def grading(self, request):
        exam_id = request.data.get('exam') or request.data.get('exam_id')
        results = request.data.get('results')

        if not exam_id or not results:
            return Response(
                {"detail": "Imtihon va talaba baholari (results) kiritilishi shart."},
                status=status.HTTP_400_BAD_REQUEST
            )

        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Tashkilot aniqlanmadi."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            exam = Exam.objects.get(id=exam_id, organization_id=org_id)
        except Exam.DoesNotExist:
            return Response({"detail": "Imtihon topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        created_results = []
        for r in results:
            student_id = r.get('student') or r.get('student_id')
            score = r.get('score')
            if student_id is None or score is None:
                continue

            exam_result, created = ExamResult.objects.update_or_create(
                organization_id=org_id,
                exam=exam,
                student_id=student_id,
                defaults={'score': score}
            )
            created_results.append(exam_result)

        serializer = ExamResultSerializer(created_results, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        summary="Imtihon natijalari ro'yxatini olish",
        description="Imtihon va talaba ID bo'yicha imtihon baholari va natijalari ro'yxatini qaytaradi."
    ),
    create=extend_schema(
        summary="Yakka talaba imtihon natijasini kiritish",
        description="Bitta talaba uchun imtihon ballini saqlaydi."
    ),
    retrieve=extend_schema(
        summary="Imtihon natijasi tafsiloti",
        description="ID bo'yicha talabaning imtihon natijasini ko'rish."
    ),
    update=extend_schema(
        summary="Imtihon natijasini yangilash",
        description="Talabaning imtihon ballini o'zgartirish."
    ),
    partial_update=extend_schema(
        summary="Imtihon natijasini qisman yangilash",
        description="Talabaning imtihon ballini qisman tahrirlash."
    ),
    destroy=extend_schema(
        summary="Imtihon natijasini o'chirish",
        description="Talabaning imtihon natijasi yozuvini o'chirish."
    ),
)
class ExamResultViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsGroupAssignedTeacherOrAdminOwnerForExam]
    permission_page_name = 'Imtihon'
    queryset = ExamResult.objects.all()
    serializer_class = ExamResultSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['exam', 'student']
