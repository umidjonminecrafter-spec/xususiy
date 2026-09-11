from rest_framework import viewsets, permissions, status, decorators, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate, get_user_model
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, inline_serializer
from drf_spectacular.types import OpenApiTypes

from common.utils import normalize_uz_phone
from organizations.models import Organization, Branch, Tariff, Subscription, ExamSetting, ReceiptSetting, BackupSetting, \
    TelegramNotificationSetting, LessonNotificationTemplate
from organizations.mixins import TenantViewSetMixin
from organizations.permissions import HasOrganizationPagePermission
from organizations.serializers import (
    OrganizationSerializer, BranchSerializer, TariffSerializer, SubscriptionSerializer, ExamSettingSerializer,
    ReceiptSettingSerializer, BackupSettingSerializer,
    TelegramNotificationSettingSerializer, LessonNotificationTemplateSerializer
)
from organizations.backup import run_backup_for_setting
from accounts.serializers import UserSerializer
from .serializers import GlobalSearchSerializer

User = get_user_model()


@extend_schema_view(
    list=extend_schema(summary="Tashkilotlar ro'yxati (Foydalanuvchining o'z tashkiloti)", tags=['Organizations & Settings']),
    create=extend_schema(summary="Yangi tashkilot yaratish", tags=['Organizations & Settings']),
    retrieve=extend_schema(summary="Tashkilot tafsilotlari", tags=['Organizations & Settings']),
    update=extend_schema(summary="Tashkilot ma'lumotlarini to'liq yangilash", tags=['Organizations & Settings']),
    partial_update=extend_schema(summary="Tashkilot ma'lumotlarini qisman yangilash", tags=['Organizations & Settings']),
    destroy=extend_schema(summary="Tashkilotni o'chirish", tags=['Organizations & Settings']),
)
class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = (permissions.IsAuthenticated, HasOrganizationPagePermission)
    permission_page_name = 'Sozlamalar'
    allow_without_organization = True

    def get_queryset(self):
        """Users can only see their own organization."""
        user = self.request.user
        if user.is_authenticated and getattr(user, 'organization_id', None):
            return Organization.objects.filter(id=user.organization_id)
        return Organization.objects.none()

    def perform_create(self, serializer):
        org = serializer.save()
        user = self.request.user
        if user.is_authenticated and not user.organization:
            user.organization = org
            user.role = 'owner'
            user.save()

        # Auto-create active Premium Subscription for the new organization
        import datetime
        from organizations.models import Subscription, Tariff
        default_tariff = Tariff.objects.filter(name__iexact='Premium').first() or Tariff.objects.first()
        today = datetime.date.today()
        Subscription.objects.get_or_create(
            organization=org,
            defaults={
                'tariff': default_tariff,
                'start_date': today,
                'end_date': today + datetime.timedelta(days=365),
                'is_active': False,
                'balance': 0.00
            }
        )

    @extend_schema(
        summary="Tashkilot umumiy sozlamalari (Ko'rish / Yangilash)",
        tags=['Organizations & Settings'],
        request=OrganizationSerializer,
        responses={200: OrganizationSerializer}
    )
    @decorators.action(detail=False, methods=['get', 'put', 'patch'], url_path='settings')
    def organization_general_settings(self, request):
        user = request.user
        if not user.is_authenticated or not getattr(user, 'organization', None):
            return Response({"detail": "Foydalanuvchiga tegishli tashkilot topilmadi."},
                            status=status.HTTP_400_BAD_REQUEST)

        organization = user.organization
        if request.method in ['PUT', 'PATCH']:
            # Support parsing multipart form data (like logo files)
            serializer = OrganizationSerializer(organization, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer = OrganizationSerializer(organization)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Imtihon sozlamalari (Ko'rish / Yangilash)",
        tags=['Organizations & Settings'],
        request=ExamSettingSerializer,
        responses={200: ExamSettingSerializer}
    )
    @decorators.action(detail=False, methods=['get', 'put'], url_path='exam-settings')
    def exam_settings(self, request):
        user = request.user
        if not user.is_authenticated or not getattr(user, 'organization', None):
            return Response({"detail": "Foydalanuvchiga tegishli tashkilot topilmadi."},
                            status=status.HTTP_400_BAD_REQUEST)

        organization = user.organization
        setting, created = ExamSetting.objects.get_or_create(organization=organization)

        if request.method == 'PUT':
            serializer = ExamSettingSerializer(setting, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer = ExamSettingSerializer(setting)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Kvitansiya / Chek sozlamalari (Ko'rish / Yangilash)",
        tags=['Organizations & Settings'],
        request=ReceiptSettingSerializer,
        responses={200: ReceiptSettingSerializer}
    )
    @decorators.action(detail=False, methods=['get', 'put'], url_path='receipt-settings')
    def receipt_settings(self, request):
        user = request.user
        if not user.is_authenticated or not getattr(user, 'organization', None):
            return Response({"detail": "Foydalanuvchiga tegishli tashkilot topilmadi."},
                            status=status.HTTP_400_BAD_REQUEST)

        organization = user.organization
        setting, created = ReceiptSetting.objects.get_or_create(organization=organization)

        if request.method == 'PUT':
            # Handle multipart/form-data with file uploads
            serializer = ReceiptSettingSerializer(setting, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer = ReceiptSettingSerializer(setting)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Zaxira nusxalash (Backup) sozlamalari (Ko'rish / Yangilash)",
        tags=['Organizations & Settings'],
        request=BackupSettingSerializer,
        responses={200: BackupSettingSerializer}
    )
    @decorators.action(detail=False, methods=['get', 'put'], url_path='backup-settings')
    def backup_settings(self, request):
        user = request.user
        if not user.is_authenticated or not getattr(user, 'organization', None):
            return Response({"detail": "Foydalanuvchiga tegishli tashkilot topilmadi."},
                            status=status.HTTP_400_BAD_REQUEST)

        organization = user.organization
        setting, created = BackupSetting.objects.get_or_create(organization=organization)

        if request.method == 'PUT':
            serializer = BackupSettingSerializer(setting, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer = BackupSettingSerializer(setting)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Zaxiralashni hozir ishga tushirish (Telegram / Cloud)",
        tags=['Organizations & Settings'],
        responses={200: OpenApiTypes.OBJECT}
    )
    @decorators.action(detail=False, methods=['post'], url_path='backup-now')
    def backup_now(self, request):
        user = request.user
        if not user.is_authenticated or not getattr(user, 'organization', None):
            return Response({"detail": "Foydalanuvchiga tegishli tashkilot topilmadi."},
                            status=status.HTTP_400_BAD_REQUEST)

        organization = user.organization
        setting, created = BackupSetting.objects.get_or_create(organization=organization)

        success, message = run_backup_for_setting(setting)
        if success:
            return Response({"detail": "Zaxira nusxasi muvaffaqiyatli yuborildi! ✅"}, status=status.HTTP_200_OK)
        else:
            return Response({"detail": f"Zaxiralashda xatolik yuz berdi: {message}"},
                            status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Tashkilot ma'lumotlari zaxirasini yuklab olish (ZIP formatda)",
        tags=['Organizations & Settings'],
        responses={200: OpenApiTypes.BINARY}
    )
    @decorators.action(detail=False, methods=['get'], url_path='backup-download')
    def backup_download(self, request):
        user = request.user
        if not user.is_authenticated or not getattr(user, 'organization', None):
            return Response({"detail": "Foydalanuvchiga tegishli tashkilot topilmadi."},
                            status=status.HTTP_400_BAD_REQUEST)

        organization = user.organization

        from django.apps import apps
        from django.core import serializers as django_serializers
        from django.http import HttpResponse
        import json
        import datetime
        import zipfile
        import io

        # 1. Gather tenant data
        backup_data = []
        for model in apps.get_models():
            field_names = [f.name for f in model._meta.fields]
            if 'organization' in field_names:
                try:
                    queryset = model.objects.filter(organization_id=organization.id)
                    if queryset.exists():
                        serialized_str = django_serializers.serialize('json', queryset)
                        serialized_list = json.loads(serialized_str)
                        backup_data.extend(serialized_list)
                except Exception as e:
                    print(f"Error serializing model {model.__name__} in manual download: {str(e)}")

        if not backup_data:
            return Response({"detail": "Zaxiralash uchun hech qanday ma'lumot topilmadi."},
                            status=status.HTTP_400_BAD_REQUEST)

        # 2. Build filenames
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        org_name_clean = "".join(c for c in organization.name if c.isalnum() or c in (' ', '_', '-')).strip().replace(
            ' ', '_')
        json_filename = f"backup_{org_name_clean}_{timestamp}.json"
        zip_filename = f"backup_{org_name_clean}_{timestamp}.zip"

        try:
            # 3. Create ZIP in memory
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                json_data = json.dumps(backup_data, ensure_ascii=False, indent=2)
                zip_file.writestr(json_filename, json_data)

            # 4. Stream response
            zip_buffer.seek(0)
            response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
            return response
        except Exception as e:
            return Response({"detail": f"Zaxira faylini yaratishda xatolik: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        summary="Telegram bildirishnoma sozlamalari (Ko'rish / Yangilash)",
        tags=['Organizations & Settings'],
        request=TelegramNotificationSettingSerializer,
        responses={200: TelegramNotificationSettingSerializer}
    )
    @decorators.action(detail=False, methods=['get', 'put'], url_path='telegram-settings')
    def telegram_settings(self, request):
        user = request.user
        if not user.is_authenticated or not getattr(user, 'organization', None):
            return Response({"detail": "Foydalanuvchiga tegishli tashkilot topilmadi."},
                            status=status.HTTP_400_BAD_REQUEST)

        organization = user.organization
        setting, created = TelegramNotificationSetting.objects.get_or_create(organization=organization)

        if request.method == 'PUT':
            serializer = TelegramNotificationSettingSerializer(setting, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer = TelegramNotificationSettingSerializer(setting)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Dars xabarnomalari shablonlari ro'yxati va yaratish",
        tags=['Organizations & Settings'],
        request=LessonNotificationTemplateSerializer,
        responses={200: LessonNotificationTemplateSerializer(many=True), 201: LessonNotificationTemplateSerializer}
    )
    @decorators.action(detail=False, methods=['get', 'post'], url_path='lesson-templates')
    def lesson_templates(self, request):
        user = request.user
        if not user.is_authenticated or not getattr(user, 'organization', None):
            return Response({"detail": "Tashkilot topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        organization = user.organization

        if request.method == 'GET':
            templates = LessonNotificationTemplate.objects.filter(organization=organization)
            serializer = LessonNotificationTemplateSerializer(templates, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        if request.method == 'POST':
            serializer = LessonNotificationTemplateSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(organization=organization)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Dars xabarnomasi shabloni tafsiloti, yangilash va o'chirish",
        parameters=[OpenApiParameter('template_id', OpenApiTypes.INT, location=OpenApiParameter.PATH, description="Shablon ID")],
        tags=['Organizations & Settings'],
        request=LessonNotificationTemplateSerializer,
        responses={200: LessonNotificationTemplateSerializer, 204: None}
    )
    @decorators.action(detail=False, methods=['put', 'patch', 'delete'],
                       url_path='lesson-templates/(?P<template_id>[^/.]+)')
    def lesson_template_detail(self, request, template_id=None):
        user = request.user
        if not user.is_authenticated or not getattr(user, 'organization', None):
            return Response({"detail": "Tashkilot topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            template = LessonNotificationTemplate.objects.get(id=template_id, organization=user.organization)
        except LessonNotificationTemplate.DoesNotExist:
            return Response({"detail": "Shablon topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        if request.method in ['PUT', 'PATCH']:
            serializer = LessonNotificationTemplateSerializer(template, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if request.method == 'DELETE':
            template.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Telegram bot integratsiyasini test xabari orqali tekshirish",
        tags=['Organizations & Settings'],
        responses={200: OpenApiTypes.OBJECT}
    )
    @decorators.action(detail=False, methods=['post'], url_path='telegram-test')
    def telegram_test(self, request):
        user = request.user
        if not user.is_authenticated or not getattr(user, 'organization', None):
            return Response({"detail": "Foydalanuvchiga tegishli tashkilot topilmadi."},
                            status=status.HTTP_400_BAD_REQUEST)

        organization = user.organization
        setting = TelegramNotificationSetting.objects.filter(organization=organization).first()
        if not setting or not setting.bot_token or not setting.chat_ids:
            return Response(
                {"detail": "Telegram bot sozlamalari to'liq emas. Bot token va Chat ID kiritilganligini tekshiring."},
                status=status.HTTP_400_BAD_REQUEST)

        import urllib.request
        import json
        text = f"<b>SmartTalim Test Xabarnomasi</b> 🔔\n\nTashkilot: <i>{organization.name}</i>\nBot orqali avtomatik moliya xabarnomalari tizimi muvaffaqiyatli sozlandi! ✅"

        chat_ids_list = [cid.strip() for cid in setting.chat_ids.replace(',', ' ').split() if cid.strip()]

        errors = []
        for chat_id in chat_ids_list:
            try:
                url = f"https://api.telegram.org/bot{setting.bot_token}/sendMessage"
                payload = {
                    'chat_id': chat_id,
                    'text': text,
                    'parse_mode': 'HTML'
                }
                data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=8) as res:
                    res.read()
            except Exception as e:
                errors.append(f"Chat ID {chat_id}: {str(e)}")

        if errors:
            return Response({"detail": f"Test xabarini yuborishda xatolik yuz berdi: {'; '.join(errors)}"},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Test xabari muvaffaqiyatli yuborildi! 🚀"}, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(summary="Filiallar ro'yxati", tags=['Organizations & Settings']),
    create=extend_schema(summary="Yangi filial yaratish", tags=['Organizations & Settings']),
    retrieve=extend_schema(summary="Filial tafsilotlari", tags=['Organizations & Settings']),
    update=extend_schema(summary="Filialni to'liq yangilash", tags=['Organizations & Settings']),
    partial_update=extend_schema(summary="Filialni qisman yangilash", tags=['Organizations & Settings']),
    destroy=extend_schema(summary="Filialni o'chirish", tags=['Organizations & Settings']),
    set_location=extend_schema(
        summary="Filial xaritadagi geografik lokatsiyasini saqlash/yangilash",
        tags=['Organizations & Settings'],
        request=inline_serializer(
            name='SetBranchLocationRequest',
            fields={
                'latitude': serializers.FloatField(help_text="Kenglik (Latitude, masalan: 41.311081)"),
                'longitude': serializers.FloatField(help_text="Uzunlik (Longitude, masalan: 69.240562)")
            }
        ),
        responses={200: OpenApiTypes.OBJECT}
    )
)
class BranchViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Sozlamalar'
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer

    def perform_create(self, serializer):
        org_id = self.get_organization_id()
        if not org_id:
            from rest_framework import exceptions
            raise exceptions.ValidationError({"detail": "Organization context is required."})
        branch = serializer.save(organization_id=org_id)
        user = self.request.user
        if user.is_authenticated and not user.branch:
            user.branch = branch
            user.save()

    @decorators.action(detail=True, methods=['post'], url_path='set-location')
    def set_location(self, request, pk=None):
        """Filial xaritadagi lokatsiyasini (latitude, longitude) saqlash/yangilash"""
        branch = self.get_object()

        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')

        if latitude is None or longitude is None:
            return Response(
                {"detail": "latitude va longitude maydonlari majburiy!"},
                status=status.HTTP_400_BAD_REQUEST
            )

        branch.latitude = latitude
        branch.longitude = longitude
        branch.save()

        return Response({
            "detail": "Filial lokatsiyasi muvaffaqiyatli saqlandi! 📍",
            "id": branch.id,
            "name": branch.name,
            "latitude": branch.latitude,
            "longitude": branch.longitude
        }, status=status.HTTP_200_OK)


@extend_schema(
    operation_id='organizations_branch_update_location_by_param',
    summary="Filial lokatsiyasini yangilash (Parametr branch_id bo'yicha)",
    parameters=[OpenApiParameter('branch_id', OpenApiTypes.INT, location=OpenApiParameter.PATH, description="Filial ID raqami")],
    tags=['Organizations & Settings'],
    request=inline_serializer(
        name='UpdateBranchLocationAPIRequest',
        fields={
            'latitude': serializers.FloatField(help_text="Kenglik (Latitude)"),
            'longitude': serializers.FloatField(help_text="Uzunlik (Longitude)")
        }
    ),
    responses={200: OpenApiTypes.OBJECT}
)
class UpdateBranchLocationAPIView(APIView):
    """Filialning geografik koordinatalarini (lokatsiyasini) yangilash API-si"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, branch_id):
        try:
            branch = Branch.objects.get(id=branch_id, organization=request.user.organization)
        except Branch.DoesNotExist:
            return Response({"error": "Filial topilmadi yoki sizda ruxsat yo'q!"}, status=status.HTTP_404_NOT_FOUND)

        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')

        if latitude is None or longitude is None:
            return Response({"error": "latitude va longitude maydonlari majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        branch.latitude = latitude
        branch.longitude = longitude
        branch.save()

        return Response({
            "success": True,
            "message": "Filial lokatsiyasi muvaffaqiyatli yangilandi!",
            "latitude": branch.latitude,
            "longitude": branch.longitude
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(summary="Ta'riflar (Tariffs) ro'yxati", tags=['Billing & Subscriptions']),
    create=extend_schema(summary="Yangi ta'rif yaratish", tags=['Billing & Subscriptions']),
    retrieve=extend_schema(summary="Ta'rif tafsilotlari", tags=['Billing & Subscriptions']),
    update=extend_schema(summary="Ta'rifni yangilash", tags=['Billing & Subscriptions']),
    partial_update=extend_schema(summary="Ta'rifni qisman yangilash", tags=['Billing & Subscriptions']),
    destroy=extend_schema(summary="Ta'rifni o'chirish", tags=['Billing & Subscriptions']),
)
class TariffViewSet(viewsets.ModelViewSet):
    permission_classes = (permissions.IsAuthenticated, HasOrganizationPagePermission)
    permission_page_name = 'Sozlamalar'
    queryset = Tariff.objects.all()
    serializer_class = TariffSerializer


@extend_schema_view(
    list=extend_schema(summary="Tashkilot faol obunasi (Subscription) ma'lumoti", tags=['Billing & Subscriptions']),
    create=extend_schema(summary="Yangi obuna yaratish", tags=['Billing & Subscriptions']),
    retrieve=extend_schema(summary="Obuna tafsilotlari", tags=['Billing & Subscriptions']),
    update=extend_schema(summary="Obunani yangilash", tags=['Billing & Subscriptions']),
    partial_update=extend_schema(summary="Obunani qisman yangilash", tags=['Billing & Subscriptions']),
    destroy=extend_schema(summary="Obunani bekor qilish", tags=['Billing & Subscriptions']),
)
class SubscriptionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Sozlamalar'
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer

    def list(self, request, *args, **kwargs):
        org_id = self.get_organization_id()
        if not org_id:
            return Response([])

        subscription, created = Subscription.objects.get_or_create(
            organization_id=org_id,
            defaults={
                'start_date': '2026-05-30',
                'end_date': '2027-05-30',
                'is_active': True
            }
        )
        serializer = self.get_serializer(subscription)
        return Response([serializer.data])


@extend_schema(
    summary="Tashkilotga kirish (Login - JWT token va foydalanuvchi ma'lumotlarini olish)",
    tags=['Authentication'],
    request=inline_serializer(
        name='OrganizationLoginRequest',
        fields={
            'username': serializers.CharField(help_text="Telefon raqami yoki login"),
            'password': serializers.CharField(help_text="Foydalanuvchi paroli")
        }
    ),
    responses={200: OpenApiTypes.OBJECT}
)
class OrganizationLoginView(APIView):
    """
    Login endpoint specifically under organizations, returns token and user info if authenticated.
    """
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        username = request.data.get('username') or request.data.get('phone')
        password = request.data.get('password')

        formatted_phone = normalize_uz_phone(username)
        user = None
        if formatted_phone:
            user = authenticate(username=formatted_phone, password=password)
            if user is None:
                cleaned = formatted_phone.replace('+', '')
                user = authenticate(username=cleaned, password=password)

        if user is None:
            user = authenticate(username=username, password=password)

        if user is not None:
            if not user.is_active:
                return Response({"detail": "User account is disabled."}, status=status.HTTP_400_BAD_REQUEST)

            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "Telefon raqam yoki parol noto'g'ri."}, status=status.HTTP_400_BAD_REQUEST)


from django.core.cache import cache
from rest_framework.decorators import api_view
from .utils import send_sms, generate_verification_code


@extend_schema(
    summary="Ro'yxatdan o'tish uchun telefon raqamiga SMS kod yuborish",
    tags=['Authentication'],
    request=inline_serializer(
        name='SendRegisterCodeRequest',
        fields={
            'phone_number': serializers.CharField(help_text="Telefon raqami (masalan: +998901234567)")
        }
    ),
    responses={200: OpenApiTypes.OBJECT}
)
@api_view(['POST'])
@decorators.permission_classes([permissions.AllowAny])
def send_register_code(request):
    """Foydalanuvchiga 6 xonali kod yuborish (Keshda saqlash)"""
    phone_number = request.data.get('phone_number')

    if not phone_number:
        return Response({"error": "Telefon raqam shart"}, status=400)

    code = generate_verification_code()
    message = f"SmartTalim. Ro'yxatdan o'tish kodi: {code}"

    success, sms_msg = send_sms(phone_number, message)

    if success:
        cache.set(f"sms_code_{phone_number}", code, timeout=300)
        return Response({"message": "Kod yuborildi! ✅"})
    return Response({"error": f"SMS xatosi: {sms_msg}"}, status=500)


@extend_schema(
    summary="SMS tasdiqlash kodini tekshirish",
    tags=['Authentication'],
    request=inline_serializer(
        name='VerifyRegisterCodeRequest',
        fields={
            'phone_number': serializers.CharField(help_text="Telefon raqami"),
            'code': serializers.CharField(help_text="Kiritilgan 6 xonali tasdiqlash kodi")
        }
    ),
    responses={200: OpenApiTypes.OBJECT}
)
@api_view(['POST'])
@decorators.permission_classes([permissions.AllowAny])
def verify_register_code(request):
    """Foydalanuvchi kiritgan kodni tekshirish"""
    phone_number = request.data.get('phone_number')
    user_code = request.data.get('code')

    if not phone_number or not user_code:
        return Response({"error": "Ma'lumotlar to'liq emas"}, status=400)

    saved_code = cache.get(f"sms_code_{phone_number}")

    if not saved_code:
        return Response({"error": "Kod eskirgan yoki raqam noto'g'ri"}, status=400)

    if str(saved_code) == str(user_code):
        cache.delete(f"sms_code_{phone_number}")
        return Response({"message": "Telefon raqam tasdiqlandi! 🎉"})
    return Response({"error": "Kod noto'g'ri! ❌"}, status=400)


from django.db.models import Q
from academics.models import Student, Group


@extend_schema(
    summary="Tizim bo'ylab universal global qidiruv",
    description="O'quvchilar (Student), xodimlar/o'qituvchilar (User) va guruhlar (Group) bo'yicha tezkor umumiy qidiruv.",
    parameters=[
        OpenApiParameter('q', OpenApiTypes.STR, description="Qidiruv matni (kamida 2 ta belgi)")
    ],
    tags=['Organizations & Search'],
    responses={200: GlobalSearchSerializer(many=True)}
)
class GlobalSearchAPIView(APIView):
    """Tizimdagi barcha muhim modellar va maydonlar bo'ylab universal global qidiruv"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()

        if len(query) < 2:
            return Response([], status=status.HTTP_200_OK)

        user_org = request.user.organization
        results = []

        # 1. O'QUVCHILAR (Student) QIDIRUVI
        students = Student.objects.filter(organization=user_org).filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(phone__icontains=query) |
            Q(address__icontains=query) |
            Q(father_name__icontains=query) |
            Q(mother_name__icontains=query)
        )[:15]

        for s in students:
            s_name = f"{s.first_name} {s.last_name or ''}".strip()
            s_phone = getattr(s, 'phone', '') or "yo'q"
            s_address = getattr(s, 'address', '') or "yo'q"

            results.append({
                'id': s.id,
                'name': s_name,
                'type': 'student',
                'type_display': "O'quvchi",
                'additional_info': f"Tel: {s_phone} | Manzil: {s_address}"
            })

        # 2. XODIMLAR VA O'QITUVCHILAR (User) QIDIRUVI
        users = User.objects.filter(organization=user_org).filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(username__icontains=query) |
            Q(phone__icontains=query) |
            Q(position__icontains=query) |
            Q(email__icontains=query)
        )[:15]

        for u in users:
            role_title = u.get_role_display() if hasattr(u, 'get_role_display') else "Xodim"
            position_title = f" ({u.position})" if getattr(u, 'position', None) else ""

            u_name = f"{u.first_name or u.username} {u.last_name or ''}".strip()
            u_phone = getattr(u, 'phone', '') or "yo'q"

            results.append({
                'id': u.id,
                'name': u_name,
                'type': 'staff',
                'type_display': f"{role_title}{position_title}",
                'additional_info': f"Tel: {u_phone} | Login: {u.username}"
            })

        # 3. GURUHLAR (Group) QIDIRUVI
        groups = Group.objects.filter(organization=user_org).filter(
            Q(name__icontains=query) |
            Q(room__name__icontains=query)
        )[:15]

        for g in groups:
            room = getattr(g.room, 'name', '') if getattr(g, 'room', None) else ''

            info_list = [f"Kun turi: {getattr(g, 'day_type', '')}"]
            if room:
                info_list.append(f"Xona: {room}")

            results.append({
                'id': g.id,
                'name': g.name,
                'type': 'group',
                'type_display': "Guruh",
                'additional_info': " | ".join(info_list)
            })

        serializer = GlobalSearchSerializer(results, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)