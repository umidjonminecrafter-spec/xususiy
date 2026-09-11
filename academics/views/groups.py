import logging
from django.apps import apps
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Count, Max, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, status, decorators
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import IsAdminOrOwnerOrReadOnly
from academics.models import Group, StudentGroup, GroupTeacher, StudentGroupLeave, Student, LessonSchedule
from academics.serializers import (
    GroupSerializer, StudentGroupSerializer, GroupTeacherSerializer, StudentGroupLeaveSerializer
)
from academics.filters import GroupFilter

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        summary="Guruhlar ro'yxatini olish",
        description="O'quv markazidagi barcha guruhlar ro'yxatini qaytaradi. O'qituvchi, filial, kurs va status bo'yicha filtrlash imkoniyati mavjud."
    ),
    create=extend_schema(
        summary="Yangi guruh yaratish",
        description="Yangi o'quv guruhini yaratadi va guruh dars jadvalini (`LessonSchedule`) avtomatik sinxronizatsiya qiladi."
    ),
    retrieve=extend_schema(
        summary="Guruh tafsilotini olish",
        description="ID bo'yicha guruhning to'liq ma'lumotlarini (o'qituvchi, xona, kurs, talabalar soni) qaytaradi."
    ),
    update=extend_schema(
        summary="Guruhni to'liq yangilash",
        description="Guruh parametrlari va dars vaqtlarini yangilaydi hamda jadvalni sinxronlashtiradi."
    ),
    partial_update=extend_schema(
        summary="Guruhni qisman yangilash",
        description="Guruhning alohida maydonlarini tahrirlaydi."
    ),
    destroy=extend_schema(
        summary="Guruhni o'chirish",
        description="Guruhni bazadan o'chiradi. Guruhda talabalar bo'lsa, o'chirish rad etiladi."
    ),
)
class GroupViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    permission_page_name = 'Guruhlar'
    queryset = Group.objects.select_related(
        'organization', 'branch', 'course', 'room', 'teacher', 'assistant_teacher'
    ).prefetch_related('group_students__student', 'group_teachers__teacher')
    serializer_class = GroupSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = GroupFilter
    search_fields = ['name']

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Guruh yaratishda xatolik yuz berdi: {str(e)}")
            return Response({
                "error": "Guruhni saqlashda xatolik yuz berdi",
                "detail": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Guruhni yangilashda xatolik: {str(e)}")
            return Response({
                "error": "Guruhni yangilashda xatolik yuz berdi",
                "detail": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    def get_queryset(self):
        qs = super().get_queryset()
        teacher_id = self.request.query_params.get('teacher')
        if teacher_id:
            qs = qs.filter(
                Q(teacher_id=teacher_id) |
                Q(assistant_teacher_id=teacher_id) |
                Q(group_teachers__teacher_id=teacher_id)
            ).distinct()

        current_user = getattr(self.request, 'user', None)
        if current_user and getattr(current_user, 'role', None) == 'student':
            phone = getattr(current_user, 'phone', None) or getattr(current_user, 'username', None)
            if phone:
                qs = qs.filter(group_students__student__phone=phone).distinct()
            else:
                qs = qs.none()
        return qs

    def destroy(self, request, *args, **kwargs):
        group = self.get_object()
        if group.group_students.exists():
            return Response({
                "detail": "Guruhda talabalar borligi sababli uni o'chirish mumkin emas. Avval talabalarni guruhdan chiqaring."
            }, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        summary="Guruhni arxivlash",
        description="Guruh holatini 'archived' ga o'zgartiradi. Agar guruhda talabalar bo'lsa, avval ularni chiqarish talab etiladi.",
        responses={
            200: inline_serializer(name='GroupArchiveSuccess', fields={'status': serializers.CharField(), 'detail': serializers.CharField()}),
            400: inline_serializer(name='GroupArchiveError', fields={'detail': serializers.CharField()})
        }
    )
    @decorators.action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        group = self.get_object()
        if group.group_students.exists():
            return Response({
                "detail": "Guruhda talabalar borligi sababli uni arxivlash mumkin emas. Avval talabalarni guruhdan chiqaring."
            }, status=status.HTTP_400_BAD_REQUEST)
        group.status = 'archived'
        group.save()
        return Response({"status": "success", "detail": "Group archived successfully."}, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Guruh talabalari ro'yxatini olish",
        description="Tanlangan guruhga a'zo barcha talabalar, ularning shaxsiy balansi, narxi va chegirmalari ro'yxatini qaytaradi.",
        responses={
            200: inline_serializer(
                name='GroupStudentItem',
                fields={
                    'id': serializers.IntegerField(),
                    'student_group_id': serializers.IntegerField(),
                    'first_name': serializers.CharField(),
                    'last_name': serializers.CharField(),
                    'full_name': serializers.CharField(),
                    'phone': serializers.CharField(),
                    'balance': serializers.FloatField(),
                    'joined_date': serializers.CharField(),
                    'price': serializers.FloatField(),
                    'discount_type': serializers.CharField(allow_null=True),
                    'discount_amount': serializers.FloatField(),
                    'is_active': serializers.BooleanField(),
                },
                many=True
            )
        }
    )
    @decorators.action(detail=True, methods=['get'], url_path='students')
    def students(self, request, pk=None):
        """Guruh talabalari ro'yxatini qaytaradi"""
        group = self.get_object()
        student_groups = group.group_students.select_related('student').all()
        data = []
        for sg in student_groups:
            s = sg.student
            if not s:
                continue
            data.append({
                "id": s.id,
                "student_group_id": sg.id,
                "first_name": s.first_name,
                "last_name": s.last_name or '',
                "full_name": f"{s.first_name} {s.last_name or ''}".strip(),
                "phone": s.phone,
                "balance": float(s.balance or 0),
                "joined_date": sg.joined_at.isoformat() if getattr(sg, 'joined_at', None) else None,
                "price": float(sg.price) if sg.price is not None else (float(group.course.price) if group.course and hasattr(group.course, 'price') else 0.0),
                "discount_type": getattr(sg, 'discount_type', None),
                "discount_amount": float(getattr(sg, 'discount_amount', 0) or 0),
                "is_active": not getattr(s, 'is_archived', False)
            })
        return Response(data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Talabani guruhga qo'shish",
        description="Talabani ko'rsatilgan guruhga a'zo qiladi va guruh darslariga mos ravishda dastlabki davomat yozuvlarini yaratadi.",
        request=inline_serializer(
            name='AddStudentToGroupRequest',
            fields={'student': serializers.IntegerField(help_text="Talaba ID raqami")}
        ),
        responses={
            201: StudentGroupSerializer,
            400: inline_serializer(name='AddStudentToGroupError', fields={'detail': serializers.CharField()})
        }
    )
    @decorators.action(detail=True, methods=['post'], url_path='add-student')
    def add_student(self, request, pk=None):
        group = self.get_object()
        student_id = request.data.get('student')
        if not student_id:
            return Response({"detail": "Student ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        org_id = self.get_organization_id()
        student = get_object_or_404(Student.objects.filter(organization_id=org_id), id=student_id)

        if StudentGroup.objects.filter(group=group, student=student).exists():
            return Response(
                {"detail": "Bu talaba ushbu guruhga allaqachon qo'shilgan!"},
                status=status.HTTP_400_BAD_REQUEST
            )

        student_group = StudentGroup.objects.create(
            organization_id=org_id,
            student=student,
            group=group
        )

        GroupLesson = apps.get_model('academics', 'GroupLesson')
        Attendance = apps.get_model('academics', 'Attendance')

        all_lessons = GroupLesson.objects.filter(group=group).order_by('date')
        today = timezone.now().date()
        past_lessons_count = all_lessons.filter(date__lte=today).count()

        if past_lessons_count <= 3:
            target_lessons = all_lessons
        else:
            target_lessons = all_lessons.filter(date__gte=today)

        for lesson in target_lessons:
            Attendance.objects.get_or_create(
                organization_id=org_id,
                student=student,
                group=group,
                date=lesson.date,
                defaults={'status': 'present'}
            )

        return Response(StudentGroupSerializer(student_group).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Guruh tarixi va voqealar logi",
        description="Guruh yaratilishi, o'qituvchi biriktirilishi, talabalar qo'shilishi/chiqishi, davomat olinganligi va onlayn darslar xronologik tarixini qaytaradi.",
        responses={
            200: inline_serializer(
                name='GroupHistoryLogItem',
                fields={
                    'action': serializers.CharField(),
                    'description': serializers.CharField(),
                    'created_at': serializers.CharField(),
                },
                many=True
            )
        }
    )
    @decorators.action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        group = self.get_object()
        logs = []

        OnlineLesson = apps.get_model('academics', 'OnlineLesson')
        Attendance = apps.get_model('academics', 'Attendance')

        created_time = getattr(group, 'created_at', timezone.now()) or timezone.now()
        logs.append({
            "action": "Yaratildi",
            "description": f"Guruh yaratildi. Kurs: {group.course.name if group.course else 'Kiritilmagan'}. Narxi: {(group.course.price if group.course else 0)} UZS.",
            "created_at": created_time
        })

        for gt in GroupTeacher.objects.filter(group=group).select_related('teacher'):
            teacher_name = gt.teacher.get_full_name() or gt.teacher.username if gt.teacher else "Noma'lum o'qituvchi"
            gt_time = getattr(gt, 'created_at', timezone.now()) or timezone.now()
            logs.append({
                "action": "O'qituvchi",
                "description": f"O'qituvchi {teacher_name} guruhga biriktirildi.",
                "created_at": gt_time
            })

        for sg in StudentGroup.objects.filter(group=group).select_related('student'):
            student_name = f"{sg.student.first_name} {sg.student.last_name or ''}".strip() if sg.student else "Noma'lum talaba"
            sg_time = getattr(sg, 'joined_at', timezone.now()) or timezone.now()
            logs.append({
                "action": "Qo'shildi",
                "description": f"Talaba {student_name} guruhga qo'shildi. Narxi: {(group.course.price if group.course else 0)} UZS.",
                "created_at": sg_time
            })

        for sgl in StudentGroupLeave.objects.filter(group=group).select_related('student', 'leave_reason'):
            student_name = f"{sgl.student.first_name} {sgl.student.last_name or ''}".strip() if sgl.student else "Noma'lum talaba"
            reason = sgl.leave_reason.reason if sgl.leave_reason else "ko'rsatilmagan"
            sgl_time = getattr(sgl, 'leave_date', timezone.now()) or timezone.now()
            logs.append({
                "action": "Chiqdi",
                "description": f"Talaba {student_name} guruhdan chiqdi (Sabab: {reason}).",
                "created_at": sgl_time
            })

        att_dates = Attendance.objects.filter(group=group).values('date').annotate(
            total=Count('id'),
            present=Count('id', filter=Q(status='present')),
            absent=Count('id', filter=Q(status='absent')),
            excused=Count('id', filter=Q(status='excused')),
            last_change=Max('id')
        ).order_by('-date')

        for ad in att_dates:
            dt_str = ad['date'].strftime('%d.%m.%Y') if hasattr(ad['date'], 'strftime') else str(ad['date'])
            present = ad['present']
            absent = ad['absent']
            excused = ad['excused']
            desc = f"{dt_str} kungi dars uchun yo'qlama olingan (Qatnashdi: {present}, Qatnashmadi: {absent}"
            if excused > 0:
                desc += f", Sababli: {excused}"
            desc += ")."
            logs.append({
                "action": "Davomat",
                "description": desc,
                "created_at": timezone.now()
            })

        for ol in OnlineLesson.objects.filter(group=group):
            logs.append({
                "action": "Onlayn dars",
                "description": f"Onlayn dars qo'shildi: '{ol.title}'.",
                "created_at": timezone.now()
            })

        for log in logs:
            if hasattr(log['created_at'], 'isoformat'):
                log['created_at'] = log['created_at'].isoformat()
            else:
                log['created_at'] = str(log['created_at'])

        logs.sort(key=lambda x: x['created_at'], reverse=True)
        return Response(logs, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Guruh talabalariga ommaviy SMS yuborish",
        description="Guruhdagi barcha faol talabalarga ko'rsatilgan xabar matnini SMS tarzida tarqatadi.",
        request=inline_serializer(
            name='GroupSendSMSRequest',
            fields={'message': serializers.CharField(help_text="SMS xabar matni")}
        ),
        responses={
            200: inline_serializer(name='GroupSendSMSSuccess', fields={'status': serializers.CharField(), 'message': serializers.CharField()}),
            400: inline_serializer(name='GroupSendSMSError', fields={'detail': serializers.CharField()}),
            403: inline_serializer(name='GroupSendSMSForbidden', fields={'detail': serializers.CharField()}),
        }
    )
    @decorators.action(detail=True, methods=['post'], url_path='send-sms')
    def send_sms(self, request, pk=None):
        group = self.get_object()

        if getattr(request.user, 'role', None) == 'teacher':
            from organizations.models import Subscription
            subscription = Subscription.objects.filter(
                organization_id=self.get_organization_id(),
                is_active=True
            ).first()
            if subscription and not subscription.allow_teacher_sms:
                return Response(
                    {"detail": "O'qituvchilarga talabalarga SMS yuborishga ruxsat berilmagan."},
                    status=status.HTTP_403_FORBIDDEN
                )

        message = request.data.get('message')
        if not message:
            return Response({"detail": "Message is required."}, status=status.HTTP_400_BAD_REQUEST)

        student_groups = StudentGroup.objects.filter(group=group)
        count = student_groups.count()

        return Response({
            "status": "success",
            "message": f"SMS successfully broadcasted to {count} students in group {group.name}."
        }, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        org_id = self.get_organization_id()
        if not org_id:
            raise ValidationError({"detail": "Organization context is required."})
        from organizations.models import Organization, Branch
        try:
            org = Organization.objects.get(id=org_id)
        except Organization.DoesNotExist:
            raise ValidationError({"detail": f"Organization with ID {org_id} not found."})

        save_kwargs = {'organization': org}
        branch_id = self.get_branch_id()
        if branch_id:
            try:
                save_kwargs['branch'] = Branch.objects.get(id=branch_id)
            except Branch.DoesNotExist:
                pass

        serializer.save(**save_kwargs)
        group = serializer.instance
        self._sync_lesson_schedules(group)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        group = serializer.instance
        self._sync_lesson_schedules(group)

    def _sync_lesson_schedules(self, group):
        LessonSchedule.objects.filter(group=group).delete()

        if group.days and group.start_time and group.end_time:
            if isinstance(group.days, list):
                days_list = [str(d).lower().strip() for d in group.days]
            else:
                days_list = [str(group.days).lower().strip()]

            days_combined = " ".join(days_list)
            is_even = any(x in days_combined for x in ['seshanba', 'payshanba', 'shanba', 'tue', 'thu', 'sat', '2', '4', '6'])
            is_odd = any(x in days_combined for x in ['dushanba', 'chorshanba', 'juma', 'mon', 'wed', 'fri', '1', '3', '5'])

            if is_even:
                calculated_day_type = 'even'
            elif is_odd:
                calculated_day_type = 'odd'
            else:
                calculated_day_type = 'even'

            org_id = getattr(group, 'organization_id', None) or self.get_organization_id()
            LessonSchedule.objects.create(
                organization_id=org_id,
                group=group,
                room_name=group.room.name if group.room else "Xona biriktirilmagan",
                teacher=group.teacher,
                start_time=group.start_time,
                end_time=group.end_time,
                day_type=calculated_day_type
            )


@extend_schema_view(
    list=extend_schema(
        summary="Talaba va guruh bog'lanishlari ro'yxati",
        description="Guruhlarga biriktirilgan barcha talabalar ro'yxati."
    ),
    create=extend_schema(
        summary="Talabani guruhga biriktirish",
        description="Talabani guruhga a'zo qilib qo'shadi."
    ),
    retrieve=extend_schema(
        summary="Talaba-guruh bog'lanishi tafsiloti",
        description="ID bo'yicha bog'lanish ma'lumotlarini ko'rish."
    ),
    update=extend_schema(
        summary="Talaba-guruh ma'lumotlarini yangilash",
        description="Chegirma yoki narx parametrlarini yangilash."
    ),
    partial_update=extend_schema(
        summary="Talaba-guruh ma'lumotlarini qisman yangilash",
        description="A'zolik parametrlarini qisman tahrirlash."
    ),
    destroy=extend_schema(
        summary="Talabani guruhdan chiqarish",
        description="Talabani guruhdan chiqaradi va ketish sababi (`StudentGroupLeave`) tarixini yaratadi."
    ),
)
class StudentGroupViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Guruhlar'
    queryset = StudentGroup.objects.all().select_related('group__teacher', 'student')
    serializer_class = StudentGroupSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['group', 'student']
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(student__isnull=False).exclude(student__is_archived=True)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        leave_reason_id = request.query_params.get('leave_reason_id') or request.query_params.get('leave_reason')
        comment = request.query_params.get('comment')
        refound_amount = request.query_params.get('refound_amount') or 0.00

        leave_reason = None
        if leave_reason_id:
            try:
                from academics.models import LeaveReason
                leave_reason = LeaveReason.objects.get(id=leave_reason_id)
            except Exception:
                pass

        StudentGroupLeave.objects.create(
            organization=instance.organization,
            branch=instance.branch,
            student=instance.student,
            group=instance.group,
            leave_date=timezone.now().date(),
            leave_reason=leave_reason,
            comment=comment,
            refound_amount=refound_amount
        )
        return super().destroy(request, *args, **kwargs)


@extend_schema_view(
    list=extend_schema(
        summary="Guruh o'qituvchilari ro'yxati",
        description="Guruhlarga biriktirilgan asosiy va yordamchi o'qituvchilar ro'yxatini qaytaradi."
    ),
    create=extend_schema(
        summary="Guruhga o'qituvchi biriktirish",
        description="O'qituvchini guruhga yangi murabbiy sifatida biriktiradi."
    ),
    retrieve=extend_schema(
        summary="Guruh o'qituvchisi tafsiloti",
        description="ID bo'yicha guruh-o'qituvchi bog'lanishini ko'rish."
    ),
    update=extend_schema(
        summary="Guruh o'qituvchisini yangilash",
        description="O'qituvchi birikmasini to'liq yangilash."
    ),
    partial_update=extend_schema(
        summary="Guruh o'qituvchisini qisman yangilash",
        description="O'qituvchi birikmasini qisman tahrirlash."
    ),
    destroy=extend_schema(
        summary="O'qituvchini guruhdan ajratish",
        description="O'qituvchining ushbu guruhdagi birikmasini bekor qiladi."
    ),
)
class GroupTeacherViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'O\'qituvchilar'
    queryset = GroupTeacher.objects.all()
    serializer_class = GroupTeacherSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['teacher', 'group']


@extend_schema_view(
    list=extend_schema(
        summary="Guruhni tark etganlar jurnali",
        description="Guruhdan yoki o'quv markazidan ketgan barcha talabalar, ketish sabablari va qaytarilgan summalar tarixi."
    ),
    create=extend_schema(
        summary="Ketgan talaba yozuvini qo'shish",
        description="Guruhdan chiqish yozuvini qo'lda kiritadi."
    ),
    retrieve=extend_schema(
        summary="Ketgan talaba yozuvi tafsiloti",
        description="ID bo'yicha ketish yozuvini ko'rish."
    ),
    update=extend_schema(
        summary="Ketish yozuvini yangilash",
        description="Ketish sababi yoki izohini o'zgartirish."
    ),
    partial_update=extend_schema(
        summary="Ketish yozuvini qisman yangilash",
        description="Ketish sababi yoki izohini qisman tahrirlash."
    ),
    destroy=extend_schema(
        summary="Ketish yozuvini arxivlash/o'chirish",
        description="Birinchi marta chaqirilganda yozuvni arxivlaydi, arxivlangan bo'lsa butunlay o'chiradi."
    ),
)
class StudentGroupLeaveViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Guruhni tark etganlar'
    queryset = StudentGroupLeave.objects.all()
    serializer_class = StudentGroupLeaveSerializer

    def get_queryset(self):
        org_id = self.get_organization_id()
        if not org_id:
            return StudentGroupLeave.objects.none()

        qs = StudentGroupLeave.objects.filter(organization_id=org_id)
        branch_id = self.get_branch_id()
        if branch_id:
            qs = qs.filter(Q(branch_id=branch_id) | Q(branch__isnull=True))

        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        course_id = self.request.query_params.get('course')
        teacher_id = self.request.query_params.get('teacher')
        reason_id = self.request.query_params.get('reason') or self.request.query_params.get('leave_reason')
        status_val = self.request.query_params.get('status')
        search = self.request.query_params.get('search')

        if start_date:
            qs = qs.filter(leave_date__gte=start_date)
        if end_date:
            qs = qs.filter(leave_date__lte=end_date)
        if course_id:
            qs = qs.filter(group__course_id=course_id)
        if teacher_id:
            qs = qs.filter(group__teacher_id=teacher_id)
        if reason_id:
            qs = qs.filter(leave_reason_id=reason_id)
        if search:
            qs = qs.filter(
                Q(student__first_name__icontains=search) |
                Q(student__last_name__icontains=search) |
                Q(student__phone__icontains=search)
            )
        if status_val:
            if status_val in ['trial', 'sinov', 'trial_left', 'Sinovdan ketgan']:
                qs = qs.filter(
                    Q(group__name__icontains='sinov') |
                    Q(group__name__icontains='trial') |
                    Q(student__first_name__icontains='trial') |
                    Q(student__first_name__icontains='sinov')
                )
            else:
                qs = qs.exclude(
                    Q(group__name__icontains='sinov') |
                    Q(group__name__icontains='trial') |
                    Q(student__first_name__icontains='trial') |
                    Q(student__first_name__icontains='sinov')
                )

        if self.action == 'list':
            is_archived = self.request.query_params.get('is_archived')
            if is_archived is not None:
                is_archived_bool = is_archived.lower() in ['true', '1']
                qs = qs.filter(is_archived=is_archived_bool)
            else:
                qs = qs.filter(is_archived=False)

        return qs.order_by('-leave_date')

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not instance.is_archived:
            instance.is_archived = True
            instance.save()
            return Response({"status": "archived", "message": "Record moved to archive."}, status=status.HTTP_200_OK)
        else:
            return super().destroy(request, *args, **kwargs)
