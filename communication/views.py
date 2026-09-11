from django.db.models import Q
from rest_framework import viewsets, mixins, permissions, status, decorators, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import HasOrganizationPagePermission
from communication.models import SmsProvider, SMSMessages, SmsSchedules, SmsTemplates, Notification, NotificationSchedule
from communication.serializers import (
    SmsProviderSerializer, SMSMessagesSerializer, SmsSchedulesSerializer, SmsTemplatesSerializer, NotificationScheduleSerializer
)
from communication.services import dispatch_notification_schedule


@extend_schema_view(
    list=extend_schema(summary="SMS provayderlar ro'yxati", description="Tashkilotga ulangan barcha SMS provayder integratsiyalari ro'yxatini qaytaradi.", tags=["Communication"]),
    retrieve=extend_schema(summary="SMS provayder tafsilotlari", description="Bitta SMS provayder sozlamalarini ko'rish.", tags=["Communication"]),
    create=extend_schema(summary="Yangi SMS provayder ulash", description="Tashkilot uchun yangi SMS provayder integratsiyasini (Eskiz, PlayMobile va h.k.) qo'shadi.", tags=["Communication"]),
    update=extend_schema(summary="SMS provayderni to'liq yangilash", description="SMS provayder sozlamalari va API kalitlarini to'liq tahrirlash.", tags=["Communication"]),
    partial_update=extend_schema(summary="SMS provayderni qisman yangilash", description="SMS provayder sozlamalarini (masalan faollik holatini) qisman yangilash.", tags=["Communication"]),
    destroy=extend_schema(summary="SMS provayderni o'chirish", description="Mavjud SMS provayder integratsiyasini o'chirish.", tags=["Communication"]),
)
class SmsProviderViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Sozlamalar'
    queryset = SmsProvider.objects.all()
    serializer_class = SmsProviderSerializer


