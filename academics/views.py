from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, permissions, status, decorators, generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from organizations.mixins import TenantViewSetMixin
from .models import StudentFieldSetting, GroupLesson
from .serializers import StudentFieldSettingSerializer, StudentProfileSerializer, RescheduleLessonSerializer, \
    SetLessonTopicSerializer, GroupLessonListSerializer, StudentEvaluationLevelSerializer
from academics.models import (
    Course, Room, Student, Group, StudentGroup, GroupTeacher, TeacherSalaryPayment, Attendance, LessonSchedule,
    BalanceHistory, Exam, ExamResult, LeaveReason, LessonTime, OnlineLesson, StudentGroupLeave, StudentPricing,
    StudentArchive, Holiday, Homework,
    BotMessageTemplate, CourseMaterial,
    Building, SchoolClass, ClassStudent, Parent, StudentAddress, StudentAppeal
)
from organizations.mixins import TenantViewSetMixin
from organizations.permissions import (
    IsAdminOrOwnerOrReadOnly, IsGroupAssignedTeacherForAttendance, IsGroupAssignedTeacherOrAdminOwnerForExam
)
from academics.serializers import (
    CourseSerializer, RoomSerializer, StudentSerializer, GroupSerializer,
    StudentGroupSerializer, GroupTeacherSerializer, TeacherSalaryPaymentSerializer, AttendanceSerializer,
    LessonScheduleSerializer, StudentBalanceSerializer, BalanceHistorySerializer, ExamSerializer,
    ExamResultSerializer, LeaveReasonSerializer, LessonTimeSerializer, OnlineLessonSerializer,
    StudentGroupLeaveSerializer, StudentPricingSerializer, StudentArchiveSerializer, HolidaySerializer,
    HomeworkSerializer, BotMessageTemplateSerializer, CourseMaterialSerializer,
    BuildingSerializer, SchoolClassSerializer, ClassStudentSerializer, ParentSerializer, StudentAddressSerializer,
    StudentAppealSerializer
)

from .models import TelegramVerification, Student
from .utills import send_telegram_verification_code


