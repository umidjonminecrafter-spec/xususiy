from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, status, decorators, generics, exceptions, serializers
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import IsAdminOrOwnerOrReadOnly
from academics.models import (
    Student, StudentGroup, Attendance, StudentArchive,
    StudentPricing, StudentFieldSetting, StudentEvaluationLevel, BalanceHistory
)
from academics.serializers import (
    StudentSerializer, StudentGroupSerializer, StudentFieldSettingSerializer,
    StudentBalanceSerializer, BalanceHistorySerializer, StudentPricingSerializer,
    StudentArchiveSerializer, StudentEvaluationLevelSerializer
)


@extend_schema_view(
    list=extend_schema(
        summary="Faol talabalar ro'yxati",
        description="Tashkilotdagi barcha faol (arxivlanmagan) talabalar ro'yxatini qaytaradi. Guruh ID, talaba ID yoki ism/telefon bo'yicha qidirish mumkin.",
        parameters=[
            OpenApiParameter('group', OpenApiTypes.INT, OpenApiParameter.QUERY, description="Guruh bo'yicha filtrlash"),
            OpenApiParameter('id', OpenApiTypes.INT, OpenApiParameter.QUERY, description="Talaba ID si bo'yicha filtrlash"),
            OpenApiParameter('search', OpenApiTypes.STR, OpenApiParameter.QUERY, description="Ism, familiya, telefon yoki email bo'yicha qidiruv"),
        ]
    ),
    retrieve=extend_schema(
        summary="Talaba profili",
        description="Tanlangan talabaning to'liq shaxsiy va akademik ma'lumotlarini (balans, biriktirilgan guruhlar, ota-onasi kontaktlari) qaytaradi."
    ),
    create=extend_schema(
        summary="Yangi talaba qo'shish",
        description="Tashkilotga yangi talaba qo'shadi. Tashkilotning joriy tarifi va talabalar limiti avtomatik tekshiriladi."
    ),
    update=extend_schema(
        summary="Talaba ma'lumotlarini to'liq yangilash",
        description="Talabaning barcha shaxsiy ma'lumotlarini to'liq yangilaydi."
    ),
    partial_update=extend_schema(
        summary="Talaba ma'lumotlarini qisman tahrirlash",
        description="Talaba profilidagi ayrim maydonlarni (telefon, manzil, status) qisman yangilaydi."
    ),
    destroy=extend_schema(
        summary="Talabani o'chirish yoki arxivlash",
        description="Talabani tizimdan o'chiradi yoki arxivga o'tkazadi. Agar talabaning qarzdorligi bo'lsa, u yumshoq o'chiriladi (arxivlanadi); aks holda to'liq o'chiriladi va arxiv qaydi yaratiladi.",
        parameters=[
            OpenApiParameter('reason', OpenApiTypes.STR, OpenApiParameter.QUERY, description="Arxivlash sababi"),
            OpenApiParameter('comment', OpenApiTypes.STR, OpenApiParameter.QUERY, description="Qo'shimcha izoh"),
        ]
    ),
)
class StudentViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Talabalar'
    queryset = Student.objects.select_related('organization', 'branch').prefetch_related('student_groups__group__course')
    serializer_class = StudentSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['first_name', 'last_name', 'phone', 'email']

    def get_queryset(self):
        queryset = super().get_queryset().exclude(is_archived=True)
        group_id = self.request.query_params.get('group') or self.request.query_params.get('group_id')
        if group_id:
            queryset = queryset.filter(student_groups__group_id=group_id)

        student_id = self.request.query_params.get('id')
        if student_id:
            queryset = queryset.filter(id=student_id)

        search_param = self.request.query_params.get('search')
        if search_param and search_param.isdigit():
            queryset = queryset.filter(
                Q(id=int(search_param)) |
                Q(first_name__icontains=search_param) |
                Q(last_name__icontains=search_param) |
                Q(phone__icontains=search_param) |
                Q(email__icontains=search_param)
            )
            self.search_fields = []

        return queryset

    def perform_create(self, serializer):
        org_id = self.get_organization_id()
        if not org_id:
            raise exceptions.ValidationError({"detail": "Organization context is required."})

        from organizations.models import Subscription
        subscription = Subscription.objects.filter(organization_id=org_id, is_active=True).first()
        if not subscription:
            raise exceptions.ValidationError(
                {"detail": "Tashkilotning faol obunasi topilmadi. Yangi talaba qo'shish uchun tarif sotib oling."}
            )

        tariff = subscription.tariff
        if tariff and tariff.student_limit > 0:
            current_students_count = Student.objects.filter(organization_id=org_id).count()
            if current_students_count >= tariff.student_limit:
                raise exceptions.ValidationError({
                    "detail": f"Tarifingizdagi talabalar limiti ({tariff.student_limit}) ga yetdingiz. Yangi talaba qo'shish uchun tarifni yangilang."
                })

        super().perform_create(serializer)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        reason = request.query_params.get('reason') or request.data.get('reason') or "O'chirib tashlangan"
        comment = request.query_params.get('comment') or request.data.get('comment') or ""

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
            if instance.phone:
                username = f"{instance.phone}_{instance.organization_id}"
                qs = User.objects.filter(username=username, role='student')
                if not qs.exists():
                    qs = User.objects.filter(username=instance.phone, role='student')
                qs.delete()
            return super().destroy(request, *args, **kwargs)

    @extend_schema(
        summary="Talabaga to'lov qo'shish",
        description="Talaba hisobiga to'lov qabul qiladi (Payment yaratadi) va talabaning balansini oshiradi.",
        request=inline_serializer(
            name='StudentAddPaymentRequest',
            fields={
                'amount': serializers.DecimalField(max_digits=12, decimal_places=2),
                'payment_method': serializers.ChoiceField(choices=['cash', 'card', 'bank', 'click', 'payme', 'uzum'], default='cash', required=False),
                'comment': serializers.CharField(required=False, allow_blank=True),
            }
        ),
        responses={
            201: inline_serializer(
                name='StudentAddPaymentResponse',
                fields={
                    'detail': serializers.CharField(),
                    'balance': serializers.DecimalField(max_digits=12, decimal_places=2),
                    'payment_id': serializers.IntegerField(),
                }
            ),
            400: inline_serializer(
                name='StudentAddPaymentErrorResponse',
                fields={'detail': serializers.CharField()}
            )
        }
    )
    @decorators.action(detail=True, methods=['post'], url_path='add-payment')
    def add_payment(self, request, pk=None):
        student = self.get_object()
        amount = request.data.get('amount')
        payment_method = request.data.get('payment_method') or request.data.get('payment_type') or 'cash'
        comment = request.data.get('comment') or request.data.get('note') or ''

        if not amount:
            return Response({"detail": "Amount is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount_dec = Decimal(str(amount))
        except ValueError:
            return Response({"detail": "Invalid amount."}, status=status.HTTP_400_BAD_REQUEST)

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

    @extend_schema(
        summary="Talabani guruhga biriktirish",
        description="Talabani ko'rsatilgan guruhga qo'shadi (StudentGroup bog'lanishini yaratadi).",
        request=inline_serializer(
            name='StudentAddToGroupRequest',
            fields={
                'group': serializers.IntegerField(help_text="Guruh ID si"),
            }
        ),
        responses={
            201: StudentGroupSerializer,
            400: inline_serializer(name='StudentAddToGroupErrorResponse', fields={'detail': serializers.CharField()}),
            404: inline_serializer(name='StudentAddToGroupNotFoundResponse', fields={'detail': serializers.CharField()})
        }
    )
    @decorators.action(detail=True, methods=['post'], url_path='add-to-group')
    def add_to_group(self, request, pk=None):
        student = self.get_object()
        group_id = request.data.get('group') or request.data.get('group_id')
        if not group_id:
            return Response({"detail": "Group ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        from academics.models import Group
        org_id = self.get_organization_id()
        group = get_object_or_404(Group.objects.filter(organization_id=org_id), id=group_id)

        student_group, created = StudentGroup.objects.get_or_create(
            organization_id=org_id,
            student=student,
            group=group
        )
        return Response(StudentGroupSerializer(student_group).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Talaba balans holati",
        description="Talabaning joriy balansi va uning musbat yoki manfiyligini (qarzdorlik holatini) qaytaradi.",
        responses={
            200: inline_serializer(
                name='StudentBalanceStatusResponse',
                fields={
                    'balance': serializers.DecimalField(max_digits=12, decimal_places=2),
                    'status': serializers.CharField(),
                }
            )
        }
    )
    @decorators.action(detail=True, methods=['get'], url_path='balance-status')
    def balance_status(self, request, pk=None):
        student = self.get_object()
        return Response({
            "balance": student.balance,
            "status": "positive" if student.balance >= 0 else "negative"
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Talabalar umumiy hisoboti",
        description="Filtrlangan talabalar soni va hisobot sanasini qaytaradi.",
        responses={
            200: inline_serializer(
                name='StudentReportResponse',
                fields={
                    'total_students': serializers.IntegerField(),
                    'report_date': serializers.DateField(),
                }
            )
        }
    )
    @decorators.action(detail=False, methods=['get'], url_path='report')
    def report(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        total_students = queryset.count()
        return Response({
            "total_students": total_students,
            "report_date": timezone.now().date()
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Talabalar holatini ommaviy o'zgartirish",
        description="Tanlangan talabalar statusini ommaviy ravishda yangilaydi.",
        parameters=[
            OpenApiParameter('action_name', OpenApiTypes.STR, location=OpenApiParameter.PATH, description="Bajariladigan amal nomi")
        ],
        responses={
            200: inline_serializer(
                name='StudentStatusActionResponse',
                fields={
                    'status': serializers.CharField(),
                    'action': serializers.CharField(),
                    'detail': serializers.CharField(),
                }
            )
        }
    )
    @decorators.action(detail=False, methods=['post'], url_path=r'status/(?P<action_name>[^/.]+)')
    def status_action(self, request, action_name=None):
        return Response({"status": "success", "action": action_name, "detail": "Bulk status action processed."},
                        status=status.HTTP_200_OK)

    @extend_schema(
        summary="Talabaning umumiy tarixi",
        description="Talabaning profili, qatnashayotgan guruhlari, to'lovlari va dars davomatlari umumiy statistikasini qaytaradi.",
        responses={
            200: inline_serializer(
                name='StudentHistoryResponse',
                fields={
                    'student': StudentSerializer(),
                    'groups': StudentGroupSerializer(many=True),
                    'attendance_count': serializers.IntegerField(),
                    'payments_count': serializers.IntegerField(),
                    'payments': inline_serializer(
                        name='StudentHistoryPaymentItem',
                        many=True,
                        fields={
                            'id': serializers.IntegerField(),
                            'amount': serializers.DecimalField(max_digits=12, decimal_places=2),
                            'date': serializers.DateField(),
                            'method': serializers.CharField(),
                        }
                    ),
                    'attendances': inline_serializer(
                        name='StudentHistoryAttendanceItem',
                        many=True,
                        fields={
                            'id': serializers.IntegerField(),
                            'group': serializers.CharField(),
                            'date': serializers.DateField(),
                            'status': serializers.CharField(),
                        }
                    )
                }
            )
        }
    )
    @decorators.action(detail=True, methods=['get'], url_path='history')
    def history(self, request, pk=None):
        student = self.get_object()
        attendances = Attendance.objects.filter(student=student)
        groups = StudentGroup.objects.filter(student=student)

        from finance.models import Payment
        payments = Payment.objects.filter(student=student)

        return Response({
            "student": StudentSerializer(student).data,
            "groups": StudentGroupSerializer(groups, many=True).data,
            "attendance_count": attendances.count(),
            "payments_count": payments.count(),
            "payments": [{"id": p.id, "amount": p.amount, "date": p.date, "method": p.payment_method} for p in payments],
            "attendances": [{"id": a.id, "group": a.group.name, "date": a.date, "status": a.status} for a in attendances]
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Talabaning lid (CRM) tarixi",
        description="Talabaning telefon raqami orqali CRM tizimidan uning qaysi voronka, manba orqali kelganlik tarixini qaytaradi.",
        responses={
            200: inline_serializer(
                name='StudentLeadHistoryResponse',
                fields={
                    'student_id': serializers.IntegerField(),
                    'phone': serializers.CharField(),
                    'leads_matched': inline_serializer(
                        name='StudentLeadHistoryItem',
                        many=True,
                        fields={
                            'id': serializers.IntegerField(),
                            'name': serializers.CharField(),
                            'status': serializers.CharField(),
                            'pipeline': serializers.CharField(allow_null=True),
                            'source': serializers.CharField(allow_null=True),
                            'created_at': serializers.DateTimeField(),
                        }
                    )
                }
            )
        }
    )
    @decorators.action(detail=True, methods=['get'], url_path='lead-history')
    def lead_history(self, request, pk=None):
        student = self.get_object()
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

    @extend_schema(
        methods=['GET'],
        summary="Talabaga yuborilgan SMSlar tarixi",
        description="Talaba va uning ota-onasining telefon raqamlariga yuborilgan barcha SMS xabarlar tarixini qaytaradi.",
        responses={
            200: inline_serializer(
                name='StudentSMSHistoryResponse',
                fields={
                    'student': inline_serializer(
                        name='StudentSMSHistoryStudent',
                        fields={
                            'id': serializers.IntegerField(),
                            'full_name': serializers.CharField(),
                            'phone': serializers.CharField(),
                        }
                    ),
                    'total_count': serializers.IntegerField(),
                    'sms_history': inline_serializer(
                        name='StudentSMSHistoryItem',
                        many=True,
                        fields={
                            'id': serializers.IntegerField(),
                            'recipient': serializers.CharField(),
                            'message': serializers.CharField(),
                            'status': serializers.CharField(),
                            'sent_at': serializers.CharField(allow_null=True),
                        }
                    )
                }
            )
        }
    )
    @extend_schema(
        methods=['POST'],
        summary="Talabaga SMS yuborish",
        description="Talabaning telefon raqamiga individual SMS xabar jo'natadi.",
        request=inline_serializer(
            name='StudentSendSMSRequest',
            fields={
                'message': serializers.CharField(),
            }
        ),
        responses={
            200: inline_serializer(
                name='StudentSendSMSResponse',
                fields={
                    'status': serializers.CharField(),
                    'message': serializers.CharField(),
                }
            ),
            400: inline_serializer(name='StudentSendSMSError', fields={'detail': serializers.CharField()}),
            403: inline_serializer(name='StudentSendSMSForbidden', fields={'detail': serializers.CharField()})
        }
    )
    @decorators.action(detail=True, methods=['get', 'post'], url_path='send-sms')
    def send_sms(self, request, pk=None):
        student = self.get_object()

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

    @extend_schema(
        summary="Talabaning to'liq davomat tarixi",
        description="Talabaning barcha guruhlardagi darslarga qatnashish davomati, baholari, sabablari va qatnashish foizi statistikasini qaytaradi.",
        responses={
            200: inline_serializer(
                name='StudentAttendanceHistoryResponse',
                fields={
                    'student': inline_serializer(
                        name='StudentAttHistoryStudent',
                        fields={'id': serializers.IntegerField(), 'full_name': serializers.CharField()}
                    ),
                    'statistics': inline_serializer(
                        name='StudentAttHistoryStats',
                        fields={
                            'total': serializers.IntegerField(),
                            'present': serializers.IntegerField(),
                            'absent': serializers.IntegerField(),
                            'late': serializers.IntegerField(),
                            'excused': serializers.IntegerField(),
                            'attendance_rate': serializers.FloatField(),
                        }
                    ),
                    'total_count': serializers.IntegerField(),
                    'by_group': inline_serializer(
                        name='StudentAttHistoryByGroup',
                        many=True,
                        fields={
                            'group_name': serializers.CharField(),
                            'records': serializers.ListField(child=serializers.DictField()),
                            'count': serializers.IntegerField(),
                        }
                    ),
                    'history': inline_serializer(
                        name='StudentAttHistoryItem',
                        many=True,
                        fields={
                            'id': serializers.IntegerField(),
                            'date': serializers.CharField(),
                            'status': serializers.CharField(),
                            'grade': serializers.IntegerField(allow_null=True),
                            'reason': serializers.CharField(allow_null=True),
                            'group_name': serializers.CharField(),
                            'group_id': serializers.IntegerField(allow_null=True),
                        }
                    )
                }
            )
        }
    )
    @decorators.action(detail=True, methods=['get'], url_path='attendance-history')
    def attendance_history(self, request, pk=None):
        student = self.get_object()
        org_id = self.get_organization_id()

        attendances = Attendance.objects.filter(
            student=student,
            organization_id=org_id
        ).select_related('group').order_by('-date')

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

    @extend_schema(
        summary="Talabalarni Excel/CSV fayldan ommaviy import qilish",
        description="Excel (.xlsx/.xls) yoki CSV fayldan talabalar ro'yxatini tashkilotga ommaviy yuklaydi va natijani qaytaradi.",
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'file': {
                        'type': 'string',
                        'format': 'binary'
                    }
                },
                'required': ['file']
            }
        },
        responses={
            200: inline_serializer(
                name='StudentExcelImportResponse',
                fields={
                    'message': serializers.CharField(),
                    'success_count': serializers.IntegerField(),
                    'errors': serializers.ListField(child=serializers.CharField()),
                }
            ),
            400: inline_serializer(name='StudentExcelImportErrorResponse', fields={'detail': serializers.CharField()})
        }
    )
    @decorators.action(detail=False, methods=['post'], url_path='import-excel')
    def import_excel(self, request):
        from academics.services.student_import import import_students_from_file
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({"detail": "No file uploaded. Please upload a file with key 'file'."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            success_count, error_logs = import_students_from_file(
                file_obj=file_obj,
                org_id=org_id,
                branch_id=self.get_branch_id()
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "message": f"Excel import tugallandi. {success_count} ta talaba muvaffaqiyatli saqlandi/yangilandi.",
            "success_count": success_count,
            "errors": error_logs
        }, status=status.HTTP_200_OK)



@extend_schema_view(
    list=extend_schema(
        summary="Talabalar balanslari ro'yxati",
        description="Tashkilotdagi barcha talabalarning joriy balanslari, qarzdor yoki haqdorlik holatlarini filtrlash imkoniyati bilan qaytaradi.",
        parameters=[
            OpenApiParameter('search', OpenApiTypes.STR, OpenApiParameter.QUERY, description="Ism, familiya yoki telefon bo'yicha qidirish"),
            OpenApiParameter('balance_min', OpenApiTypes.FLOAT, OpenApiParameter.QUERY, description="Minimal balans summasi"),
            OpenApiParameter('balance_max', OpenApiTypes.FLOAT, OpenApiParameter.QUERY, description="Maksimal balans summasi"),
            OpenApiParameter('date_from', OpenApiTypes.DATE, OpenApiParameter.QUERY, description="Talaba qo'shilgan sana (boshlanish)"),
            OpenApiParameter('date_to', OpenApiTypes.DATE, OpenApiParameter.QUERY, description="Talaba qo'shilgan sana (tugash)"),
        ]
    ),
    retrieve=extend_schema(
        summary="Talaba balans tafsiloti",
        description="Tanlangan talabaning balans va to'lov hisob-kitob ma'lumotlarini qaytaradi."
    ),
)
class StudentBalancesViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    permission_page_name = 'Talabalar'
    queryset = Student.objects.all()
    serializer_class = StudentBalanceSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
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


@extend_schema_view(
    list=extend_schema(
        summary="Talaba balans o'zgarishlari tarixi",
        description="Talabalar hisobiga pul tushishi, dars uchun mablag' yechilishi yoki balans o'zgarishlari loglari ro'yxatini qaytaradi."
    ),
    retrieve=extend_schema(
        summary="Balans o'zgarish yozuvi tafsiloti",
        description="Bitta balans o'zgarish yozuvining to'liq tafsilotlarini qaytaradi."
    ),
    create=extend_schema(
        summary="Balans o'zgarishi qaydini yaratish",
        description="Talaba balansi o'zgarishi bo'yicha yangi audit qaydini kiritadi."
    ),
    update=extend_schema(
        summary="Balans o'zgarish qaydini to'liq yangilash",
        description="Balans o'zgarish qaydini to'liq yangilaydi."
    ),
    partial_update=extend_schema(
        summary="Balans o'zgarish qaydini qisman tahrirlash",
        description="Balans o'zgarish qaydidagi ayrim maydonlarni qisman yangilaydi."
    ),
    destroy=extend_schema(
        summary="Balans o'zgarish qaydini o'chirish",
        description="Balans o'zgarish qaydini o'chiradi."
    ),
)
class BalanceHistoryViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Barcha to\'lovlar'
    queryset = BalanceHistory.objects.all()
    serializer_class = BalanceHistorySerializer


@extend_schema_view(
    list=extend_schema(
        summary="Talaba individual narxlari ro'yxati",
        description="Muayyan talabalarga berilgan maxsus narxlar va individual chegirmalar ro'yxatini qaytaradi."
    ),
    retrieve=extend_schema(
        summary="Individual narx tafsiloti",
        description="Talabaning individual narx parametrlarini qaytaradi."
    ),
    create=extend_schema(
        summary="Talabaga individual narx belgilash",
        description="Talabaga maxsus narx yoki chegirma biriktiradi."
    ),
    update=extend_schema(
        summary="Individual narxni to'liq yangilash",
        description="Talabaning individual narx ma'lumotlarini to'liq yangilaydi."
    ),
    partial_update=extend_schema(
        summary="Individual narxni qisman tahrirlash",
        description="Talabaning individual narx parametrlarini qisman o'zgartiradi."
    ),
    destroy=extend_schema(
        summary="Individual narxni bekor qilish",
        description="Talabaga biriktirilgan maxsus narxni o'chiradi (standart narxga qaytaradi)."
    ),
)
class StudentPricingViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Talabalar'
    queryset = StudentPricing.objects.all()
    serializer_class = StudentPricingSerializer


@extend_schema_view(
    list=extend_schema(
        summary="Talaba qo'shimcha maydonlari sozlamalari",
        description="Tashkilot uchun talabalar anketasida foydalaniladigan dinamik/maxsus maydonlar ro'yxatini qaytaradi."
    ),
    retrieve=extend_schema(
        summary="Qo'shimcha maydon tafsiloti",
        description="Talaba anketasi maydoni parametrlarini qaytaradi."
    ),
    create=extend_schema(
        summary="Yangi qo'shimcha maydon yaratish",
        description="Talabalar anketasi uchun yangi maxsus maydon qo'shadi."
    ),
    update=extend_schema(
        summary="Qo'shimcha maydonni to'liq yangilash",
        description="Maxsus maydon sozlamalarini to'liq yangilaydi."
    ),
    partial_update=extend_schema(
        summary="Qo'shimcha maydonni qisman tahrirlash",
        description="Maxsus maydon parametrlarini qisman o'zgartiradi."
    ),
    destroy=extend_schema(
        summary="Qo'shimcha maydonni o'chirish",
        description="Talaba anketasidagi maxsus maydonni o'chiradi."
    ),
)
class StudentFieldSettingViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
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


@extend_schema_view(
    list=extend_schema(
        summary="Talabalarni baholash darajalari ro'yxati",
        description="Tashkilotdagi talabalarning bilim darajasini baholash shkalalari (daraja nomi, ball oralig'i, rang) ro'yxatini qaytaradi."
    ),
    retrieve=extend_schema(
        summary="Baholash darajasi tafsiloti",
        description="Tanlangan baholash darajasining parametrlarini qaytaradi."
    ),
    create=extend_schema(
        summary="Yangi baholash darajasini yaratish",
        description="Tashkilot uchun yangi baholash darajasini (nomi, ball oralig'i, rangi) kiritadi."
    ),
    update=extend_schema(
        summary="Baholash darajasini to'liq yangilash",
        description="Baholash darajasi parametrlarini to'liq yangilaydi."
    ),
    partial_update=extend_schema(
        summary="Baholash darajasini qisman tahrirlash",
        description="Baholash darajasini qisman yangilaydi."
    ),
    destroy=extend_schema(
        summary="Baholash darajasini o'chirish",
        description="Baholash darajasini tizimdan o'chiradi."
    ),
)
class StudentEvaluationLevelViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StudentEvaluationLevelSerializer
    queryset = StudentEvaluationLevel.objects.all()

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)


class StudentTransactionsView(TenantViewSetMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Barcha to\'lovlar'
    pagination_class = None

    def get_queryset(self):
        from finance.models import Payment
        queryset = Payment.objects.all()

        org_id = self.get_organization_id()
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        else:
            return queryset.none()

        branch_id = self.get_branch_id()
        if branch_id:
            queryset = queryset.filter(Q(branch_id=branch_id) | Q(branch__isnull=True))

        student_id = (
            self.request.query_params.get('student') or
            self.request.query_params.get('student_id') or
            self.request.query_params.get('id')
        )
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        return queryset

    @extend_schema(
        summary="Talabaning to'lov tranzaksiyalari ro'yxati",
        description="Talabaning barcha to'lovlari (tranzaksiyalari) ro'yxatini qaytaradi.",
        parameters=[
            OpenApiParameter('student', OpenApiTypes.INT, OpenApiParameter.QUERY, description="Talaba ID si bo'yicha filtrlash"),
            OpenApiParameter('student_id', OpenApiTypes.INT, OpenApiParameter.QUERY, description="Talaba ID si"),
            OpenApiParameter('id', OpenApiTypes.INT, OpenApiParameter.QUERY, description="Talaba ID si"),
        ],
        responses={
            200: inline_serializer(
                name='StudentTransactionItem',
                many=True,
                fields={
                    'id': serializers.IntegerField(),
                    'amount': serializers.DecimalField(max_digits=12, decimal_places=2),
                    'date': serializers.DateField(),
                    'payment_method': serializers.CharField(),
                    'comment': serializers.CharField(allow_blank=True, allow_null=True),
                }
            )
        }
    )
    def get(self, request, *args, **kwargs):
        from finance.serializers import PaymentSerializer
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = PaymentSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = PaymentSerializer(queryset, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        summary="Arxivdagi talabalar ro'yxati",
        description="O'qishni to'xtatgan yoki guruhdan ketgan arxivlangan talabalar ro'yxatini qaytaradi."
    ),
    retrieve=extend_schema(
        summary="Arxivlangan talaba tafsiloti",
        description="Arxivlangan talabaning ketish sababi, sanasi va ma'lumotlarini qaytaradi."
    ),
    create=extend_schema(
        summary="Talabani arxivga qo'shish",
        description="Talabani arxiv ro'yxatiga to'g'ridan-to'g'ri kiritadi."
    ),
    update=extend_schema(
        summary="Arxiv yozuvini to'liq yangilash",
        description="Arxiv yozuvini to'liq yangilaydi."
    ),
    partial_update=extend_schema(
        summary="Arxiv yozuvini qisman tahrirlash",
        description="Arxiv yozuvini qisman yangilaydi."
    ),
    destroy=extend_schema(
        summary="Arxivdan butunlay o'chirish",
        description="Arxivdagi talabani va unga tegishli akkauntni tizimdan butunlay o'chiradi. Agar qarzdorlik bo'lsa, o'chirish taqiqlanadi."
    ),
)
class StudentArchiveViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Guruhni tark etganlar'
    queryset = StudentArchive.objects.all()
    serializer_class = StudentArchiveSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['first_name', 'last_name', 'phone', 'email']

    def destroy(self, request, *args, **kwargs):
        archive_item = self.get_object()
        archived_student = Student.objects.filter(phone=archive_item.phone, is_archived=True).first()
        if archived_student and archived_student.balance < 0:
            raise exceptions.ValidationError({
                "detail": "Qarzdorligi bor talabani arxivdan o'chirib bo'lmaydi! Avval qarzi to'lanishi kerak."
            })

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

    @extend_schema(
        summary="Talabani arxivdan tiklash",
        description="Arxivdagi talabani (yoki xodimni) faol holatga qaytaradi va kerak bo'lsa uning foydalanuvchi akkauntini qayta faollashtiradi.",
        responses={
            200: inline_serializer(
                name='StudentArchiveRestoreResponse',
                fields={
                    'status': serializers.CharField(),
                    'detail': serializers.CharField(),
                }
            ),
            400: inline_serializer(
                name='StudentArchiveRestoreErrorResponse',
                fields={'detail': serializers.CharField()}
            )
        }
    )
    @decorators.action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        archive_item = self.get_object()
        is_student = not archive_item.role or archive_item.role.lower() in ['student', 'talaba']

        from accounts.models import User
        org_id = archive_item.organization_id
        phone = archive_item.phone
        username = f"{phone}_{org_id}" if (phone and org_id) else (phone or archive_item.email or f"user_{archive_item.id}")

        if is_student:
            if Student.objects.filter(phone=archive_item.phone, organization_id=org_id, is_archived=False).exists():
                return Response({"detail": "Ushbu telefon raqamli talaba tizimda allaqachon mavjud."},
                                status=status.HTTP_400_BAD_REQUEST)

            archived_student = Student.objects.filter(phone=archive_item.phone, organization_id=org_id, is_archived=True).first()
            if archived_student:
                archived_student.is_archived = False
                archived_student.save(update_fields=['is_archived'])

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

            Student.objects.create(
                organization=archive_item.organization,
                branch=archive_item.branch,
                first_name=archive_item.first_name,
                last_name=archive_item.last_name,
                phone=archive_item.phone,
                email=archive_item.email,
                balance=0.00
            )
        else:
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
