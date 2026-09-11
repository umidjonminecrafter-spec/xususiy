import datetime
import traceback
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import IsAdminOrOwnerOrReadOnly
from academics.models import (
    Student, Group, StudentGroup, ExamResult, Attendance,
    LessonSchedule, BotMessageTemplate, TelegramVerification
)
from academics.serializers import (
    BotMessageTemplateSerializer, StudentProfileSerializer, BirthdayCalendarSerializer
)
from academics.utills import send_telegram_verification_code
from common.utils import normalize_uz_phone

User = get_user_model()


class SendCodeAPIView(APIView):
    permission_classes = (permissions.AllowAny,)

    @extend_schema(
        summary="Telegram orqali tasdiqlash kodini yuborish",
        description="Foydalanuvchi telefon raqamiga Telegram bot orqali ro'yxatdan o'tish ('register') yoki parolni tiklash ('forgot') uchun tasdiqlash kodini yuboradi.",
        request=inline_serializer(
            name='SendCodeRequest',
            fields={
                'phone': serializers.CharField(help_text="Telefon raqami (masalan, +998901234567)"),
                'purpose': serializers.ChoiceField(choices=['register', 'forgot'], help_text="Yuborish maqsadi"),
            }
        ),
        responses={
            200: inline_serializer(name='SendCodeSuccessResponse', fields={'message': serializers.CharField()}),
            400: inline_serializer(name='SendCodeErrorResponse', fields={'error': serializers.CharField()}),
        }
    )
    def post(self, request):
        phone = request.data.get('phone')
        purpose = request.data.get('purpose')

        if not phone or not purpose:
            return Response({"error": "phone va purpose maydonlari majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        if purpose not in ['register', 'forgot']:
            return Response({"error": "Purpose noto'g'ri!"}, status=status.HTTP_400_BAD_REQUEST)

        result = send_telegram_verification_code(phone, purpose)
        if result["status"]:
            return Response({"message": result["message"]}, status=status.HTTP_200_OK)
        return Response({"error": result["message"]}, status=status.HTTP_400_BAD_REQUEST)


class VerifyCodeAPIView(APIView):
    permission_classes = (permissions.AllowAny,)

    @extend_schema(
        summary="Tasdiqlash kodini tekshirish va parolni yangilash",
        description="Telegram bot orqali yuborilgan 6 xonali kodni tekshiradi. 'forgot' maqsadi uchun yangi parolni ham o'rnatadi.",
        request=inline_serializer(
            name='VerifyCodeRequest',
            fields={
                'phone': serializers.CharField(help_text="Telefon raqami"),
                'code': serializers.CharField(help_text="6 xonali tasdiqlash kodi"),
                'purpose': serializers.ChoiceField(choices=['register', 'forgot'], help_text="Maqsad"),
                'password': serializers.CharField(required=False, help_text="Yangi parol (ixtiyoriy)"),
                'new_password': serializers.CharField(required=False, help_text="Yangi parol muqobil maydoni"),
            }
        ),
        responses={
            200: inline_serializer(name='VerifyCodeSuccessResponse', fields={'status': serializers.CharField(), 'message': serializers.CharField()}),
            400: inline_serializer(name='VerifyCodeErrorResponse', fields={'error': serializers.CharField()}),
        }
    )
    def post(self, request):
        phone = request.data.get('phone')
        code = request.data.get('code')
        purpose = request.data.get('purpose')
        new_password = request.data.get('password') or request.data.get('new_password')

        if not phone or not code or not purpose:
            return Response({"error": "Barcha maydonlar majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        formatted_phone = normalize_uz_phone(phone) or phone
        cleaned = ''.join(c for c in str(phone) if c.isdigit())

        verif = TelegramVerification.objects.filter(
            phone__in=[phone, cleaned, formatted_phone], code=code, purpose=purpose
        ).order_by('id').last()

        if verif and verif.is_valid():
            verif.is_verified = True
            verif.save()

            if purpose == 'forgot':
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

            elif purpose == 'register':
                return Response({"status": "success", "message": "Kod tasdiqlandi. Ro'yxatdan o'tish yakunlandi."},
                                status=status.HTTP_200_OK)

        return Response({"error": "Tasdiqlash kodi noto'g'ri yoki vaqti o'tib ketgan!"},
                        status=status.HTTP_400_BAD_REQUEST)


class StudentProfileAPIView(APIView):
    @extend_schema(
        summary="Talaba profili ma'lumotlarini olish (Bot uchun)",
        description="Telefon raqami bo'yicha talabaning profil ma'lumotlarini (ism, familiya, balans, guruhlar) qaytaradi.",
        parameters=[
            OpenApiParameter('phone', OpenApiTypes.STR, required=True, description="Talaba telefon raqami")
        ],
        responses={
            200: StudentProfileSerializer,
            400: inline_serializer(name='StudentProfileError', fields={'error': serializers.CharField()}),
            404: inline_serializer(name='StudentProfileNotFound', fields={'error': serializers.CharField()})
        }
    )
    def get(self, request):
        phone = request.query_params.get('phone')
        if not phone:
            return Response({"error": "phone parametri majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(phone=phone)
            serializer = StudentProfileSerializer(student)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Student.DoesNotExist:
            return Response({"error": "Talaba topilmadi!"}, status=status.HTTP_404_NOT_FOUND)


class StudentLessonsAPIView(APIView):
    @extend_schema(
        summary="Talabaning darslari ro'yxatini olish (Bot uchun)",
        description="Talabaning faol guruhlari, kurs nomi, o'qituvchisi va dars vaqtlari ro'yxatini qaytaradi.",
        parameters=[
            OpenApiParameter('phone', OpenApiTypes.STR, required=True, description="Talaba telefon raqami")
        ],
        responses={
            200: inline_serializer(
                name='StudentLessonsResponse',
                fields={
                    'student': serializers.CharField(),
                    'lessons': serializers.ListField(child=serializers.DictField())
                }
            ),
            404: inline_serializer(name='StudentLessonsNotFound', fields={'error': serializers.CharField()})
        }
    )
    def get(self, request):
        phone = request.query_params.get('phone')
        if not phone:
            return Response({"error": "phone parametri majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(phone=phone)
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


class ParentStudentsAPIView(APIView):
    @extend_schema(
        summary="Ota-onaga tegishli talabalar ro'yxatini olish (Bot uchun)",
        description="Ota-ona telefon raqami (ota yoki ona telefoni) bo'yicha bog'langan barcha farzandlar ro'yxati, ularning ID va joriy balanslarini qaytaradi.",
        parameters=[
            OpenApiParameter('phone', OpenApiTypes.STR, required=True, description="Ota yoki ona telefon raqami")
        ],
        responses={
            200: inline_serializer(
                name='ParentStudentsResponse',
                fields={'students': serializers.ListField(child=serializers.DictField())}
            ),
            400: inline_serializer(name='ParentStudentsError', fields={'error': serializers.CharField()})
        }
    )
    def get(self, request):
        parent_phone = request.query_params.get('phone')
        if not parent_phone:
            return Response({"error": "phone parametri majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        students = Student.objects.filter(
            Q(father_phone=parent_phone) | Q(mother_phone=parent_phone)
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


class ParentStudentDetailsAPIView(APIView):
    @extend_schema(
        summary="Farzandning imtihon va davomat tarixi (Bot uchun)",
        description="Talaba ID bo'yicha uning imtihon baholari va oxirgi 10 ta davomat yozuvlari tarixini qaytaradi.",
        parameters=[
            OpenApiParameter('student_id', OpenApiTypes.INT, required=True, description="Talaba ID raqami")
        ],
        responses={
            200: inline_serializer(
                name='ParentStudentDetailsResponse',
                fields={
                    'student_name': serializers.CharField(),
                    'exam_results': serializers.ListField(child=serializers.DictField()),
                    'attendance_history': serializers.ListField(child=serializers.DictField()),
                }
            ),
            400: inline_serializer(name='ParentStudentDetailsError', fields={'error': serializers.CharField()}),
            404: inline_serializer(name='ParentStudentDetailsNotFound', fields={'error': serializers.CharField()})
        }
    )
    def get(self, request):
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response({"error": "student_id parametri majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(id=student_id)
            exam_results = ExamResult.objects.filter(student=student).select_related('exam')
            marks = []
            for res in exam_results:
                marks.append({
                    "exam_name": res.exam.name,
                    "score": float(res.score),
                    "date": str(res.exam.date)
                })

            attendances = Attendance.objects.filter(student=student).order_by('-date')[:10]
            attendance_log = []
            for att in attendances:
                attendance_log.append({
                    "date": str(att.date),
                    "status": att.status,
                    "group_name": att.group.name if att.group else "Noma'lum"
                })

            return Response({
                "student_name": f"{student.first_name} {student.last_name or ''}",
                "exam_results": marks,
                "attendance_history": attendance_log
            }, status=status.HTTP_200_OK)
        except Student.DoesNotExist:
            return Response({"error": "Talaba topilmadi!"}, status=status.HTTP_404_NOT_FOUND)


class StaffProfileAPIView(APIView):
    @extend_schema(
        summary="Xodim / O'qituvchi profili (Bot uchun)",
        description="Telefon raqami bo'yicha xodim yoki o'qituvchining ma'lumotlari va faol o'qitayotgan guruhlarini qaytaradi.",
        parameters=[
            OpenApiParameter('phone', OpenApiTypes.STR, required=True, description="Xodim telefon raqami")
        ],
        responses={
            200: inline_serializer(
                name='StaffProfileResponse',
                fields={
                    'staff_name': serializers.CharField(),
                    'role': serializers.CharField(),
                    'phone': serializers.CharField(),
                    'active_groups': serializers.ListField(child=serializers.DictField()),
                }
            ),
            400: inline_serializer(name='StaffProfileError', fields={'error': serializers.CharField()}),
            404: inline_serializer(name='StaffProfileNotFound', fields={'error': serializers.CharField()})
        }
    )
    def get(self, request):
        phone = request.query_params.get('phone')
        if not phone:
            return Response({"error": "phone parametri majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(phone=phone, is_active=True)
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


class StaffScheduleAPIView(APIView):
    @extend_schema(
        summary="O'qituvchi dars jadvali (Bot uchun)",
        description="Telefon raqami bo'yicha o'qituvchining haftalik dars jadvalini (guruh, xona, boshlanish va tugash vaqti, juft/toq kun) qaytaradi.",
        parameters=[
            OpenApiParameter('phone', OpenApiTypes.STR, required=True, description="O'qituvchi telefon raqami")
        ],
        responses={
            200: inline_serializer(
                name='StaffScheduleResponse',
                fields={'schedule': serializers.ListField(child=serializers.DictField())}
            ),
            400: inline_serializer(name='StaffScheduleError', fields={'error': serializers.CharField()}),
            404: inline_serializer(name='StaffScheduleNotFound', fields={'error': serializers.CharField()})
        }
    )
    def get(self, request):
        phone = request.query_params.get('phone')
        if not phone:
            return Response({"error": "phone parametri majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(phone=phone)
            schedules = LessonSchedule.objects.filter(teacher=user).select_related('group')
            schedule_list = []
            for sch in schedules:
                schedule_list.append({
                    "group_name": sch.group.name if sch.group else "Guruhsiz",
                    "room_name": sch.room_name,
                    "start_time": str(sch.start_time),
                    "end_time": str(sch.end_time),
                    "day_type": sch.day_type
                })
            return Response({"schedule": schedule_list}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "Xodim topilmadi!"}, status=status.HTTP_404_NOT_FOUND)


@extend_schema_view(
    list=extend_schema(
        summary="Bot xabar shablonlari ro'yxati",
        description="Telegram bot orqali yuboriladigan xabar shablonlari (tabrik, eslatma, ogohlantirish) ro'yxatini qaytaradi."
    ),
    create=extend_schema(
        summary="Yangi bot xabar shablonini yaratish",
        description="Yangi xabar shabloni matni va turini saqlaydi."
    ),
    retrieve=extend_schema(
        summary="Bot xabar shabloni tafsiloti",
        description="ID bo'yicha bot xabar shablonini ko'rish."
    ),
    update=extend_schema(
        summary="Bot xabar shablonini to'liq yangilash",
        description="Mavjud shablon matnini yoki holatini yangilash."
    ),
    partial_update=extend_schema(
        summary="Bot xabar shablonini qisman yangilash",
        description="Shablonning ayrim maydonlarini tahrirlash."
    ),
    destroy=extend_schema(
        summary="Bot xabar shablonini o'chirish",
        description="Tanlangan shablonni bazadan o'chirish."
    ),
)
class BotMessageTemplateViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Bot Shablonlari'
    queryset = BotMessageTemplate.objects.all()
    serializer_class = BotMessageTemplateSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['template_type', 'is_active']


@method_decorator(csrf_exempt, name='dispatch')
class TelegramWebhookView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Telegram Webhook qabul qiluvchi endpoint",
        description="Telegram botidan kelgan Update obyektlarini qabul qilib, tegishli bot logikasiga yo'naltiradi.",
        parameters=[
            OpenApiParameter('bot_type', OpenApiTypes.STR, location=OpenApiParameter.PATH, description="Bot turi (masalan: auth, student, parent, staff)"),
            OpenApiParameter('token', OpenApiTypes.STR, location=OpenApiParameter.PATH, description="Bot maxfiy webhook tokeni"),
        ],
        request=inline_serializer(name='TelegramWebhookPayload', fields={'update_id': serializers.IntegerField()}),
        responses={
            200: inline_serializer(name='TelegramWebhookSuccess', fields={'status': serializers.CharField()}),
            400: inline_serializer(name='TelegramWebhookError', fields={'error': serializers.CharField()})
        }
    )
    def post(self, request, bot_type, token):
        from academics.telegram_bot import handle_telegram_update, send_telegram_message
        try:
            update_data = request.data
            handle_telegram_update(bot_type, token, update_data)
            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        except Exception as e:
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


class BirthdayCalendarAPIView(APIView):
    """Xodimlar, o'qituvchilar va o'quvchilarning tug'ilgan kunlarini oy bo'yicha olish APIsi"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Tug'ilgan kunlar taqvimi",
        description="Ko'rsatilgan oy bo'yicha barcha xodimlar, o'qituvchilar va talabalarning tug'ilgan kunlari ro'yxatini tartiblangan holda qaytaradi.",
        parameters=[
            OpenApiParameter('month', OpenApiTypes.INT, description="Oy raqami (1-12). Standart holatda joriy oy olinadi.")
        ],
        responses={200: BirthdayCalendarSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        now = datetime.datetime.now()
        try:
            month = int(request.query_params.get('month', now.month))
        except ValueError:
            month = now.month

        user_organization = request.user.organization
        students = Student.objects.filter(organization=user_organization, birth_date__month=month)
        users = User.objects.filter(organization=user_organization, birth_date__month=month)

        birthday_list = []
        for s in students:
            birthday_list.append({
                'id': s.id,
                'name': f"{s.first_name} {s.last_name or ''}".strip(),
                'birth_date': s.birth_date,
                'day': s.birth_date.day,
                'type': 'student',
                'role_display': "O'quvchi"
            })

        for u in users:
            if u.role == 'teacher':
                type_label = 'teacher'
                role_title = "O'qituvchi"
            elif u.role in ['owner', 'admin', 'manager']:
                type_label = 'staff'
                role_title = u.get_role_display()
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

        birthday_list = sorted(birthday_list, key=lambda x: x['day'])
        serializer = BirthdayCalendarSerializer(birthday_list, many=True)
        return Response(serializer.data)


class CheckBotRegistrationAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Bot orqali ro'yxatdan o'tganlik holatini tekshirish",
        description="Telefon raqam, student_id yoki user_id orqali foydalanuvchining Telegram botdan ro'yxatdan o'tganligi va chat_id mavjudligini tekshiradi.",
        parameters=[
            OpenApiParameter('phone', OpenApiTypes.STR, description="Telefon raqami"),
            OpenApiParameter('student_id', OpenApiTypes.INT, description="Talaba ID"),
            OpenApiParameter('user_id', OpenApiTypes.INT, description="Foydalanuvchi/Xodim ID"),
        ],
        responses={
            200: inline_serializer(
                name='CheckBotRegistrationResponse',
                fields={
                    'is_registered': serializers.BooleanField(),
                    'message': serializers.CharField(),
                    'details': serializers.DictField(required=False)
                }
            ),
            400: inline_serializer(name='CheckBotRegistrationError', fields={'error': serializers.CharField()}),
            404: inline_serializer(name='CheckBotRegistrationNotFound', fields={'error': serializers.CharField()})
        }
    )
    def get(self, request):
        phone = request.query_params.get('phone')
        student_id = request.query_params.get('student_id')
        user_id = request.query_params.get('user_id')

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