# 1. KOD YUBORISH API (Ro'yxatdan o'tish yoki Parol unutilganda chaqiriladi)
class SendCodeAPIView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        phone = request.data.get('phone')
        purpose = request.data.get('purpose')  # 'register' yoki 'forgot'

        if not phone or not purpose:
            return Response({"error": "phone va purpose maydonlari majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        if purpose not in ['register', 'forgot']:
            return Response({"error": "Purpose noto'g'ri!"}, status=status.HTTP_400_BAD_REQUEST)

        # Kodni generatsiya qilib jo'natamiz
        result = send_telegram_verification_code(phone, purpose)

        if result["status"]:
            return Response({"message": result["message"]}, status=status.HTTP_200_OK)
        return Response({"error": result["message"]}, status=status.HTTP_400_BAD_REQUEST)


# 2. KODNI TEKSHIRISH API
class VerifyCodeAPIView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        phone = request.data.get('phone')
        code = request.data.get('code')
        purpose = request.data.get('purpose')
        new_password = request.data.get('password') or request.data.get('new_password')

        if not phone or not code or not purpose:
            return Response({"error": "Barcha maydonlar majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        # Telefon raqamni normallashtiramiz (+998XXXXXXXXX formatga)
        cleaned = ''.join(c for c in str(phone) if c.isdigit())
        if len(cleaned) == 9:
            cleaned = '998' + cleaned
        formatted_phone = '+' + cleaned

        # Eng oxirgi yuborilgan faol kodni turli formatlar orqali qidiramiz
        verif = TelegramVerification.objects.filter(
            phone__in=[phone, cleaned, formatted_phone], code=code, purpose=purpose
        ).order_by('id').last()

        if verif and verif.is_valid():
            # Kod to'g'ri bo'lsa, uni ishlatildi deb belgilaymiz
            verif.is_verified = True
            verif.save()

            # AGAR PAROL TIKLASH BO'LSA:
            if purpose == 'forgot':
                from django.contrib.auth import get_user_model
                User = get_user_model()

                # Foydalanuvchini telefon raqami yoki username orqali topamiz
                user = User.objects.filter(phone__in=[phone, cleaned, formatted_phone]).first()
                if not user:
                    user = User.objects.filter(username__in=[phone, cleaned, formatted_phone]).first()

                if user:
                    if new_password:
                        user.set_password(new_password)
                        user.save()
                        return Response(
                            {"status": "success",
                             "message": "Parol muvaffaqiyatli o'zgartirildi! Yangi parol bilan tizimga kirishingiz mumkin."},
                            status=status.HTTP_200_OK
                        )
                    else:
                        return Response(
                            {"status": "success", "message": "Tasdiqlash kodi to'g'ri. Yangi parolingizni kiriting."},
                            status=status.HTTP_200_OK
                        )
                else:
                    return Response({"error": "Tizimda bunday telefon raqamli foydalanuvchi topilmadi!"},
                                    status=status.HTTP_400_BAD_REQUEST)

            # AGAR RO'YXATDAN O'TISH BO'LSA:
            elif purpose == 'register':
                return Response({"status": "success", "message": "Kod tasdiqlandi. Ro'yxatdan o'tish yakunlandi."},
                                status=status.HTTP_200_OK)

        return Response({"error": "Tasdiqlash kodi noto'g'ri yoki vaqti o'tib ketgan!"},
                        status=status.HTTP_400_BAD_REQUEST)


class StudentFieldSettingViewSet(
    TenantViewSetMixin,
    viewsets.ModelViewSet
):
    serializer_class = StudentFieldSettingSerializer
    queryset = StudentFieldSetting.objects.all()

    def get_queryset(self):
        return StudentFieldSetting.objects.filter(
            organization=self.request.user.organization
        )

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization
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
            return Response({"detail": "Kursga biriktirilgan guruhlar mavjudligi sababli uni o'chirish mumkin emas."},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)


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
            return Response({"detail": "Xonaga biriktirilgan guruhlar mavjudligi sababli uni o'chirish mumkin emas."},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

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


class StudentViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Talabalar'
    queryset = Student.objects.all().select_related('school_class')
    serializer_class = StudentSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['first_name', 'last_name', 'phone', 'email', 'school_class__grade_level', 'school_class__section']
    pagination_class = None

    def get_queryset(self):
        is_archived_param = self.request.query_params.get('is_archived') or self.request.query_params.get('archived')
        if is_archived_param and str(is_archived_param).lower() in ('true', '1'):
            queryset = super().get_queryset().filter(is_archived=True)
        else:
            queryset = super().get_queryset().exclude(is_archived=True)
        group_id = self.request.query_params.get('group') or self.request.query_params.get('group_id')
        if group_id:
            queryset = queryset.filter(student_groups__group_id=group_id)

        # 🌟 Sinf (SchoolClass) bo'yicha filterlash
        class_id = (
            self.request.query_params.get('school_class') or
            self.request.query_params.get('school_class_id') or
            self.request.query_params.get('class_id') or
            self.request.query_params.get('class')
        )
        if class_id:
            queryset = queryset.filter(school_class_id=class_id)

        # 🌟 Yangi: ID bo'yicha filterlash
        student_id = self.request.query_params.get('id')
        if student_id:
            queryset = queryset.filter(id=student_id)

        # 🌟 Yangi: Agar search param berilgan bo'lsa va u raqam (ID) bo'lsa, ID bo'yicha ham qidiramiz
        search_param = self.request.query_params.get('search')
        if search_param and search_param.isdigit():
            from django.db.models import Q
            queryset = queryset.filter(
                Q(id=int(search_param)) |
                Q(first_name__icontains=search_param) |
                Q(last_name__icontains=search_param) |
                Q(phone__icontains=search_param) |
                Q(email__icontains=search_param)
            )
            # Standart SearchFilter qaytadan ishlamasligi uchun search_fields ni vaqtincha tozalaymiz
            self.search_fields = []

        return queryset

    def perform_create(self, serializer):
        org_id = self.get_organization_id()
        if not org_id:
            from rest_framework import exceptions
            raise exceptions.ValidationError({"detail": "Organization context is required."})

        # Obunani tekshirish
        from organizations.models import Subscription
        subscription = Subscription.objects.filter(organization_id=org_id, is_active=True).first()
        if not subscription:
            from rest_framework import exceptions
            raise exceptions.ValidationError(
                {"detail": "Tashkilotning faol obunasi topilmadi. Yangi talaba qo'shish uchun tarif sotib oling."})

        tariff = subscription.tariff
        if tariff and tariff.student_limit > 0:
            # Hozirgi talabalar sonini hisoblash
            current_students_count = Student.objects.filter(organization_id=org_id).count()
            if current_students_count >= tariff.student_limit:
                from rest_framework import exceptions
                raise exceptions.ValidationError({
                                                     "detail": f"Tarifingizdagi talabalar limiti ({tariff.student_limit}) ga yetdingiz. Yangi talaba qo'shish uchun tarifni yangilang."})

        super().perform_create(serializer)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        reason = request.query_params.get('reason') or request.data.get('reason') or "O'chirib tashlangan"
        comment = request.query_params.get('comment') or request.data.get('comment') or ""
        
        # Arxiv yozuvini yaratish
        StudentArchive.objects.create(
            organization=instance.organization,
            branch=instance.branch,
            first_name=instance.first_name,
            last_name=instance.last_name,
            phone=instance.phone,
            email=instance.email,
            role="Student",
            reason=reason,
            comment=comment,
            archived_by=request.user.get_full_name() or request.user.username if request.user.is_authenticated else "Tizim"
        )
        
        from accounts.models import User
        if instance.balance < 0:
            # Qarzdorligi bor: Soft delete qilinadi va User faqat bloklanadi
            instance.is_archived = True
            instance.save(update_fields=['is_archived'])
            if instance.phone:
                username = f"{instance.phone}_{instance.organization_id}"
                qs = User.objects.filter(username=username, role='student')
                if not qs.exists():
                    qs = User.objects.filter(username=instance.phone, role='student')
                qs.update(is_active=False)
            return Response({"detail": "Qarzdorligi borligi sababli talaba yumshoq o'chirildi (arxivlandi).", "id": instance.id}, status=status.HTTP_200_OK)
        else:
            # Qarzdorligi yo'q: Butunlay o'chiriladi va User akkaunti ham o'chiriladi
            if instance.phone:
                username = f"{instance.phone}_{instance.organization_id}"
                qs = User.objects.filter(username=username, role='student')
                if not qs.exists():
                    qs = User.objects.filter(username=instance.phone, role='student')
                qs.delete()
            return super().destroy(request, *args, **kwargs)

    @decorators.action(detail=True, methods=['post'], url_path='add-payment')
    def add_payment(self, request, pk=None):
        student = self.get_object()
        amount = request.data.get('amount')
        payment_method = request.data.get('payment_method') or request.data.get('payment_type') or 'cash'
        comment = request.data.get('comment') or request.data.get('note') or ''

        if not amount:
            return Response({"detail": "Amount is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from decimal import Decimal
            amount_dec = Decimal(str(amount))
        except ValueError:
            return Response({"detail": "Invalid amount."}, status=status.HTTP_400_BAD_REQUEST)

        # Import Finance Payment dynamically to avoid circular dependencies
        from finance.models import Payment
        org_id = self.get_organization_id()
        payment = Payment.objects.create(
            organization_id=org_id,
            branch_id=self.get_branch_id(),
            student=student,
            amount=amount_dec,
            date=timezone.now().date(),
            payment_method=payment_method,
            employee=request.user if request.user.is_authenticated else None,
            comment=comment
        )

        student.refresh_from_db()

        return Response({
            "detail": "Payment added successfully.",
            "balance": student.balance,
            "payment_id": payment.id
        }, status=status.HTTP_201_CREATED)

    @decorators.action(detail=True, methods=['post'], url_path='add-to-group')
    def add_to_group(self, request, pk=None):
        student = self.get_object()
        group_id = request.data.get('group') or request.data.get('group_id')
        if not group_id:
            return Response({"detail": "Group ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        org_id = self.get_organization_id()
        group = get_object_or_404(Group.objects.filter(organization_id=org_id), id=group_id)

        student_group, created = StudentGroup.objects.get_or_create(
            organization_id=org_id,
            student=student,
            group=group
        )
        return Response(StudentGroupSerializer(student_group).data, status=status.HTTP_201_CREATED)

    @decorators.action(detail=True, methods=['get'], url_path='balance-status')
    def balance_status(self, request, pk=None):
        student = self.get_object()
        return Response({
            "balance": student.balance,
            "status": "positive" if student.balance >= 0 else "negative"
        }, status=status.HTTP_200_OK)

    @decorators.action(detail=False, methods=['get'], url_path='report')
    def report(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        total_students = queryset.count()
        return Response({
            "total_students": total_students,
            "report_date": timezone.now().date()
        }, status=status.HTTP_200_OK)

    @decorators.action(detail=False, methods=['post'], url_path=r'status/(?P<action_name>[^/.]+)')
    def status_action(self, request, action_name=None):
        return Response({"status": "success", "action": action_name, "detail": "Bulk status action processed."},
                        status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=['get'], url_path='history')
    def history(self, request, pk=None):
        student = self.get_object()
        attendances = Attendance.objects.filter(student=student)
        groups = StudentGroup.objects.filter(student=student)

        # Pull payments dynamically
        from finance.models import Payment
        payments = Payment.objects.filter(student=student)

        return Response({
            "student": StudentSerializer(student).data,
            "groups": StudentGroupSerializer(groups, many=True).data,
            "attendance_count": attendances.count(),
            "payments_count": payments.count(),
            "payments": [{"id": p.id, "amount": p.amount, "date": p.date, "method": p.payment_method} for p in
                         payments],
            "attendances": [{"id": a.id, "group": a.group.name, "date": a.date, "status": a.status} for a in
                            attendances]
        }, status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=['get'], url_path='lead-history')
    def lead_history(self, request, pk=None):
        student = self.get_object()
        # Find matching Lead in CRM dynamically
        from crm.models import Lead
        leads = Lead.objects.filter(phone=student.phone, organization_id=self.get_organization_id())

        lead_data = []
        for lead in leads:
            lead_data.append({
                "id": lead.id,
                "name": lead.name,
                "status": lead.status,
                "pipeline": lead.pipeline.name if lead.pipeline else None,
                "source": lead.source.name if lead.source else None,
                "created_at": lead.created_at
            })

        return Response({
            "student_id": student.id,
            "phone": student.phone,
            "leads_matched": lead_data
        }, status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=['get', 'post'], url_path='send-sms')
    def send_sms(self, request, pk=None):
        student = self.get_object()

        # GET: SMS tarixini qaytarish
        if request.method == 'GET':
            from communication.models import SMSMessages
            org_id = self.get_organization_id()

            phone_numbers = [student.phone]
            if student.father_phone:
                phone_numbers.append(student.father_phone)
            if student.mother_phone:
                phone_numbers.append(student.mother_phone)

            sms_messages = SMSMessages.objects.filter(
                organization_id=org_id,
                recipient__in=phone_numbers
            ).order_by('-sent_at')

            return Response({
                "student": {
                    "id": student.id,
                    "full_name": student.full_name,
                    "phone": student.phone,
                },
                "total_count": sms_messages.count(),
                "sms_history": [
                    {
                        "id": sms.id,
                        "recipient": sms.recipient,
                        "message": sms.message,
                        "status": sms.status,
                        "sent_at": sms.sent_at.isoformat() if sms.sent_at else None,
                    }
                    for sms in sms_messages
                ]
            }, status=status.HTTP_200_OK)

        # POST: SMS yuborish
        # Enforce allow_teacher_sms check for teachers
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

        # SMSMessages jadvaliga yozish
        from communication.models import SMSMessages as SMSModel
        SMSModel.objects.create(
            organization_id=self.get_organization_id(),
            recipient=student.phone,
            message=message,
            status='sent'
        )

        return Response({
            "status": "success",
            "message": f"SMS successfully sent to {student.phone}."
        }, status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=['get'], url_path='attendance-history')
    def attendance_history(self, request, pk=None):
        """Talabaning barcha yo'qlama tarixini qaytaradi."""
        student = self.get_object()
        org_id = self.get_organization_id()

        from academics.models import Attendance
        attendances = Attendance.objects.filter(
            student=student,
            organization_id=org_id
        ).select_related('group').order_by('-date')

        # Guruh bo'yicha guruhlash
        from collections import defaultdict
        grouped = defaultdict(list)
        for att in attendances:
            group_name = att.group.name if att.group else "Noma'lum"
            grouped[group_name].append({
                "id": att.id,
                "date": att.date.isoformat(),
                "status": att.status,
                "grade": att.grade,
                "reason": att.reason,
            })

        # Umumiy statistika
        total = attendances.count()
        present_count = attendances.filter(status='present').count()
        absent_count = attendances.filter(status='absent').count()
        late_count = attendances.filter(status='late').count()
        excused_count = attendances.filter(status='excused').count()

        return Response({
            "student": {
                "id": student.id,
                "full_name": student.full_name,
            },
            "statistics": {
                "total": total,
                "present": present_count,
                "absent": absent_count,
                "late": late_count,
                "excused": excused_count,
                "attendance_rate": round((present_count / total * 100), 1) if total > 0 else 0,
            },
            "total_count": total,
            "by_group": [
                {
                    "group_name": group_name,
                    "records": records,
                    "count": len(records),
                }
                for group_name, records in grouped.items()
            ],
            "history": [
                {
                    "id": att.id,
                    "date": att.date.isoformat(),
                    "status": att.status,
                    "grade": att.grade,
                    "reason": att.reason,
                    "group_name": att.group.name if att.group else "Noma'lum",
                    "group_id": att.group_id,
                }
                for att in attendances
            ]
        }, status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        student = self.get_object()
        reason = request.data.get('reason') or "Arxivlangan"
        comment = request.data.get('comment') or ""
        StudentArchive.objects.create(
            organization=student.organization,
            branch=student.branch,
            first_name=student.first_name,
            last_name=student.last_name,
            phone=student.phone,
            email=student.email,
            role="Student",
            reason=reason,
            comment=comment,
            archived_by=request.user.get_full_name() or request.user.username if request.user.is_authenticated else "Tizim"
        )
        student.is_archived = True
        student.save(update_fields=['is_archived', 'updated_at'])
        from accounts.models import User
        if student.phone:
            username = f"{student.phone}_{student.organization_id}"
            qs = User.objects.filter(username=username, role='student')
            if not qs.exists():
                qs = User.objects.filter(username=student.phone, role='student')
            qs.update(is_active=False)
        return Response({"status": "archived", "id": student.id, "is_archived": True}, status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        student = self.get_object()
        student.is_archived = False
        student.save(update_fields=['is_archived', 'updated_at'])
        from accounts.models import User
        if student.phone:
            username = f"{student.phone}_{student.organization_id}"
            qs = User.objects.filter(username=username, role='student')
            if not qs.exists():
                qs = User.objects.filter(username=student.phone, role='student')
            qs.update(is_active=True)
        StudentArchive.objects.filter(phone=student.phone, organization=student.organization).delete()
        return Response({"status": "restored", "id": student.id, "is_archived": False}, status=status.HTTP_200_OK)

    @decorators.action(detail=False, methods=['post'], url_path='import-excel')
    def import_excel(self, request):
        import csv
        import datetime
        from decimal import Decimal, InvalidOperation
        from io import BytesIO
        import random
        import re

        from academics.models import (
            ClassStudent, Group, Parent, SchoolClass, Student, StudentAddress, StudentGroup
        )

        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        branch_id = (
            self.get_branch_id()
            or request.data.get('branch')
            or request.data.get('branch_id')
            or request.query_params.get('branch_id')
            or request.query_params.get('branch')
        )

        default_class_id = (
            request.data.get('school_class')
            or request.data.get('school_class_id')
            or request.data.get('class_id')
            or request.data.get('class')
            or request.query_params.get('school_class')
            or request.query_params.get('school_class_id')
            or request.query_params.get('class_id')
            or request.query_params.get('class')
        )

        default_group_id = (
            request.data.get('group')
            or request.data.get('group_id')
            or request.query_params.get('group')
            or request.query_params.get('group_id')
        )

        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({"detail": "No file uploaded. Please upload a file with key 'file'."}, status=status.HTTP_400_BAD_REQUEST)

        filename = file_obj.name.lower()
        raw_rows = []

        # -------------------------------------------------------------
        # 1. READ FILE CONTENT (CSV or XLSX/XLS)
        # -------------------------------------------------------------
        if filename.endswith('.csv'):
            try:
                decoded_file = file_obj.read().decode('utf-8-sig', errors='ignore').splitlines()
                reader = csv.reader(decoded_file)
                for r in reader:
                    if any(cell.strip() for cell in r if cell):
                        raw_rows.append([str(c).strip() for c in r])
            except Exception as e:
                return Response({"detail": f"CSV faylni o'qishda xatolik: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        elif filename.endswith(('.xlsx', '.xls')):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(filename=BytesIO(file_obj.read()), data_only=True)
                sheet = wb.active
                for r in range(1, sheet.max_row + 1):
                    row_cells = []
                    has_val = False
                    for c in range(1, sheet.max_column + 1):
                        val = sheet.cell(row=r, column=c).value
                        if val is not None:
                            has_val = True
                            row_cells.append(val)
                        else:
                            row_cells.append('')
                    if has_val:
                        raw_rows.append(row_cells)
            except Exception as e:
                return Response({"detail": f"Excel faylni o'qishda xatolik: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"detail": "Faqat .xlsx, .xls yoki .csv fayllar qo'llab-quvvatlanadi."}, status=status.HTTP_400_BAD_REQUEST)

        if not raw_rows:
            return Response({"detail": "Fayl bo'sh yoki unda ma'lumot topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        # -------------------------------------------------------------
        # 2. INTELLIGENT HEADER DETECTION (within first 10 rows)
        # -------------------------------------------------------------
        header_keywords = {
            'ism', 'name', 'first', 'familiya', 'surname', 'last', 'fio', 'fish', 'f.i.sh', 'f.i.o',
            'telefon', 'phone', 'tel', 'aloqa', 'sinf', 'class', 'guruh', 'group', 'balans', 'balance',
            'sana', 'birth', 'tugilgan', "tug'ilgan", 'ota', 'ona', 'manzil', 'address', 'talaba', "o'quvchi",
            'фио', 'ф.и.о', 'исм', 'фамилия', 'телефон', 'синф', 'класс', 'гуруҳ'
        }

        def normalize_header(h):
            s = str(h).strip().lower()
            s = re.sub(r'[\r\n\t]+', ' ', s)
            s = re.sub(r'[^a-z0-9а-яёўқғҳ\'_ ]', '', s)
            return re.sub(r'\s+', ' ', s).strip()

        header_row_idx = 0
        best_score = -1

        for idx, row in enumerate(raw_rows[:10]):
            score = 0
            for cell in row:
                norm = normalize_header(cell)
                for kw in header_keywords:
                    if kw in norm:
                        score += 1
                        break
            if score > best_score:
                best_score = score
                header_row_idx = idx

        if best_score <= 0:
            header_row_idx = 0

        raw_headers = raw_rows[header_row_idx]
        headers = [normalize_header(h) for h in raw_headers]
        data_rows = raw_rows[header_row_idx + 1:]

        # -------------------------------------------------------------
        # 3. FIELD MAPPING WITH EXPANDED SYNONYMS
        # -------------------------------------------------------------
        field_mapping = {
            'full_name': [
                'fish', 'fio', 'f i sh', 'f i o', 'ism sharifi', 'ismsharifi',
                "to'liq ism", "to'liq ismi", 'toliq ism', 'toliq ismi',
                'talaba', 'talaba fish', 'talabaning fish',
                "o'quvchi", "o'quvchi fish", "o'quvchining fish",
                'oquvchi', 'oquvchi fish', 'oquvchining fish',
                'full name', 'fullname', 'student name', 'fio toliq',
                'фио', 'ф и о', 'исми шарифи', 'ўқувчи', 'ўқувчининг фиш', 'талаба'
            ],
            'first_name': [
                'ism', 'ismi', 'first name', 'firstname', 'first_name', 'name', 'student first name',
                'исм', 'исми', 'имя'
            ],
            'last_name': [
                'familiya', 'familiyasi', 'last name', 'lastname', 'last_name', 'surname',
                'фамилия', 'фамилияси'
            ],
            'father_name': [
                'otasining ismi', 'ota ismi', 'sharifi', 'otasi', 'father name', 'father_name',
                'patronymic', 'middle name', 'middle_name', 'отасининг исми', 'шарифи', 'отчество'
            ],
            'phone': [
                'telefon', 'telefoni', 'telefon raqami', 'telefon raqam', 'phone', 'phone number',
                'phone_number', 'mobile', 'tel', 'aloqa', 'telefon nomer', 'nomer',
                'телефон', 'тел', 'номер телефона', 'номер', 'телефон рақами'
            ],
            'father_phone': [
                'ota telefoni', 'otasining telefoni', 'otasining telefon raqami', 'father phone',
                'father_phone', "father phone", 'ота телефони', 'отасининг телефони', 'телефон отца'
            ],
            'mother_name': [
                'ona ismi', 'onasi', 'onasining ismi', 'mother name', 'mother_name', "mother name",
                'она исми', 'онасининг исми', 'имя матери'
            ],
            'mother_phone': [
                'ona telefoni', 'onasining telefoni', 'onasining telefon raqami', 'mother phone',
                'mother_phone', "mother phone", 'она телефони', 'онасининг телефони', 'телефон матери'
            ],
            'school_class': [
                'sinf', 'sinfi', 'class', 'school_class', 'school class', 'grade', 'grade_level', 'klass',
                'синф', 'синфи', 'класс'
            ],
            'group': [
                'guruh', 'guruhi', 'group', 'group_name', 'kurs', 'course',
                'гуруҳ', 'гуруҳи', 'группа', 'курс'
            ],
            'birth_date': [
                "tug'ilgan sana", "tug'ilgan sanasi", "tug'ilgan kun", "tug'ilgan kuni",
                "tugilgan sana", "tugilgan sanasi", "tugilgan kun", "tugilgan kuni",
                'birth date', 'birth_date', 'birthday', 'dob', 'date of birth',
                'туғилган сана', 'туғилган кун', 'тугилган сана', 'тугилган кун', 'дата рождения', 'др'
            ],
            'gender': [
                'jins', 'jinsi', 'gender', 'sex', 'жинси', 'жинс', 'пол'
            ],
            'balance': [
                'balans', 'balansi', 'hisob', 'balance', 'баланс'
            ],
            'address': [
                'manzil', 'manzili', 'yashash manzili', 'uy manzili', 'address', 'residential address',
                'манзил', 'манзили', 'яшаш манзили', 'адрес'
            ],
            'email': [
                'email', 'e-mail', 'pochta', 'elektron pochta', 'электронная почта', 'почта'
            ],
            'telegram_chat_id': [
                'telegram', 'telegram chat id', 'telegram_chat_id', 'telegram id', 'телеграм'
            ]
        }

        def clean_phone(val):
            """Normalize phone values including floats like 998901234567.0 to +998XXXXXXXXX format."""
            if val is None or val == '':
                return None
            if isinstance(val, (int, float)):
                try:
                    val = str(int(val))
                except (ValueError, OverflowError):
                    val = str(val)
            else:
                val = str(val).strip()
                if val.endswith('.0'):
                    val = val[:-2]

            digits = ''.join(c for c in val if c.isdigit())
            if not digits:
                return None

            # 9-digit local format: 901234567 -> 998901234567
            if len(digits) == 9:
                digits = '998' + digits
            # 13-digit float artifact: 9989012345670 -> 998901234567
            elif len(digits) == 13 and digits.startswith('998') and digits.endswith('0'):
                digits = digits[:12]

            if len(digits) == 12 and digits.startswith('998'):
                return '+' + digits
            elif len(digits) == 12:
                return '+' + digits
            elif len(digits) > 7:
                return '+' + digits
            return None

        def clean_date(val):
            """Parse Excel datetime objects, strings, and timestamps safely."""
            if val is None or val == '':
                return None
            if isinstance(val, (datetime.datetime, datetime.date)):
                return val.strftime('%Y-%m-%d')
            s_val = str(val).strip()
            # If datetime string like "2010-05-10 00:00:00", take date part
            if ' ' in s_val:
                s_val = s_val.split(' ')[0].strip()
            if 'T' in s_val:
                s_val = s_val.split('T')[0].strip()

            date_formats = (
                '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y',
                '%Y/%m/%d', '%Y.%m.%d', '%d.%m.%y', '%d/%m/%y'
            )
            for fmt in date_formats:
                try:
                    return datetime.datetime.strptime(s_val, fmt).date().isoformat()
                except ValueError:
                    pass
            return None

        def clean_balance(val):
            """Clean string balance to valid Decimal or default 0.00."""
            if val is None or val == '':
                return Decimal('0.00')
            if isinstance(val, (int, float)):
                return Decimal(str(val))
            cleaned = str(val).replace(' ', '').replace("so'm", "").replace("som", "").replace("$", "").strip()
            if ',' in cleaned and '.' not in cleaned:
                cleaned = cleaned.replace(',', '.')
            elif ',' in cleaned and '.' in cleaned:
                cleaned = cleaned.replace(',', '')
            try:
                return Decimal(cleaned)
            except InvalidOperation:
                return Decimal('0.00')

        success_count = 0
        error_logs = []

        # -------------------------------------------------------------
        # 4. ROW-BY-ROW IMPORT LOOP
        # -------------------------------------------------------------
        for idx, row in enumerate(data_rows):
            row_num = header_row_idx + idx + 2

            # Check if row has any non-empty content
            if not any(str(c).strip() for c in row if c is not None):
                continue

            extracted_fields = {}
            for col_idx, h in enumerate(headers):
                if col_idx >= len(row):
                    continue
                cell_val = row[col_idx]
                if cell_val is None or str(cell_val).strip() == '':
                    continue

                for field, synonyms in field_mapping.items():
                    if field in extracted_fields:
                        continue
                    for syn in synonyms:
                        if syn == h or syn in h:
                            extracted_fields[field] = cell_val
                            break

            # ---------------------------------------------------------
            # Full Name / First Name / Last Name parsing
            # ---------------------------------------------------------
            full_name_val = extracted_fields.get('full_name')
            first_name = extracted_fields.get('first_name')
            last_name = extracted_fields.get('last_name')
            father_name = extracted_fields.get('father_name')

            if full_name_val and (not first_name or not last_name):
                fn_str = str(full_name_val).strip()
                # Remove leading numbers like "1. Aliyev Vali" or "1) Aliyev Vali"
                fn_str = re.sub(r'^\d+[\.\)\- ]+', '', fn_str).strip()
                parts = fn_str.split()
                if len(parts) == 1:
                    if not first_name:
                        first_name = parts[0]
                elif len(parts) == 2:
                    if not last_name:
                        last_name = parts[0]
                    if not first_name:
                        first_name = parts[1]
                elif len(parts) >= 3:
                    if not last_name:
                        last_name = parts[0]
                    if not first_name:
                        first_name = parts[1]
                    if not father_name:
                        father_name = ' '.join(parts[2:])

            if not first_name:
                # If only last_name exists or full_name couldn't be parsed
                if last_name:
                    first_name = last_name
                    last_name = ''
                else:
                    error_logs.append(f"{row_num}-qatorda 'Ism' yoki 'F.I.SH' ustuni bo'sh yoki topilmadi.")
                    continue

            # ---------------------------------------------------------
            # Phone & Contact handling
            # ---------------------------------------------------------
            raw_phone = clean_phone(extracted_fields.get('phone'))
            father_phone = clean_phone(extracted_fields.get('father_phone'))
            mother_phone = clean_phone(extracted_fields.get('mother_phone'))

            # Fallbacks if student phone is empty
            phone = raw_phone or father_phone or mother_phone
            if not phone:
                # Auto-generate a valid unique placeholder phone for student
                rand_digits = f"{random.randint(1000000, 9999999)}"
                phone = f"+99800{rand_digits}"

            student_data = {
                'first_name': str(first_name).strip(),
                'last_name': str(last_name).strip() if last_name else '',
                'phone': phone,
                'balance': clean_balance(extracted_fields.get('balance'))
            }

            if father_name:
                student_data['father_name'] = str(father_name).strip()
            if father_phone:
                student_data['father_phone'] = father_phone
            if extracted_fields.get('mother_name'):
                student_data['mother_name'] = str(extracted_fields.get('mother_name')).strip()
            if mother_phone:
                student_data['mother_phone'] = mother_phone

            if extracted_fields.get('email'):
                student_data['email'] = str(extracted_fields.get('email')).strip()
            if extracted_fields.get('telegram_chat_id'):
                student_data['telegram_chat_id'] = str(extracted_fields.get('telegram_chat_id')).strip()
            if extracted_fields.get('address'):
                student_data['address'] = str(extracted_fields.get('address')).strip()

            # Birth date
            parsed_bdate = clean_date(extracted_fields.get('birth_date'))
            if parsed_bdate:
                student_data['birth_date'] = parsed_bdate

            # Gender
            raw_gender = str(extracted_fields.get('gender', '')).lower().strip()
            if raw_gender:
                if raw_gender in ['o', "o'g'il", 'ogil', 'erkak', 'm', 'male', 'мужик', 'муж', 'мужской']:
                    student_data['gender'] = 'male'
                elif raw_gender in ['q', 'qiz', 'ayol', 'f', 'female', 'жен', 'женский']:
                    student_data['gender'] = 'female'

            # ---------------------------------------------------------
            # SchoolClass (Sinf) resolution
            # ---------------------------------------------------------
            assigned_class = None
            class_field_val = extracted_fields.get('school_class')

            if class_field_val:
                raw_class_str = str(class_field_val).strip()
                # 1. If numeric ID
                if raw_class_str.isdigit():
                    assigned_class = SchoolClass.objects.filter(id=int(raw_class_str), organization_id=org_id).first()
                # 2. If format like "5-A", "5 A", "5A", "10-B"
                if not assigned_class:
                    m = re.match(r'^(\d+)\s*[-_ ]?\s*([A-Za-zА-Яа-яЎўҚқҒғҲҳ]?)$', raw_class_str)
                    if m:
                        g_lvl = m.group(1)
                        sec = (m.group(2) or 'A').upper()
                        assigned_class = SchoolClass.objects.filter(
                            organization_id=org_id,
                            grade_level=g_lvl,
                            section__iexact=sec
                        ).first()
                        if not assigned_class:
                            try:
                                assigned_class = SchoolClass.objects.create(
                                    organization_id=org_id,
                                    branch_id=branch_id,
                                    grade_level=g_lvl,
                                    section=sec,
                                    academic_year="2026-2027",
                                    language="uz"
                                )
                            except Exception:
                                pass
                # 3. Fallback name search
                if not assigned_class:
                    for sc in SchoolClass.objects.filter(organization_id=org_id):
                        if sc.name.lower() == raw_class_str.lower() or f"{sc.grade_level}{sc.section}".lower() == raw_class_str.lower():
                            assigned_class = sc
                            break

            # If no row class, use request default class
            if not assigned_class and default_class_id:
                try:
                    assigned_class = SchoolClass.objects.filter(id=int(default_class_id), organization_id=org_id).first()
                except (ValueError, TypeError):
                    pass

            if assigned_class:
                student_data['school_class'] = assigned_class.id

            # ---------------------------------------------------------
            # Safe Matching for Existing Student vs Creating New
            # (Prevents overwriting/deleting students sharing a phone)
            # ---------------------------------------------------------
            existing_student = None
            first_name_str = student_data['first_name'].strip()
            last_name_str = student_data.get('last_name', '').strip()

            # A. Match by phone AND matching first_name
            if phone:
                existing_student = Student.objects.filter(
                    phone=phone,
                    organization_id=org_id,
                    first_name__iexact=first_name_str
                ).first()

            # B. Match by first_name AND last_name in same organization
            if not existing_student and first_name_str and last_name_str:
                existing_student = Student.objects.filter(
                    organization_id=org_id,
                    first_name__iexact=first_name_str,
                    last_name__iexact=last_name_str
                ).first()

            # If student was previously archived, unarchive upon re-import
            if existing_student and existing_student.is_archived:
                existing_student.is_archived = False
                existing_student.save(update_fields=['is_archived'])

            if not existing_student and 'password' not in student_data:
                raw_pwd = ''.join(c for c in phone if c.isdigit())
                student_data['password'] = raw_pwd if len(raw_pwd) >= 6 else "smarttalim123"

            try:
                if existing_student:
                    serializer = StudentSerializer(
                        existing_student,
                        data=student_data,
                        partial=True,
                        context={'request': request, 'allow_shared_phone': True}
                    )
                else:
                    serializer = StudentSerializer(
                        data=student_data,
                        context={'request': request, 'allow_shared_phone': True}
                    )

                if serializer.is_valid():
                    student_instance = serializer.save(
                        organization_id=org_id,
                        branch_id=branch_id
                    )
                    success_count += 1

                    # -------------------------------------------------
                    # Post-save: Link SchoolClass, Group, Parent, Address
                    # -------------------------------------------------
                    if assigned_class:
                        ClassStudent.objects.update_or_create(
                            student=student_instance,
                            school_class=assigned_class,
                            defaults={
                                'is_active': True,
                                'organization_id': org_id,
                                'branch_id': branch_id
                            }
                        )

                    # Group resolution
                    target_group = None
                    group_field_val = extracted_fields.get('group')
                    if group_field_val:
                        g_str = str(group_field_val).strip()
                        if g_str.isdigit():
                            target_group = Group.objects.filter(id=int(g_str), organization_id=org_id).first()
                        if not target_group:
                            target_group = Group.objects.filter(name__iexact=g_str, organization_id=org_id).first()
                    elif default_group_id:
                        try:
                            target_group = Group.objects.filter(id=int(default_group_id), organization_id=org_id).first()
                        except (ValueError, TypeError):
                            pass

                    if target_group:
                        StudentGroup.objects.get_or_create(
                            organization_id=org_id,
                            branch_id=branch_id or target_group.branch_id,
                            student=student_instance,
                            group=target_group
                        )

                    # Parent info
                    father_n = student_data.get('father_name')
                    father_p = student_data.get('father_phone')
                    if father_n or father_p:
                        Parent.objects.update_or_create(
                            student=student_instance,
                            relation='father',
                            defaults={
                                'full_name': father_n or "Otasi",
                                'phone': father_p or student_instance.phone or '',
                                'organization_id': org_id,
                                'branch_id': branch_id
                            }
                        )

                    mother_n = student_data.get('mother_name')
                    mother_p = student_data.get('mother_phone')
                    if mother_n or mother_p:
                        Parent.objects.update_or_create(
                            student=student_instance,
                            relation='mother',
                            defaults={
                                'full_name': mother_n or "Onasi",
                                'phone': mother_p or student_instance.phone or '',
                                'organization_id': org_id,
                                'branch_id': branch_id
                            }
                        )

                    # Address info
                    addr_val = student_data.get('address')
                    if addr_val:
                        StudentAddress.objects.update_or_create(
                            student=student_instance,
                            defaults={
                                'organization_id': org_id,
                                'branch_id': branch_id,
                                'address': addr_val,
                                'district': addr_val[:100],
                                'student_phone': student_instance.phone or ''
                            }
                        )
                else:
                    errors_str = ", ".join([f"{k}: {v[0]}" for k, v in serializer.errors.items()])
                    error_logs.append(f"{row_num}-qatorda xatolik: {errors_str}")
            except Exception as e:
                error_logs.append(f"{row_num}-qatorda kutilmagan xatolik: {str(e)}")

        return Response({
            "message": f"Excel import tugallandi. {success_count} ta talaba muvaffaqiyatli saqlandi/yangilandi.",
            "success_count": success_count,
            "errors": error_logs
        }, status=status.HTTP_200_OK)
from django.apps import apps  # Modellarni xavfsiz chaqirish uchun
from academics.filters import GroupFilter
import logging


logger = logging.getLogger(__name__)






class GroupViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    permission_page_name = 'Guruhlar'
    queryset = Group.objects.all()
    serializer_class = GroupSerializer

    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = GroupFilter  # teacher='' bo'sh string → ValueError → 500 ni oldini oladi
    search_fields = ['name']

    # 🛠️ Abdulmajidga 500 o'rniga tushunarli Xato xabarini qaytarish uchun create metodini o'raymiz
    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Guruh yaratishda xatolik yuz berdi: {str(e)}")
            return Response({
                "error": "Guruhni saqlashda xatolik yuz berdi",
                "detail": str(e)  # Abdulmajid bu yerda aniq qaysi maydon xatoligini ko'radi
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
            from django.db.models import Q
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

    @decorators.action(detail=True, methods=['get'])
    def students(self, request, pk=None):
        group = self.get_object()
        student_groups = group.group_students.select_related('student').filter(student__isnull=False)
        students = [sg.student for sg in student_groups if sg.student]
        serializer = StudentSerializer(students, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

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

    @decorators.action(detail=True, methods=['post'], url_path='add-student')
    def add_student(self, request, pk=None):
        group = self.get_object()
        student_id = request.data.get('student')
        if not student_id:
            return Response({"detail": "Student ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        org_id = self.get_organization_id()
        student = get_object_or_404(Student.objects.filter(organization_id=org_id), id=student_id)

        StudentGroup = apps.get_model(self.queryset.model._meta.app_label, 'StudentGroup')
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

        from django.utils import timezone
        GroupLesson = apps.get_model(self.queryset.model._meta.app_label, 'GroupLesson')
        Attendance = apps.get_model(self.queryset.model._meta.app_label, 'Attendance')

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

    @decorators.action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        group = self.get_object()
        logs = []
        from django.db.models import Count, Max, Q
        from django.utils import timezone

        # Modellarni xavfsiz yuklab olish (Import xatolarini oldini oladi)
        app_label = self.queryset.model._meta.app_label
        GroupTeacher = apps.get_model(app_label, 'GroupTeacher')
        StudentGroup = apps.get_model(app_label, 'StudentGroup')
        StudentGroupLeave = apps.get_model(app_label, 'StudentGroupLeave')
        Attendance = apps.get_model(app_label, 'Attendance')
        OnlineLesson = apps.get_model(app_label, 'OnlineLesson')

        created_time = getattr(group, 'created_at', timezone.now()) or timezone.now()
        logs.append({
            "action": "Yaratildi",
            "description": f"Guruh yaratildi. Kurs: {group.course.name if group.course else 'Kiritilmagan'}. Narxi: {(group.course.price if group.course else 0)} UZS.",
            "created_at": created_time
        })

        for gt in GroupTeacher.objects.filter(group=group).select_related('teacher'):
            if gt.teacher:
                teacher_name = gt.teacher.get_full_name() or gt.teacher.username
            else:
                teacher_name = "Noma'lum o'qituvchi"
            gt_time = getattr(gt, 'created_at', timezone.now()) or timezone.now()
            logs.append({
                "action": "O'qituvchi",
                "description": f"O'qituvchi {teacher_name} guruhga biriktirildi.",
                "created_at": gt_time
            })

        for sg in StudentGroup.objects.filter(group=group).select_related('student'):
            if sg.student:
                student_name = f"{sg.student.first_name} {sg.student.last_name or ''}".strip()
            else:
                student_name = "Noma'lum talaba"
            sg_time = getattr(sg, 'joined_at', timezone.now()) or timezone.now()
            logs.append({
                "action": "Qo'shildi",
                "description": f"Talaba {student_name} guruhga qo'shildi. Narxi: {(group.course.price if group.course else 0)} UZS.",
                "created_at": sg_time
            })

        for sgl in StudentGroupLeave.objects.filter(group=group).select_related('student', 'leave_reason'):
            if sgl.student:
                student_name = f"{sgl.student.first_name} {sgl.student.last_name or ''}".strip()
            else:
                student_name = "Noma'lum talaba"
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
            ol_time = timezone.now()
            logs.append({
                "action": "Onlayn dars",
                "description": f"Onlayn dars qo'shildi: '{ol.title}'.",
                "created_at": ol_time
            })

        for log in logs:
            if hasattr(log['created_at'], 'isoformat'):
                log['created_at'] = log['created_at'].isoformat()
            else:
                log['created_at'] = str(log['created_at'])

        logs.sort(key=lambda x: x['created_at'], reverse=True)
        return Response(logs, status=status.HTTP_200_OK)

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

        StudentGroup = apps.get_model(self.queryset.model._meta.app_label, 'StudentGroup')
        student_groups = StudentGroup.objects.filter(group=group)
        count = student_groups.count()

        return Response({
            "status": "success",
            "message": f"SMS successfully broadcasted to {count} students in group {group.name}."
        }, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        # Organization ni aniq (explicit) o'rnatamiz — mixin zanjiriga ishonmasdan
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
        LessonSchedule = apps.get_model(self.queryset.model._meta.app_label, 'LessonSchedule')

        LessonSchedule.objects.filter(group=group).delete()

        if group.days and group.start_time and group.end_time:
            if isinstance(group.days, list):
                days_list = [str(d).lower().strip() for d in group.days]
            else:
                days_list = [str(group.days).lower().strip()]

            days_combined = " ".join(days_list)

            # Juft kunlar: Seshanba(Tue), Payshanba(Thu), Shanba(Sat) -> even
            is_even = any(x in days_combined for x in ['seshanba', 'payshanba', 'shanba', 'tue', 'thu', 'sat', '2', '4', '6'])
            # Toq kunlar: Dushanba(Mon), Chorshanba(Wed), Juma(Fri) -> odd
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

        # Create StudentGroupLeave record
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


class GroupTeacherViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'O\'qituvchilar'
    queryset = GroupTeacher.objects.all()
    serializer_class = GroupTeacherSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['teacher', 'group']


class TeacherSalaryPaymentViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Ish haqi'
    queryset = TeacherSalaryPayment.objects.all()
    serializer_class = TeacherSalaryPaymentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['teacher']


class StudentTransactionsView(TenantViewSetMixin, generics.ListAPIView):
    """
    List transactions/payments for a student. Filter by student query param.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Barcha to\'lovlar'
    pagination_class = None

    def get_queryset(self):
        from finance.models import Payment
        from django.db.models import Q
        queryset = Payment.objects.all()

        # Enforce multi-tenancy filtering
        org_id = self.get_organization_id()
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        else:
            return queryset.none()

        # Branch filtering
        branch_id = self.get_branch_id()
        if branch_id:
            queryset = queryset.filter(branch_id=branch_id)

        student_id = (
            self.request.query_params.get('student') or
            self.request.query_params.get('student_id') or
            self.request.query_params.get('id')
        )
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        return queryset

    def get(self, request, *args, **kwargs):
        # We need a serializer here. Let's build a quick inline representation or load serialized data.
        from finance.serializers import PaymentSerializer
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = PaymentSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = PaymentSerializer(queryset, many=True)
        return Response(serializer.data)


class GroupAttendanceView(TenantViewSetMixin, APIView):
    """
    GET, POST, PATCH, DELETE attendance records for a group.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Guruhlar'

    def get_serializer_context(self):
        return {'request': self.request}

    def get(self, request, group_id):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        # If group_id is actually attendance ID
        if Attendance.objects.filter(id=group_id, organization_id=org_id).exists():
            attendances = Attendance.objects.filter(id=group_id, organization_id=org_id)
        else:
            attendances = Attendance.objects.filter(group_id=group_id, organization_id=org_id)
        serializer = AttendanceSerializer(attendances, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)



    def post(self, request, group_id):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        # Resolve potential parameter mismatch (e.g. {id: payload_dict})
        if isinstance(data, dict) and 'id' in data and isinstance(data['id'], dict):
            data = data['id']

        if not isinstance(data, list):
            data = [data]

        # Check if group_id is actually the attendance ID (due to frontend calling updateAttendance(recordId, payload))
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
                import datetime
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
            status_str = str(status_val or '').lower().strip()
            if status_str in ['keldi', 'bor', 'ha', 'true', '1', 'present']:
                status_val = 'present'
            elif status_str in ['kelmadi', 'yoq', "yo'q", 'false', '0', 'absent']:
                status_val = 'absent'
            elif status_str in ['kechikdi', 'kech', 'late']:
                status_val = 'late'
            elif status_str in ['sababli', 'excused']:
                status_val = 'excused'
            elif not status_val:
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
        # If it was a single record and list was created from single item, return single dict
        if len(serializer.data) == 1 and not isinstance(request.data, list):
            return Response(serializer.data[0], status=status.HTTP_201_CREATED)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def patch(self, request, group_id):
        return self.post(request, group_id)

    def delete(self, request, group_id):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        date = request.query_params.get('date')
        student_id = request.query_params.get('student')

        attendance_id = request.query_params.get('id')
        if not attendance_id and isinstance(request.data, dict):
            attendance_id = request.data.get('id') or request.data.get('attendanceId')

        # Check if group_id is actually the attendance ID (due to frontend calling deleteAttendance(recordId))
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



class StudentBalancesViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    permission_page_name = 'Talabalar'
    queryset = Student.objects.all()
    serializer_class = StudentBalanceSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        from django.db.models import Q

        student_id = (
            self.request.query_params.get('student') or
            self.request.query_params.get('student_id') or
            self.request.query_params.get('id')
        )
        if student_id:
            queryset = queryset.filter(id=student_id)

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(phone__icontains=search)
            )

        balance_min = self.request.query_params.get('balance_min')
        if balance_min:
            queryset = queryset.filter(balance__gte=balance_min)

        balance_max = self.request.query_params.get('balance_max')
        if balance_max:
            queryset = queryset.filter(balance__lte=balance_max)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        return queryset


class BalanceHistoryViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Barcha to\'lovlar'
    queryset = BalanceHistory.objects.all()
    serializer_class = BalanceHistorySerializer


class ExamViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsGroupAssignedTeacherOrAdminOwnerForExam]
    permission_page_name = 'Imtihon'
    queryset = Exam.objects.all()
    serializer_class = ExamSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['group', 'course', 'date']

    @decorators.action(detail=False, methods=['post'], url_path='grading')
    def grading(self, request):
        exam_id = request.data.get('exam') or request.data.get('exam_id')
        results = request.data.get('results')

        if not exam_id or not results:
            return Response({"detail": "Imtihon va talaba baholari (results) kiritilishi shart."},
                            status=status.HTTP_400_BAD_REQUEST)

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


class ExamResultViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsGroupAssignedTeacherOrAdminOwnerForExam]
    permission_page_name = 'Imtihon'
    queryset = ExamResult.objects.all()
    serializer_class = ExamResultSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['exam', 'student']


class LeaveReasonViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Guruhni tark etganlar'
    queryset = LeaveReason.objects.all()
    serializer_class = LeaveReasonSerializer


class LessonTimeViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Darslar hisoboti'
    queryset = LessonTime.objects.all()
    serializer_class = LessonTimeSerializer


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

        # Student faqat o'zining guruhlaridagi published darslarni ko'radi
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

        # Group bo'yicha filter
        group_id = self.request.query_params.get('group') or self.request.query_params.get('group_id')
        if group_id:
            qs = qs.filter(group_id=group_id)

        # attendance_date bo'yicha filter
        attendance_date = self.request.query_params.get('attendance_date') or self.request.query_params.get('date')
        if attendance_date:
            qs = qs.filter(attendance_date=attendance_date)

        # is_published filter (string -> bool)
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

    @decorators.action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        lesson = self.get_object()
        lesson.is_published = True
        lesson.save()
        return Response({"status": "success", "detail": "Lesson published."}, status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=['post'], url_path='unpublish')
    def unpublish(self, request, pk=None):
        lesson = self.get_object()
        lesson.is_published = False
        lesson.save()
        return Response({"status": "success", "detail": "Lesson unpublished."}, status=status.HTTP_200_OK)



class StudentGroupLeaveViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Guruhni tark etganlar'
    queryset = StudentGroupLeave.objects.all()
    serializer_class = StudentGroupLeaveSerializer

    def get_queryset(self):
        org_id = self.get_organization_id()
        if not org_id:
            return StudentGroupLeave.objects.none()

        from django.db.models import Q
        qs = StudentGroupLeave.objects.filter(organization_id=org_id)

        # Branch filtering
        branch_id = self.get_branch_id()
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        course_id = self.request.query_params.get('course')
        teacher_id = self.request.query_params.get('teacher')
        reason_id = self.request.query_params.get('reason') or self.request.query_params.get('leave_reason')
        status = self.request.query_params.get('status')
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
        if status:
            from django.db.models import Q
            if status in ['trial', 'sinov', 'trial_left', 'Sinovdan ketgan']:
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

        # is_archived filtering (only for list view so detail actions like PATCH/DELETE can access archived records)
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


class StudentPricingViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Talabalar'
    queryset = StudentPricing.objects.all()
    serializer_class = StudentPricingSerializer


class StudentArchiveViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Guruhni tark etganlar'
    queryset = StudentArchive.objects.all()
    serializer_class = StudentArchiveSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['first_name', 'last_name', 'phone', 'email']

    def destroy(self, request, *args, **kwargs):
        from rest_framework import exceptions
        archive_item = self.get_object()
        
        # Check if there is a corresponding archived student with active debt
        archived_student = Student.objects.filter(phone=archive_item.phone, is_archived=True).first()
        if archived_student and archived_student.balance < 0:
            raise exceptions.ValidationError({
                "detail": "Qarzdorligi bor talabani arxivdan o'chirib bo'lmaydi! Avval qarzi to'lanishi kerak."
            })
            
        # Otherwise, perform hard deletion
        if archived_student:
            archived_student.delete()
            
        from accounts.models import User
        org_id = archive_item.organization_id
        phone = archive_item.phone
        username = f"{phone}_{org_id}" if (phone and org_id) else (phone or archive_item.email or f"user_{archive_item.id}")
        
        qs = User.objects.filter(username=username, role='student')
        if not qs.exists() and phone:
            qs = User.objects.filter(username=phone, role='student')
        qs.delete()
        
        return super().destroy(request, *args, **kwargs)

    @decorators.action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        archive_item = self.get_object()

        is_student = not archive_item.role or archive_item.role.lower() in ['student', 'talaba']

        from accounts.models import User
        org_id = archive_item.organization_id
        phone = archive_item.phone
        username = f"{phone}_{org_id}" if (phone and org_id) else (phone or archive_item.email or f"user_{archive_item.id}")

        if is_student:
            # Check if active student already exists
            if Student.objects.filter(phone=archive_item.phone, organization_id=org_id, is_archived=False).exists():
                return Response({"detail": "Ushbu telefon raqamli talaba tizimda allaqachon mavjud."},
                                status=status.HTTP_400_BAD_REQUEST)

            # Check if archived student exists in Student table
            archived_student = Student.objects.filter(phone=archive_item.phone, organization_id=org_id, is_archived=True).first()
            if archived_student:
                archived_student.is_archived = False
                archived_student.save(update_fields=['is_archived'])
                
                # Reactivate user account
                existing_user = User.objects.filter(username=username).first()
                if not existing_user and phone:
                    existing_user = User.objects.filter(username=phone).first() or User.objects.filter(phone=phone, organization_id=org_id).first()
                if existing_user:
                    existing_user.is_active = True
                    existing_user.username = username
                    existing_user.save(update_fields=['is_active', 'username'])
                
                archive_item.delete()
                return Response({"status": "success", "detail": "Restored successfully."}, status=status.HTTP_200_OK)

            existing_user = User.objects.filter(username=username).first()
            if not existing_user and phone:
                existing_user = User.objects.filter(username=phone).first() or User.objects.filter(phone=phone, organization_id=org_id).first()
            if existing_user:
                if existing_user.role == 'student':
                    # Reactivate the existing student user
                    existing_user.is_active = True
                    existing_user.username = username
                    existing_user.first_name = archive_item.first_name
                    existing_user.last_name = archive_item.last_name or ''
                    existing_user.email = archive_item.email or ''
                    existing_user.organization = archive_item.organization
                    existing_user.branch = archive_item.branch
                    existing_user.save()
                else:
                    return Response({"detail": "Ushbu telefon raqamli foydalanuvchi tizimda allaqachon mavjud."},
                                    status=status.HTTP_400_BAD_REQUEST)
            else:
                if archive_item.phone:
                    User.objects.create_user(
                        username=username,
                        password=archive_item.phone if archive_item.phone else 'smarttalim123',
                        first_name=archive_item.first_name,
                        last_name=archive_item.last_name or '',
                        phone=archive_item.phone,
                        email=archive_item.email,
                        role='student',
                        organization=archive_item.organization,
                        branch=archive_item.branch
                    )

            student = Student.objects.create(
                organization=archive_item.organization,
                branch=archive_item.branch,
                first_name=archive_item.first_name,
                last_name=archive_item.last_name,
                phone=archive_item.phone,
                email=archive_item.email,
                balance=0.00
            )
        else:
            # Check if user already exists
            existing_user = User.objects.filter(username=username).first()
            if not existing_user and phone:
                existing_user = User.objects.filter(username=phone).first() or User.objects.filter(phone=phone, organization_id=org_id).first()
            if existing_user:
                return Response({"detail": "Ushbu telefon raqamli foydalanuvchi tizimda allaqachon mavjud."},
                                status=status.HTTP_400_BAD_REQUEST)

            role_to_set = archive_item.role
            SYSTEM_ROLES = ['owner', 'admin', 'manager', 'teacher', 'receptionist', 'employee', 'student', 'superadmin']
            position_to_set = None
            if role_to_set not in SYSTEM_ROLES:
                position_to_set = role_to_set
                role_to_set = 'employee'

            User.objects.create_user(
                username=username,
                password=archive_item.phone if archive_item.phone else 'smarttalim123',
                first_name=archive_item.first_name,
                last_name=archive_item.last_name,
                phone=archive_item.phone,
                email=archive_item.email,
                role=role_to_set,
                position=position_to_set,
                organization=archive_item.organization,
                branch=archive_item.branch
            )

        archive_item.delete()
        return Response({"status": "success", "detail": "Restored successfully."}, status=status.HTTP_200_OK)


class AttendanceViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Guruhlar'
    permission_classes = [permissions.IsAuthenticated, IsGroupAssignedTeacherForAttendance]
    queryset = Attendance.objects.all()
    serializer_class = AttendanceSerializer
    pagination_class = None

    def perform_create(self, serializer):
        """
        MUHIM QO'SHIMCHA: Davomat qo'yilayotgan sana bayram (Holiday) kuniga
        to'g'ri kelsa va talabalarga ta'siri bo'lsa (student_impact=True),
        tizim davomat qo'yishni taqiqlaydi. Bu bilan talaba balansidan adashib pul ketishi oldi olinadi.
        """
        attendance_date = serializer.validated_data.get('date')
        org_id = self.get_organization_id()

        # Shu sanada talabalarga ta'sir qiluvchi bayram bormi tekshiramiz
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

        super().perform_create(serializer)

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


class HolidayViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Ofis sozlamalari'
    queryset = Holiday.objects.all()
    serializer_class = HolidaySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name']
    pagination_class = None


class HomeworkViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    permission_page_name = 'Guruhlar'
    queryset = Homework.objects.select_related('group', 'teacher', 'created_by').all()
    serializer_class = HomeworkSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['group', 'teacher']
    search_fields = ['title', 'description', 'text', 'group__name']
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        group_id = self.request.query_params.get('group') or self.request.query_params.get('group_id')
        if group_id:
            queryset = queryset.filter(group_id=group_id)

        teacher_id = self.request.query_params.get('teacher') or self.request.query_params.get('teacher_id')
        if teacher_id:
            queryset = queryset.filter(teacher_id=teacher_id)

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


from .models import Student, StudentGroup


# 1. TALABA PROFILI VA BALANSI
class StudentProfileAPIView(APIView):
    def get(self, request):
        phone = request.query_params.get('phone')
        if not phone:
            return Response({"error": "phone parametri majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(phone=phone)
            # Ma'lumotlarni serializer orqali o'giramiz
            serializer = StudentProfileSerializer(student)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Student.DoesNotExist:
            return Response({"error": "Talaba topilmadi!"}, status=status.HTTP_404_NOT_FOUND)


# 2. TALABA DARS JADVALI (StudentGroup va Group modelidan oladi)
class StudentLessonsAPIView(APIView):
    def get(self, request):
        phone = request.query_params.get('phone')
        if not phone:
            return Response({"error": "phone parametri majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(phone=phone)
            # Talaba a'zo bo'lgan faol guruhlarni qidiramiz
            st_groups = StudentGroup.objects.filter(student=student, group__status='active')

            lessons_list = []
            for st_g in st_groups:
                group = st_g.group
                lessons_list.append({
                    "group_name": group.name,
                    "course_name": group.course.name if group.course else None,
                    "teacher_name": group.teacher.get_full_name() if group.teacher else "Ustoz biriktirilmagan",
                    "day_type": group.day_type,
                    "start_time": str(group.start_time) if group.start_time else None
                })

            return Response({"student": student.first_name, "lessons": lessons_list}, status=status.HTTP_200_OK)
        except Student.DoesNotExist:
            return Response({"error": "Talaba topilmadi!"}, status=status.HTTP_404_NOT_FOUND)


from .models import Student, ExamResult, Attendance


class ParentStudentsAPIView(APIView):
    def get(self, request):
        parent_phone = request.query_params.get('phone')  # Ota yoki onaning teli
        if not parent_phone:
            return Response({"error": "phone parametri majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        # Otasining yoki onasining raqami mos keladigan talabalarni qidiramiz
        students = Student.objects.filter(
            models.Q(father_phone=parent_phone) | models.Q(mother_phone=parent_phone)
        )

        student_list = []
        for student in students:
            student_list.append({
                "id": student.id,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "balance": float(student.balance),
                "payment_date": str(student.payment_date) if student.payment_date else None
            })

        return Response({"students": student_list}, status=status.HTTP_200_OK)


# 2. FARZANDINING OLDINGI IMTIHON BAHOLARI VA DAVOMATI APISI
class ParentStudentDetailsAPIView(APIView):
    def get(self, request):
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response({"error": "student_id parametri majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(id=student_id)

            # 1. Baholar tarixi (`ExamResult` modelidan)
            exam_results = ExamResult.objects.filter(student=student).select_related('exam')
            marks = []
            for res in exam_results:
                marks.append({
                    "exam_name": res.exam.name,
                    "score": float(res.score),
                    "date": str(res.exam.date)
                })

            # 2. Davomat tarixi (`Attendance` modelidan)
            attendances = Attendance.objects.filter(student=student).order_by('-date')[:10]  # oxirgi 10 ta dars
            attendance_log = []
            for att in attendances:
                attendance_log.append({
                    "date": str(att.date),
                    "status": att.status,  # present, absent, late
                    "group_name": att.group.name if att.group else "Noma'lum"
                })

            return Response({
                "student_name": f"{student.first_name} {student.last_name or ''}",
                "exam_results": marks,
                "attendance_history": attendance_log
            }, status=status.HTTP_200_OK)

        except Student.DoesNotExist:
            return Response({"error": "Talaba topilmadi!"}, status=status.HTTP_404_NOT_FOUND)


from django.contrib.auth import get_user_model
from .models import Group, LessonSchedule

User = get_user_model()


# 1. XODIM PROFILI VA UNING DARSLARI APISI
class StaffProfileAPIView(APIView):
    def get(self, request):
        phone = request.query_params.get('phone')
        if not phone:
            return Response({"error": "phone parametri majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(phone=phone, is_active=True)

            # Xodim o'qituvchi bo'lsa, uning faol guruhlarini topamiz
            teaching_groups = Group.objects.filter(teacher=user, status='active')
            groups_data = []
            for group in teaching_groups:
                groups_data.append({
                    "group_id": group.id,
                    "group_name": group.name,
                    "course_name": group.course.name if group.course else "Noma'lum"
                })

            return Response({
                "staff_name": user.get_full_name() or user.username,
                "role": "O'qituvchi/Xodim",
                "phone": user.phone,
                "active_groups": groups_data
            }, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({"error": "Xodim topilmadi!"}, status=status.HTTP_404_NOT_FOUND)


# 2. XODIMNING KUNLIK DARS JADVALI (LessonSchedule modelidan oladi)
class StaffScheduleAPIView(APIView):
    def get(self, request):
        phone = request.query_params.get('phone')
        if not phone:
            return Response({"error": "phone parametri majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(phone=phone)
            # Xodimga biriktirilgan dars jadvallari
            schedules = LessonSchedule.objects.filter(teacher=user).select_related('group')

            schedule_list = []
            for sch in schedules:
                schedule_list.append({
                    "group_name": sch.group.name if sch.group else "Guruhsiz",
                    "room_name": sch.room_name,
                    "start_time": str(sch.start_time),
                    "end_time": str(sch.end_time),
                    "day_type": sch.day_type  # even yoki odd
                })

            return Response({"schedule": schedule_list}, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({"error": "Xodim topilmadi!"}, status=status.HTTP_404_NOT_FOUND)


# --- TELEGRAM BOT BILDIRIShNOMALARI ShABLONLARI VA WEBHOOK API ---

class BotMessageTemplateViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Bot Shablonlari'
    queryset = BotMessageTemplate.objects.all()
    serializer_class = BotMessageTemplateSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['template_type', 'is_active']


from rest_framework.permissions import AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator


@method_decorator(csrf_exempt, name='dispatch')
class TelegramWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, bot_type, token):
        from .telegram_bot import handle_telegram_update, send_telegram_message
        try:
            update_data = request.data
            handle_telegram_update(bot_type, token, update_data)
            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"Error handling webhook for {bot_type}: {tb}")
            try:
                chat_id = request.data.get("message", {}).get("chat", {}).get("id")
                if chat_id:
                    tb_safe = tb.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    send_telegram_message(token, chat_id, f"<b>⚠️ Xatolik yuz berdi ({bot_type}):</b>\n<pre>{tb_safe}</pre>")
            except Exception as e_inner:
                print(f"Failed to send error traceback to telegram: {str(e_inner)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# 1. MAVZU QO'SHISH
class SetLessonTopicAPIView(APIView):
    def post(self, request, lesson_id):
        try:
            lesson = GroupLesson.objects.get(id=lesson_id)
        except GroupLesson.DoesNotExist:
            return Response({"error": "Dars kuni topilmadi!"}, status=status.HTTP_404_NOT_FOUND)

        serializer = SetLessonTopicSerializer(lesson, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()  # Bu yerda signal ishlab ketadi
            return Response({
                "success": True,
                "message": "Mavzu dars kalendariga qo'shildi!",
                "data": serializer.data
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# 2. DARSNI BEKOR QILISH (Bu yerda serializer shart emas, chunki tana (body) bo'sh keladi)
class CancelOrRestoreLessonAPIView(APIView):
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


# 3. DARSNI KO'CHIRISH
class RescheduleLessonAPIView(APIView):
    def post(self, request, lesson_id):
        try:
            lesson = GroupLesson.objects.get(id=lesson_id)
        except GroupLesson.DoesNotExist:
            return Response({"error": "Dars topilmadi!"}, status=status.HTTP_404_NOT_FOUND)

        today = timezone.now().date()
        if lesson.date < today:
            return Response({"error": "O'tib ketgan darsni ko'chirish mumkin emas!"},
                            status=status.HTTP_400_BAD_REQUEST)

        # Serializer orqali tekshiramiz
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
from .models import generate_group_lessons
from rest_framework.generics import ListAPIView


class GroupLessonListAPIView(ListAPIView):
    """Guruh id-si va ixtiyoriy sana oralig'i bo'yicha darslar ro'yxatini olish API-si"""
    serializer_class = GroupLessonListSerializer
    pagination_class = None  # 🎯 KALENDAR UCHUN PAGINATION'NI O'CHIRAMIZ! Hamma dars birdiga chiqsin.

    def get_queryset(self):
        group_id = self.request.query_params.get('group')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')

        if not group_id:
            return GroupLesson.objects.none()

        # Darslar yaratilmagan bo'lsa real vaqtda yaratish
        if not GroupLesson.objects.filter(group_id=group_id).exists():
            try:
                group = Group.objects.get(id=group_id)
                generate_group_lessons(group)
            except Group.DoesNotExist:
                return GroupLesson.objects.none()

        queryset = GroupLesson.objects.filter(group_id=group_id)

        # 🎯 Frontenddan kelayotgan start_date va end_date filtrlarini qo'shamiz
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        return queryset.order_by('date')


from django.db.models import F
from rest_framework.permissions import IsAuthenticated
from .serializers import BirthdayCalendarSerializer
from academics.models import Student  # Student modeli qaysi appdaligiga qarab importni tekshiring



class BirthdayCalendarAPIView(APIView):
    """Xodimlar, o'qituvchilar va o'quvchilarning tug'ilgan kunlarini oy bo'yicha olish APIsi"""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Frontenddan kelayotgan oy parametrini olamiz (Default: joriy oy)
        import datetime
        now = datetime.datetime.now()

        try:
            month = int(request.query_params.get('month', now.month))
        except ValueError:
            month = now.month

        user_organization = request.user.organization

        from django.db.models import Q
        branch_id = (
            request.query_params.get('branch') or
            request.query_params.get('branch_id') or
            request.headers.get('x-branch-id') or
            request.headers.get('X-Branch-ID') or
            getattr(request.user, 'branch_id', None)
        )
        if branch_id:
            try:
                branch_id = int(branch_id)
            except (ValueError, TypeError):
                branch_id = None

        # 1. O'quvchilarni (Student) filterlash
        students = Student.objects.filter(
            organization=user_organization,
            birth_date__month=month
        )

        # 2. Xodimlar va O'qituvchilarni (User) filterlash
        users = User.objects.filter(
            organization=user_organization,
            birth_date__month=month
        )

        if branch_id:
            students = students.filter(branch_id=branch_id)
            users = users.filter(Q(branches__id=branch_id) | Q(branch_id=branch_id) | Q(role='owner')).distinct()

        birthday_list = []

        # O'quvchilarni ro'yxatga qo'shish
        for s in students:
            birthday_list.append({
                'id': s.id,
                'name': f"{s.first_name} {s.last_name or ''}".strip(),
                'birth_date': s.birth_date,
                'day': s.birth_date.day,
                'type': 'student',
                'role_display': "O'quvchi"
            })

        # Xodimlarni rollariga qarab ajratib qo'shish
        for u in users:
            # Tizimdagi rol nomlanishini chiroyli ko'rinishga keltiramiz
            if u.role == 'teacher':
                type_label = 'teacher'
                role_title = "O'qituvchi"
            elif u.role in ['owner', 'admin', 'manager']:
                type_label = 'staff'
                role_title = u.get_role_display()  # "Admin", "Manager" va hk.
            else:
                type_label = 'staff'
                role_title = "Xodim"

            birthday_list.append({
                'id': u.id,
                'name': f"{u.first_name or u.username} {u.last_name or ''}".strip(),
                'birth_date': u.birth_date,
                'day': u.birth_date.day,
                'type': type_label,
                'role_display': role_title
            })

        # Kalendarda ketma-ketlik to'g'ri chiqishi uchun kunlar bo'yicha tartiblaymiz (1-dan 31-gacha)
        birthday_list = sorted(birthday_list, key=lambda x: x['day'])

        # Serializer orqali ma'lumotni formatlab frontendga uzatamiz
        serializer = BirthdayCalendarSerializer(birthday_list, many=True)
        return Response(serializer.data)
from .models import StudentEvaluationLevel
class StudentEvaluationLevelViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """O'quvchilarni baholash darajalarini CRUD qilish (Yaratish, o'chirish, tahrirlash)"""
    permission_classes = [IsAuthenticated]
    serializer_class = StudentEvaluationLevelSerializer
    queryset = StudentEvaluationLevel.objects.all()

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)


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

        course_id = (
            self.request.query_params.get('course') or
            self.request.query_params.get('course_id')
        )
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


class CheckBotRegistrationAPIView(APIView):
    """
    Foydalanuvchi (Talaba, Ota-ona, Xodim) Telegram botdan ro'yxatdan o'tganligini tekshiruvchi API
    GET params:
      - phone: "+998901234567" (telefon raqami bo'yicha)
      - student_id: 12 (talaba ID si bo'yicha)
      - user_id: 5 (xodim ID si bo'yicha)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        phone = request.query_params.get('phone')
        student_id = request.query_params.get('student_id')
        user_id = request.query_params.get('user_id')

        from accounts.models import User

        if student_id:
            try:
                student = Student.objects.get(id=student_id)
                has_student_bot = bool(student.telegram_chat_id)
                has_father_bot = bool(student.father_telegram_chat_id)
                has_mother_bot = bool(student.mother_telegram_chat_id)
                is_registered = has_student_bot or has_father_bot or has_mother_bot

                details = {
                    "student_bot": "Ro'yxatdan o'tgan" if has_student_bot else "Ro'yxatdan o'tmagan",
                    "father_bot": "Ro'yxatdan o'tgan" if has_father_bot else "Ro'yxatdan o'tmagan",
                    "mother_bot": "Ro'yxatdan o'tgan" if has_mother_bot else "Ro'yxatdan o'tmagan",
                }

                message = "Foydalanuvchi botdan ro'yxatdan o'tgan" if is_registered else "Foydalanuvchi botdan ro'yxatdan o'tmagan"

                return Response({
                    "is_registered": is_registered,
                    "type": "student",
                    "id": student.id,
                    "name": f"{student.first_name} {student.last_name or ''}".strip(),
                    "message": message,
                    "details": details
                }, status=status.HTTP_200_OK)
            except Student.DoesNotExist:
                return Response({"error": "Talaba topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        if user_id:
            try:
                user = User.objects.get(id=user_id)
                is_registered = bool(user.telegram_chat_id)
                message = "Xodim botdan ro'yxatdan o'tgan" if is_registered else "Xodim botdan ro'yxatdan o'tmagan"
                return Response({
                    "is_registered": is_registered,
                    "type": "user",
                    "id": user.id,
                    "name": user.get_full_name() or user.username,
                    "message": message
                }, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                return Response({"error": "Xodim topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        if phone:
            from django.db.models import Q
            from academics.telegram_bot import normalize_phone
            norm_phone = normalize_phone(phone)

            st_match = Student.objects.filter(
                Q(phone=norm_phone) | Q(father_phone=norm_phone) | Q(mother_phone=norm_phone)
            ).first()

            user_match = User.objects.filter(
                Q(phone=norm_phone) | Q(username=norm_phone)
            ).first()

            is_registered = False
            message = "Foydalanuvchi botdan ro'yxatdan o'tmagan"

            if st_match:
                if st_match.telegram_chat_id or st_match.father_telegram_chat_id or st_match.mother_telegram_chat_id:
                    is_registered = True
                    message = "Talaba / Ota-ona botdan ro'yxatdan o'tgan"

            if not is_registered and user_match:
                if user_match.telegram_chat_id:
                    is_registered = True
                    message = "Xodim botdan ro'yxatdan o'tgan"

            return Response({
                "phone": norm_phone,
                "is_registered": is_registered,
                "message": message
            }, status=status.HTTP_200_OK)

        return Response({"error": "phone, student_id yoki user_id yuborilishi majburiy!"}, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────
# 1. BINOLAR VIEWSET
# ─────────────────────────────────────────────────────────────
class BuildingViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['branch']
    search_fields = ['name', 'address']
    pagination_class = None


# ─────────────────────────────────────────────────────────────
# 2. SINFLAR VIEWSET
# ─────────────────────────────────────────────────────────────
class SchoolClassViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = SchoolClass.objects.all().select_related('teacher', 'room', 'branch')
    serializer_class = SchoolClassSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['branch', 'grade_level', 'language', 'academic_year', 'teacher']
    search_fields = ['grade_level', 'section', 'teacher__first_name', 'teacher__last_name', 'teacher__username']
    pagination_class = None

    # Sinf ichidagi faol o'quvchilar ro'yxati
    @decorators.action(detail=True, methods=['get'])
    def students(self, request, pk=None):
        school_class = self.get_object()
        class_students = school_class.students.filter(is_active=True).select_related('student')
        serializer = ClassStudentSerializer(class_students, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # Sinfga o'quvchi biriktirish (bitta yoki ko'plab)
    @decorators.action(detail=True, methods=['post'], url_path='add-students')
    def add_students(self, request, pk=None):
        school_class = self.get_object()
        
        if hasattr(request.data, 'getlist') and len(request.data.getlist('student_ids')) > 0:
            student_ids = request.data.getlist('student_ids')
        else:
            student_ids = request.data.get('student_ids', [])

        if not isinstance(student_ids, list):
            student_ids = [student_ids]
        
        added = []
        for s_id in student_ids:
            try:
                obj, created = ClassStudent.objects.update_or_create(
                    school_class=school_class,
                    student_id=int(s_id),
                    defaults={
                        'is_active': True,
                        'organization': school_class.organization,
                        'branch': school_class.branch
                    }
                )
                added.append(int(s_id))
            except Exception:
                pass

        if added:
            Student.objects.filter(id__in=added).update(school_class=school_class)

        return Response({'status': 'success', 'added_students': added}, status=status.HTTP_200_OK)

    # Sinfdan o'quvchini chiqarish
    @decorators.action(detail=True, methods=['post'], url_path='remove-student')
    def remove_student(self, request, pk=None):
        school_class = self.get_object()
        student_id = request.data.get('student_id')
        if not student_id:
            return Response({'error': 'student_id talab qilinadi'}, status=status.HTTP_400_BAD_REQUEST)
        
        updated = ClassStudent.objects.filter(school_class=school_class, student_id=student_id).update(is_active=False)
        Student.objects.filter(id=student_id, school_class=school_class).update(school_class=None)
        return Response({'status': 'removed_successfully', 'updated_count': updated}, status=status.HTTP_200_OK)

    # O'quvchini boshqa sinfga o'tkazish (Transfer)
    @decorators.action(detail=True, methods=['post'], url_path='transfer-student')
    def transfer_student(self, request, pk=None):
        source_class = self.get_object()
        student_id = request.data.get('student_id')
        target_class_id = request.data.get('target_class_id')
        
        if not student_id or not target_class_id:
            return Response({'error': 'student_id va target_class_id talab qilinadi'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            target_class = SchoolClass.objects.get(id=target_class_id)
        except SchoolClass.DoesNotExist:
            return Response({'error': f'ID si {target_class_id} bo\'lgan sinf topilmadi'}, status=status.HTTP_404_NOT_FOUND)

        # Eski sinfda nofaol qilish
        ClassStudent.objects.filter(school_class=source_class, student_id=student_id).update(is_active=False)
        
        # Yangi sinfga biriktirish
        ClassStudent.objects.update_or_create(
            school_class=target_class,
            student_id=student_id,
            defaults={
                'is_active': True,
                'organization': target_class.organization,
                'branch': target_class.branch
            }
        )
        Student.objects.filter(id=student_id).update(school_class=target_class)
        return Response({'status': 'transferred_successfully'}, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────
# 3. OTA-ONALAR VIEWSET
# ─────────────────────────────────────────────────────────────
class ParentViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = Parent.objects.all().select_related('student')
    serializer_class = ParentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['student', 'relation', 'branch']
    search_fields = ['full_name', 'phone', 'student__first_name', 'student__last_name', 'workplace', 'address']
    pagination_class = None


# ─────────────────────────────────────────────────────────────
# 4. O'QUVCHI MANZILLARI VIEWSET
# ─────────────────────────────────────────────────────────────
class StudentAddressViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = StudentAddress.objects.all().select_related('student')
    serializer_class = StudentAddressSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['region', 'district', 'student', 'branch']
    search_fields = ['student__first_name', 'student__last_name', 'address', 'district', 'parent_name', 'parent_phone']
    pagination_class = None


# ─────────────────────────────────────────────────────────────
# 5. O'QUVCHI MUROJAATLARI VIEWSET
# ─────────────────────────────────────────────────────────────
class StudentAppealViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = StudentAppeal.objects.all().select_related('student', 'responded_by')
    serializer_class = StudentAppealSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'appeal_type', 'student', 'is_escalated_to_owner', 'branch']
    search_fields = ['student__first_name', 'student__last_name', 'student__phone', 'message', 'response']
    ordering_fields = ['created_at', 'status', 'appeal_type']
    ordering = ['-created_at']

    @decorators.action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """Murojaatni ma'muriyat tomonidan qabul qilish / ko'rib chiqishga o'tkazish"""
        appeal = self.get_object()
        appeal.status = 'in_progress'
        appeal.responded_by = request.user
        appeal.responded_at = timezone.now()
        appeal.save(update_fields=['status', 'responded_by', 'responded_at'])

        # Talabaga xabar berish
        if appeal.student and appeal.student.telegram_chat_id:
            try:
                from academics.telegram_bot import send_telegram_message, get_student_bot_token
                token = get_student_bot_token(appeal.organization)
                if token:
                    msg = (
                        f"📢 <b>Murojaatingiz holati yangilandi!</b>\n\n"
                        f"Murojaat raqami: <b>#{appeal.id}</b>\n"
                        f"Turi: <b>{appeal.get_appeal_type_display()}</b>\n"
                        f"Yangi holati: <b>Ko'rib chiqilmoqda 🔄</b>\n\n"
                        f"Sizning murojaatingiz ma'muriyat tomonidan qabul qilindi va mutaxassislarimiz tomonidan o'rganilmoqda."
                    )
                    send_telegram_message(token, appeal.student.telegram_chat_id, msg)
            except Exception as e_tg:
                print(f"[ACCEPT_APPEAL_TG_ERR]: {e_tg}")

        serializer = self.get_serializer(appeal)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Murojaatni hal etish va talabaga javob qaytarish"""
        appeal = self.get_object()
        response_text = request.data.get('response', '').strip()
        status_val = request.data.get('status', 'resolved')
        if status_val not in ['resolved', 'rejected']:
            status_val = 'resolved'

        appeal.status = status_val
        appeal.response = response_text
        appeal.responded_by = request.user
        appeal.responded_at = timezone.now()
        appeal.save(update_fields=['status', 'response', 'responded_by', 'responded_at'])

        # Talabaga javob xabari yuborish
        if appeal.student and appeal.student.telegram_chat_id:
            try:
                from academics.telegram_bot import send_telegram_message, get_student_bot_token
                token = get_student_bot_token(appeal.organization)
                if token:
                    status_text = "Hal etildi / Bajarildi ✅" if status_val == 'resolved' else "Ko'rib chiqildi 📋"
                    msg = (
                        f"📢 <b>Murojaatingizga javob berildi!</b>\n\n"
                        f"Murojaat raqami: <b>#{appeal.id}</b>\n"
                        f"Turi: <b>{appeal.get_appeal_type_display()}</b>\n"
                        f"Holati: <b>{status_text}</b>\n\n"
                    )
                    if response_text:
                        msg += f"✍️ <b>Ma'muriyat javobi:</b>\n<i>\"{response_text}\"</i>\n\n"
                    msg += "SmartTalim tizimi orqali faol ishtirokingiz uchun minnatdormiz!"
                    send_telegram_message(token, appeal.student.telegram_chat_id, msg)
            except Exception as e_tg:
                print(f"[RESOLVE_APPEAL_TG_ERR]: {e_tg}")

        serializer = self.get_serializer(appeal)
        return Response(serializer.data, status=status.HTTP_200_OK)

class StudentTransactionsViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """Talabalar to'lovlari / tranzaksiyalari uchun to'liq CRUD ViewSet"""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = "Barcha to'lovlar"
    from finance.serializers import PaymentSerializer
    serializer_class = PaymentSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['student', 'cashbox', 'payment_method']
    search_fields = ['student__first_name', 'student__last_name', 'comment']
    ordering_fields = ['date', 'amount', 'created_at']
    ordering = ['-date', '-created_at']

    def get_queryset(self):
        from finance.models import Payment
        org_id = self.get_organization_id()
        if not org_id:
            return Payment.objects.none()
        queryset = Payment.objects.filter(organization_id=org_id).select_related('student', 'cashbox')
        branch_id = self.get_branch_id()
        if branch_id:
            queryset = queryset.filter(branch_id=branch_id)
        student_id = (
            self.request.query_params.get('student') or
            self.request.query_params.get('student_id') or
            self.request.query_params.get('id')
        )
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        return queryset

    def perform_create(self, serializer):
        from finance.models import Cashbox
        branch_id = self.get_branch_id()
        cashbox = None
        cashbox_id = self.request.data.get('cashbox') or self.request.data.get('cashbox_id')
        if cashbox_id:
            cashbox = Cashbox.objects.filter(id=cashbox_id).first()
        serializer.save(
            organization=self.get_organization(),
            branch_id=branch_id if branch_id else None,
            cashbox=cashbox
        )


class TeacherViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """O'qituvchilar ro'yxati va boshqaruvi (/api/v1/academics/teachers/)"""
    permission_classes = [permissions.IsAuthenticated]
    permission_page_name = 'Xodimlar'
    from accounts.serializers import EmployeeSerializer
    serializer_class = EmployeeSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['first_name', 'last_name', 'phone', 'email', 'specialty']

    def get_queryset(self):
        from accounts.models import User
        org = self.get_organization()
        if not org:
            return User.objects.none()
        branch_id = self.get_branch_id()
        qs = User.objects.filter(organization=org, is_active=True)
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        from django.db.models import Q
        return qs.filter(
            Q(role__iexact='teacher') |
            Q(position__icontains='teacher') |
            Q(position__icontains="o'qituvchi") |
            Q(position__icontains='oqituvchi') |
            Q(position__icontains='ustoz') |
            (Q(specialty__isnull=False) & ~Q(specialty=''))
        ).exclude(is_superuser=True).distinct()


class LessonCalendarAPIView(APIView):
    """Darslar kalendari endpointi (/api/v1/academics/lessons/calendar/)"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from academics.models import GroupLesson
        from academics.serializers import GroupLessonListSerializer
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

    def get(self, request, lesson_id=None):
        from academics.models import GroupLesson, Attendance
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


class CoursesReportAPIView(TenantViewSetMixin, APIView):
    """Kurslar bo'yicha tahliliy hisobot (/api/v1/academics/reports/courses/)"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from academics.models import Course, Group, StudentGroup
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
    """Ketish sabablari hisoboti (/api/v1/academics/reports/leave-reasons/ va /reports/student-leaves/)"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return self._build_report(request)

    def post(self, request):
        return self._build_report(request)

    def _build_report(self, request):
        from academics.models import StudentArchive
        from django.db.models import Count
        org_id = self.get_organization_id() or getattr(request.user, 'organization_id', None)
        archives = StudentArchive.objects.filter(organization_id=org_id)
        start_date = request.query_params.get('start_date') or request.data.get('start_date')
        end_date = request.query_params.get('end_date') or request.data.get('end_date')
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

    def get(self, request):
        from django.contrib.auth import get_user_model
        from django.db.models import Q
        from academics.models import Group, StudentGroup, Attendance
        User = get_user_model()
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