@extend_schema_view(
    list=extend_schema(summary="Yuborilgan SMS xabarlar jurnali", description="Tashkilot nomidan yuborilgan barcha SMS xabarlari ro'yxati va ularning holati.", tags=["Communication"]),
    retrieve=extend_schema(summary="SMS xabar tafsiloti", description="Bitta yuborilgan SMS xabarning to'liq tafsilotlarini ko'rish.", tags=["Communication"]),
    create=extend_schema(summary="Yangi SMS xabar yuborish", description="Qabul qiluvchiga to'g'ridan-to'g'ri yangi SMS xabarni yuboradi va jurnalga yozadi.", tags=["Communication"]),
)
class SMSMessagesViewSet(TenantViewSetMixin,
                         mixins.CreateModelMixin,
                         mixins.ListModelMixin,
                         mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
    permission_page_name = 'Sozlamalar'
    queryset = SMSMessages.objects.all()
    serializer_class = SMSMessagesSerializer


@extend_schema_view(
    list=extend_schema(summary="Rejalashtirilgan SMS xabarlar ro'yxati", description="Muayyan vaqtda yuborilishi rejalashtirilgan barcha SMS xabarlar ro'yxati.", tags=["Communication"]),
    retrieve=extend_schema(summary="Rejalashtirilgan SMS tafsiloti", description="Bitta rejalashtirilgan SMS xabar parametrlarini ko'rish.", tags=["Communication"]),
    create=extend_schema(summary="Yangi SMS rejalashtirish", description="Belgilangan vaqtda yuborilishi uchun yangi SMS xabar yaratadi.", tags=["Communication"]),
    update=extend_schema(summary="Rejalashtirilgan SMSni to'liq yangilash", description="Rejalashtirilgan SMS vaqti va matnini to'liq yangilash.", tags=["Communication"]),
    partial_update=extend_schema(summary="Rejalashtirilgan SMSni qisman yangilash", description="Rejalashtirilgan SMS parametrlarini qisman o'zgartirish.", tags=["Communication"]),
    destroy=extend_schema(summary="Rejalashtirilgan SMSni bekor qilish", description="Rejalashtirilgan SMS xabarni o'chirish/bekor qilish.", tags=["Communication"]),
)
class SmsSchedulesViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Sozlamalar'
    queryset = SmsSchedules.objects.all()
    serializer_class = SmsSchedulesSerializer


@extend_schema_view(
    list=extend_schema(summary="SMS shablonlari ro'yxati", description="Tashkilotda saqlangan barcha tezkor SMS shablonlari (matn andozalari) ro'yxati.", tags=["Communication"]),
    retrieve=extend_schema(summary="SMS shablon tafsiloti", description="Bitta SMS shablon matnini ko'rish.", tags=["Communication"]),
    create=extend_schema(summary="Yangi SMS shablon yaratish", description="Tez-tez yuboriladigan xabarlar uchun yangi shablon qo'shadi.", tags=["Communication"]),
    update=extend_schema(summary="SMS shablonni to'liq yangilash", description="Mavjud shablon nomi va matnini to'liq yangilash.", tags=["Communication"]),
    partial_update=extend_schema(summary="SMS shablonni qisman yangilash", description="Mavjud shablonni qisman yangilash.", tags=["Communication"]),
    destroy=extend_schema(summary="SMS shablonni o'chirish", description="Keraksiz SMS shablonini o'chirib tashlash.", tags=["Communication"]),
)
class SmsTemplatesViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Sozlamalar'
    queryset = SmsTemplates.objects.all()
    serializer_class = SmsTemplatesSerializer


@extend_schema_view(
    list=extend_schema(summary="Bildirishnoma tarqatish jadvallari", description="Ommaviy yoki rejalashtirilgan bildirishnomalar (NotificationSchedule) ro'yxati.", tags=["Communication"]),
    retrieve=extend_schema(summary="Bildirishnoma jadvali tafsiloti", description="Bitta bildirishnoma tarqatish topshirig'i tafsilotlarini ko'rish.", tags=["Communication"]),
    create=extend_schema(summary="Rejalashtirilgan bildirishnoma yaratish", description="Muayyan vaqtda foydalanuvchilar, guruhlar yoki kurslarga yuboriladigan yangi bildirishnoma rejasini tuzadi.", tags=["Communication"]),
    update=extend_schema(summary="Bildirishnoma rejasini to'liq yangilash", description="Bildirishnoma rejasi matni, qabul qiluvchilari va vaqtini to'liq yangilash.", tags=["Communication"]),
    partial_update=extend_schema(summary="Bildirishnoma rejasini qisman yangilash", description="Bildirishnoma rejasini qisman yangilash.", tags=["Communication"]),
    destroy=extend_schema(summary="Bildirishnoma rejasini o'chirish", description="Rejalashtirilgan bildirishnomani bekor qilish yoki o'chirish.", tags=["Communication"]),
)
class NotificationScheduleViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Xabarlar'
    queryset = NotificationSchedule.objects.all()
    serializer_class = NotificationScheduleSerializer

    def perform_create(self, serializer):
        serializer.save(
            organization_id=self.get_organization_id(),
            branch_id=self.get_branch_id(),
            created_by=self.request.user
        )

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data['delivery_mode'] = 'scheduled'
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        schedule = serializer.save(
            organization_id=self.get_organization_id(),
            branch_id=self.get_branch_id(),
            created_by=self.request.user,
            delivery_mode='scheduled',
        )
        headers = self.get_success_headers(serializer.data)
        return Response(self.get_serializer(schedule).data, status=status.HTTP_201_CREATED, headers=headers)

    @extend_schema(
        operation_id="send_immediate_notification_schedule",
        summary="Bildirishnomani zudlik bilan (darhol) yuborish",
        description="Yangi bildirishnoma yaratadi va uni zudlik bilan belgilangan qabul qiluvchilarga tarqatadi.",
        request=NotificationScheduleSerializer,
        responses={
            201: inline_serializer(
                name="NotificationScheduleImmediateResponse",
                fields={
                    "detail": serializers.CharField(),
                    "sent_count": serializers.IntegerField(),
                    "schedule": NotificationScheduleSerializer(),
                }
            )
        },
        tags=["Communication"],
    )
    @decorators.action(detail=False, methods=['post'], url_path='send-now')
    def send_immediate(self, request):
        data = request.data.copy()
        data['delivery_mode'] = 'immediate'
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        schedule = serializer.save(
            organization_id=self.get_organization_id(),
            branch_id=self.get_branch_id(),
            created_by=self.request.user,
            delivery_mode='immediate',
            send_at=timezone.now(),
        )
        sent_count = dispatch_notification_schedule(schedule)
        schedule.refresh_from_db()
        return Response({
            "detail": "Xabar yuborildi.",
            "sent_count": sent_count,
            "schedule": self.get_serializer(schedule).data,
        }, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="dispatch_existing_notification_schedule_now",
        summary="Mavjud rejalashtirilgan bildirishnomani muddatidan oldin yuborish",
        description="Avval yaratilgan 'pending' holatidagi bildirishnomani kutmasdan darhol barcha qabul qiluvchilarga yuboradi.",
        request=None,
        responses={
            200: inline_serializer(
                name="NotificationScheduleSendNowResponse",
                fields={
                    "detail": serializers.CharField(),
                    "sent_count": serializers.IntegerField(),
                    "status": serializers.CharField(),
                }
            )
        },
        tags=["Communication"],
    )
    @decorators.action(detail=True, methods=['post'], url_path='send-now')
    def send_now(self, request, pk=None):
        schedule = self.get_object()
        sent_count = dispatch_notification_schedule(schedule)
        return Response({
            "detail": "Xabar yuborildi.",
            "sent_count": sent_count,
            "status": schedule.status,
        }, status=status.HTTP_200_OK)


class NotificationView(APIView):
    """Frontend tepasidagi bildirishnomalar (Notificationlar)"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="O'qilmagan va so'nggi bildirishnomalar ro'yxati",
        description="Joriy foydalanuvchiga tegishli yoki tashkilotning umumiy so'nggi 20 ta bildirishnomasi va o'qilmagan bildirishnomalar sonini qaytaradi.",
        responses={
            200: inline_serializer(
                name="NotificationListResponse",
                fields={
                    "count": serializers.IntegerField(),
                    "notifications": inline_serializer(
                        name="NotificationItemResponse",
                        many=True,
                        fields={
                            "id": serializers.IntegerField(),
                            "title": serializers.CharField(),
                            "message": serializers.CharField(),
                            "type": serializers.CharField(),
                            "is_read": serializers.BooleanField(),
                            "created_at": serializers.CharField(),
                        }
                    )
                }
            )
        },
        tags=["Communication"],
    )
    def get(self, request):
        """O'qilmagan va yaqindagi bildirishnomalarni qaytaradi"""
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({"count": 0, "notifications": []})

        # Eng so'nggi 20 ta bildirishnomani yuklash (umumiy yoki joriy userga tegishli)
        notifications = Notification.objects.filter(
            organization=org
        ).filter(
            Q(user__isnull=True) | Q(user=request.user)
        )[:20]
        
        unread_count = Notification.objects.filter(
            organization=org,
            is_read=False
        ).filter(
            Q(user__isnull=True) | Q(user=request.user)
        ).count()

        return Response({
            "count": unread_count,
            "notifications": [
                {
                    "id": n.id,
                    "title": n.title,
                    "message": n.message,
                    "type": n.type,
                    "is_read": n.is_read,
                    "created_at": n.created_at.isoformat() if n.created_at else "",
                }
                for n in notifications
            ]
        })

    @extend_schema(
        summary="Bildirishnomani o'qilgan deb belgilash",
        description="Bitta bildirishnomani (id orqali) yoki tana qismi bo'sh berilsa foydalanuvchining barcha bildirishnomalarini o'qilgan (is_read=True) deb belgilaydi.",
        request=inline_serializer(
            name="NotificationMarkReadRequest",
            fields={
                "id": serializers.IntegerField(required=False, help_text="Bildirishnoma ID si (agar berilmasa barchasi o'qilgan qilinadi)")
            }
        ),
        responses={
            200: inline_serializer(
                name="NotificationMarkReadResponse",
                fields={"detail": serializers.CharField()}
            ),
            400: inline_serializer(name="NotificationMarkReadError400", fields={"detail": serializers.CharField()}),
            403: inline_serializer(name="NotificationMarkReadError403", fields={"detail": serializers.CharField()}),
            404: inline_serializer(name="NotificationMarkReadError404", fields={"detail": serializers.CharField()}),
        },
        tags=["Communication"],
    )
    def patch(self, request):
        """Bildirishnomani o'qilgan deb belgilash"""
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({"detail": "Tashkilot topilmadi."}, status=400)

        notification_id = request.data.get('id')
        if notification_id:
            try:
                notification = Notification.objects.get(
                    id=notification_id, 
                    organization=org
                )
                # Faqat o'ziga tegishli yoki umumiy bo'lsa o'qilgan qilishi mumkin
                if notification.user and notification.user != request.user:
                    return Response({"detail": "Ruxsat etilmagan."}, status=403)
                    
                notification.is_read = True
                notification.save()
                return Response({"detail": "Bildirishnoma o'qildi deb belgilandi."})
            except Notification.DoesNotExist:
                return Response({"detail": "Bildirishnoma topilmadi."}, status=404)
        else:
            Notification.objects.filter(
                organization=org, 
                is_read=False
            ).filter(
                Q(user__isnull=True) | Q(user=request.user)
            ).update(is_read=True)
            return Response({"detail": "Barcha bildirishnomalar o'qildi."})

    @extend_schema(
        summary="Bildirishnomalarni o'chirish",
        description="Bitta bildirishnomani (id orqali) yoki parametr berilmasa foydalanuvchining barcha bildirishnomalarini o'chiradi.",
        request=inline_serializer(
            name="NotificationDeleteRequest",
            fields={
                "id": serializers.IntegerField(required=False, help_text="O'chiriladigan bildirishnoma ID si (agar berilmasa barchasi o'chiriladi)")
            }
        ),
        responses={
            200: inline_serializer(
                name="NotificationDeleteResponse",
                fields={"detail": serializers.CharField()}
            ),
            400: inline_serializer(name="NotificationDeleteError400", fields={"detail": serializers.CharField()}),
            403: inline_serializer(name="NotificationDeleteError403", fields={"detail": serializers.CharField()}),
            404: inline_serializer(name="NotificationDeleteError404", fields={"detail": serializers.CharField()}),
        },
        tags=["Communication"],
    )
    def delete(self, request):
        """Bildirishnomani o'chirib tashlash"""
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({"detail": "Tashkilot topilmadi."}, status=400)

        notification_id = request.data.get('id') or request.query_params.get('id')
        if notification_id:
            try:
                notification = Notification.objects.get(
                    id=notification_id, 
                    organization=org
                )
                if notification.user and notification.user != request.user:
                    return Response({"detail": "Ruxsat etilmagan."}, status=403)
                    
                notification.delete()
                return Response({"detail": "Bildirishnoma o'chirildi."})
            except Notification.DoesNotExist:
                return Response({"detail": "Bildirishnoma topilmadi."}, status=404)
        else:
            Notification.objects.filter(
                organization=org
            ).filter(
                Q(user__isnull=True) | Q(user=request.user)
            ).delete()
            return Response({"detail": "Barcha bildirishnomalar o'chirildi."})


class StudentSMSHistoryAPIView(APIView):
    """
    Bitta studentga yuborilgan barcha SMS xabarlarining tarixi.
    URL: /api/v1/communication/student-sms-history/<student_id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Talaba va uning ota-onasiga yuborilgan SMS tarixi",
        description="Ko'rsatilgan talaba (student_id), uning otasi va onasi telefon raqamlariga yuborilgan barcha SMS xabarlar tarixini xronologik tartibda qaytaradi.",
        responses={
            200: inline_serializer(
                name="StudentSMSHistoryResponse",
                fields={
                    "student": inline_serializer(
                        name="StudentSMSHistoryInfo",
                        fields={
                            "id": serializers.IntegerField(),
                            "full_name": serializers.CharField(),
                            "phone": serializers.CharField(),
                            "father_phone": serializers.CharField(allow_null=True),
                            "mother_phone": serializers.CharField(allow_null=True),
                        }
                    ),
                    "total_count": serializers.IntegerField(),
                    "sms_history": inline_serializer(
                        name="StudentSMSHistoryItem",
                        many=True,
                        fields={
                            "id": serializers.IntegerField(),
                            "recipient": serializers.CharField(),
                            "message": serializers.CharField(),
                            "status": serializers.CharField(),
                            "sent_at": serializers.CharField(allow_null=True),
                        }
                    )
                }
            ),
            400: inline_serializer(name="StudentSMSHistoryError400", fields={"detail": serializers.CharField()}),
            404: inline_serializer(name="StudentSMSHistoryError404", fields={"detail": serializers.CharField()}),
        },
        tags=["Communication"],
    )
    def get(self, request, student_id):
        from academics.models import Student

        org_id = getattr(request.user, 'organization_id', None)
        if not org_id:
            return Response({"detail": "Tashkilot aniqlanmadi."}, status=400)

        # Studentni topish
        try:
            student = Student.objects.get(id=student_id, organization_id=org_id)
        except Student.DoesNotExist:
            return Response({"detail": "Talaba topilmadi."}, status=404)

        # Student telefon raqami va ota-ona raqamlari bo'yicha SMS xabarlarini qidirish
        phone_numbers = [student.phone]
        if student.father_phone:
            phone_numbers.append(student.father_phone)
        if student.mother_phone:
            phone_numbers.append(student.mother_phone)

        sms_messages = SMSMessages.objects.filter(
            organization_id=org_id,
            recipient__in=phone_numbers
        ).order_by('-sent_at')

        data = {
            "student": {
                "id": student.id,
                "full_name": student.full_name,
                "phone": student.phone,
                "father_phone": student.father_phone,
                "mother_phone": student.mother_phone,
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
        }

        return Response(data)

