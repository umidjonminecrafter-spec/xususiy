import datetime
from decimal import Decimal, InvalidOperation

from rest_framework import permissions, status, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, inline_serializer

from billing.models import BillingHistory, BalanceTopUp, SubscriptionRequest
from billing.serializers import BillingHistorySerializer
from organizations.models import Subscription, Tariff
from organizations.serializers import TariffSerializer


def add_months(start_date, months):
    total_months = start_date.month + months - 1
    year = start_date.year + (total_months // 12)
    month = (total_months % 12) + 1
    day = min(start_date.day, 28)
    return datetime.date(year, month, day)


class BillingPlansView(APIView):
    """Barcha tariflarni ko'rsatadi"""
    permission_classes = (permissions.AllowAny,)

    @extend_schema(
        summary="Mavjud barcha tarif rejalari ro'yxati",
        description="Tizimda faol bo'lgan barcha obuna tarif rejalari (narxi, davomiyligi, funksional imkoniyatlari) ro'yxatini qaytaradi.",
        responses={200: TariffSerializer(many=True)},
        tags=["Billing"],
    )
    def get(self, request):
        tariffs = Tariff.objects.all()
        serializer = TariffSerializer(tariffs, many=True)
        return Response(serializer.data)


class BillingCurrentView(APIView):
    """Hozirgi balance va tarif holati"""
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        summary="Joriy tashkilotning obunasi va hisob balansi",
        description="Foydalanuvchi tashkilotining faol obunasi, qolgan kunlar soni, amal qilish muddati va hisobidagi mavjud pul balansini qaytaradi. Agar muddat tugagan bo'lsa, avtomatik ravishda nofaol qilib yangilaydi.",
        responses={
            200: inline_serializer(
                name="BillingCurrentResponse",
                fields={
                    "balance": serializers.DecimalField(max_digits=12, decimal_places=2),
                    "tariff": TariffSerializer(allow_null=True),
                    "start_date": serializers.DateField(allow_null=True),
                    "end_date": serializers.DateField(allow_null=True),
                    "is_active": serializers.BooleanField(),
                    "days_left": serializers.IntegerField(),
                    "expires_soon": serializers.BooleanField(),
                    "expired": serializers.BooleanField(),
                    "no_subscription": serializers.BooleanField(required=False),
                }
            )
        },
        tags=["Billing"],
    )
    def get(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({"balance": 0, "no_subscription": True})

        today = datetime.date.today()
        subscription = Subscription.objects.filter(organization=org).first()
        if not subscription:
            return Response({"balance": 0, "no_subscription": True})

        # Muddati o'tgan bo'lsa o'chirish
        if subscription.is_active and subscription.end_date < today:
            subscription.is_active = False
            subscription.save(update_fields=['is_active'])

        days_left = (subscription.end_date - today).days

        return Response({
            "balance": subscription.balance,
            "tariff": TariffSerializer(subscription.tariff).data if subscription.tariff else None,
            "start_date": subscription.start_date,
            "end_date": subscription.end_date,
            "is_active": subscription.is_active,
            "days_left": max(days_left, 0),
            "expires_soon": 0 <= days_left <= 7,
            "expired": days_left < 0 or not subscription.is_active,
        })


class BillingHistoryView(APIView):
    """To'lov tarixi"""
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        summary="Tashkilotning to'lovlar va obunalar tarixi",
        description="Tashkilot tomonidan amalga oshirilgan barcha tarif xaridlari va to'lovlar tarixini xronologik tartibda qaytaradi.",
        responses={200: BillingHistorySerializer(many=True)},
        tags=["Billing"],
    )
    def get(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response([])
        history = BillingHistory.objects.filter(organization=org).order_by('-created_at')
        return Response(BillingHistorySerializer(history, many=True).data)


class BalanceTopUpView(APIView):
    """Balance yuklash — cheksiz"""
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        summary="Tashkilot hisob balansini to'ldirish",
        description="Tashkilotning ichki hisob balansiga ko'rsatilgan summani qo'shadi va to'ldirishlar tarixiga yozadi.",
        request=inline_serializer(
            name="BalanceTopUpRequest",
            fields={
                "amount": serializers.DecimalField(max_digits=12, decimal_places=2, help_text="To'ldiriladigan summa"),
                "comment": serializers.CharField(required=False, allow_blank=True, help_text="Izoh"),
            }
        ),
        responses={
            200: inline_serializer(
                name="BalanceTopUpResponse",
                fields={
                    "detail": serializers.CharField(),
                    "added": serializers.DecimalField(max_digits=12, decimal_places=2),
                    "balance": serializers.DecimalField(max_digits=12, decimal_places=2),
                }
            ),
            400: inline_serializer(
                name="BalanceTopUpErrorResponse",
                fields={"detail": serializers.CharField()}
            ),
        },
        tags=["Billing"],
    )
    def post(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({"detail": "Tashkilot topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = Decimal(str(request.data.get('amount', 0)))
            if amount <= 0:
                raise ValueError()
        except (InvalidOperation, ValueError):
            return Response({"detail": "Summa musbat bo'lishi kerak."}, status=status.HTTP_400_BAD_REQUEST)

        # Subscriptionni topish yoki yaratish
        subscription, _ = Subscription.objects.get_or_create(
            organization=org,
            defaults={
                'start_date': datetime.date.today(),
                'end_date': datetime.date.today(),
                'is_active': False,
                'balance': Decimal("0.00"),
            }
        )

        # Balancega qo'shish — cheksiz
        subscription.balance += amount
        subscription.save(update_fields=['balance'])

        # Tarix saqlash
        BalanceTopUp.objects.create(
            organization=org,
            amount=amount,
            comment=request.data.get('comment', '')
        )

        return Response({
            "detail": "Balance muvaffaqiyatli yuklandi.",
            "added": amount,
            "balance": subscription.balance,
        })


class SubscribePreviewView(APIView):
    """
    Tarif sotib olishdan OLDIN eslatma ko'rsatadi.
    Balancedan yechmaydi — faqat ma'lumot beradi.
    """
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        summary="Tarifni sotib olishdan oldingi hisob-kitob ko'rigi (Preview)",
        description="Foydalanuvchi tanlagan tarifni sotib olishdan oldin hisobdagi mablag' yetarliligini, keyingi to'lov sanasini va qoladigan qoldiqni hisoblab ko'rsatadi (balansdan mablag' yechilmaydi).",
        request=inline_serializer(
            name="SubscribePreviewRequest",
            fields={
                "tariff_id": serializers.IntegerField(help_text="Tanlangan tarif ID si"),
            }
        ),
        responses={
            200: inline_serializer(
                name="SubscribePreviewResponse",
                fields={
                    "tariff": TariffSerializer(),
                    "price": serializers.DecimalField(max_digits=12, decimal_places=2),
                    "balance": serializers.DecimalField(max_digits=12, decimal_places=2),
                    "balance_after": serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True),
                    "enough_balance": serializers.BooleanField(),
                    "charge_date": serializers.DateField(),
                    "warning": serializers.CharField(allow_null=True),
                    "confirm_message": serializers.CharField(allow_null=True),
                }
            ),
            400: inline_serializer(
                name="SubscribePreviewErrorResponse",
                fields={"detail": serializers.CharField()}
            ),
        },
        tags=["Billing"],
    )
    def post(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({"detail": "Tashkilot topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        tariff_id = request.data.get('tariff_id')
        if not tariff_id:
            return Response({"detail": "tariff_id majburiy."}, status=status.HTTP_400_BAD_REQUEST)

        tariff = Tariff.objects.filter(id=tariff_id).first()
        if not tariff:
            return Response({"detail": "Tarif topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        subscription = Subscription.objects.filter(organization=org).first()
        balance = subscription.balance if subscription else Decimal("0.00")
        price = tariff.final_price
        enough = balance >= price

        today = datetime.date.today()
        charge_date = add_months(today, tariff.months)

        return Response({
            "tariff": TariffSerializer(tariff).data,
            "price": price,
            "balance": balance,
            "balance_after": balance - price if enough else None,
            "enough_balance": enough,
            "charge_date": charge_date,  # keyingi yechish sanasi
            "warning": None if enough else f"Balancingiz yetarli emas. Kerak: {price}, Mavjud: {balance}",
            "confirm_message": f"Balancingizdan {price} UZS yechiladi. Tasdiqlaysizmi?" if enough else None,
        })


class SubscribeConfirmView(APIView):
    """
    Foydalanuvchi tasdiqlagan — balancedan yechadi va subscriptionni yangilaydi.
    """
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        summary="Tarif xaridini tasdiqlash va faollashtirish",
        description="Foydalanuvchi hisob balansidan tanlangan tarif summasini yechib oladi, obunani belgilangan muddatga uzaytiradi/faollashtiradi va tasdiqlangan so'rov yaratadi.",
        request=inline_serializer(
            name="SubscribeConfirmRequest",
            fields={
                "tariff_id": serializers.IntegerField(help_text="Faollashtirilayotgan tarif ID si"),
            }
        ),
        responses={
            200: inline_serializer(
                name="SubscribeConfirmResponse",
                fields={
                    "detail": serializers.CharField(),
                    "tariff": serializers.CharField(),
                    "deducted": serializers.DecimalField(max_digits=12, decimal_places=2),
                    "balance": serializers.DecimalField(max_digits=12, decimal_places=2),
                    "start_date": serializers.DateField(allow_null=True),
                    "end_date": serializers.DateField(allow_null=True),
                    "next_charge_date": serializers.DateField(allow_null=True),
                    "request_id": serializers.IntegerField(),
                }
            ),
            400: inline_serializer(
                name="SubscribeConfirmErrorResponse",
                fields={
                    "detail": serializers.CharField(),
                    "required": serializers.DecimalField(max_digits=12, decimal_places=2, required=False),
                    "balance": serializers.DecimalField(max_digits=12, decimal_places=2, required=False),
                    "missing": serializers.DecimalField(max_digits=12, decimal_places=2, required=False),
                }
            ),
        },
        tags=["Billing"],
    )
    def post(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({"detail": "Tashkilot topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        tariff_id = request.data.get('tariff_id')
        if not tariff_id:
            return Response({"detail": "tariff_id majburiy."}, status=status.HTTP_400_BAD_REQUEST)

        tariff = Tariff.objects.filter(id=tariff_id).first()
        if not tariff:
            return Response({"detail": "Tarif topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        subscription, _ = Subscription.objects.get_or_create(
            organization=org,
            defaults={
                'start_date': datetime.date.today(),
                'end_date': datetime.date.today(),
                'is_active': False,
                'balance': Decimal("0.00"),
            }
        )

        price = tariff.final_price

        # Balance yetarlimi?
        if subscription.balance < price:
            return Response({
                "detail": "Mablag' yetarli emas.",
                "required": price,
                "balance": subscription.balance,
                "missing": price - subscription.balance,
            }, status=status.HTTP_400_BAD_REQUEST)

        # Balancedan yechish
        subscription.balance -= price
        subscription.save()

        approved_request = SubscriptionRequest.objects.create(
            organization=org,
            tariff=tariff,
            months=tariff.months,
            amount=price,
            status='approved',
            comment="Tarif tasdiqlash orqali faollashtirildi",
        )

        subscription = Subscription.objects.filter(organization=org).first()
        start = subscription.start_date if subscription else None
        end = subscription.end_date if subscription else None
        next_charge = end

        return Response({
            "detail": "Tarif muvaffaqiyatli faollashtirildi.",
            "tariff": tariff.name,
            "deducted": price,
            "balance": subscription.balance,
            "start_date": start,
            "end_date": end,
            "next_charge_date": next_charge,
            "request_id": approved_request.id,
        })


class BillingPayView(APIView):
    """Tarif sotib olish so'rovini yuboradi (Django Adminda tasdiqlash uchun)"""
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        summary="Tarif sotib olish bo'yicha so'rov yuborish",
        description="Admin yoki operatorlar bilan bog'lanish va to'lov orqali faollashtirish uchun obuna so'rovini (SubscriptionRequest) 'pending' holatida yaratadi.",
        request=inline_serializer(
            name="BillingPayRequest",
            fields={
                "tariff_id": serializers.IntegerField(required=False, help_text="Tarif ID si"),
                "plan": serializers.CharField(required=False, help_text="Tarif nomi"),
                "months": serializers.IntegerField(required=False, default=1, help_text="Oylar soni"),
                "amount": serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0.00, help_text="To'lov summasi"),
            }
        ),
        responses={
            201: inline_serializer(
                name="BillingPayResponse",
                fields={
                    "status": serializers.CharField(),
                    "detail": serializers.CharField(),
                    "request_id": serializers.IntegerField(),
                }
            ),
            400: inline_serializer(
                name="BillingPayErrorResponse",
                fields={
                    "status": serializers.CharField(required=False),
                    "detail": serializers.CharField(),
                }
            ),
        },
        tags=["Billing"],
    )
    def post(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({"detail": "Tashkilot topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        tariff_id = request.data.get('tariff_id')
        plan_name = request.data.get('plan')
        try:
            months = int(request.data.get('months', 1))
            if months <= 0:
                raise ValueError()
        except ValueError:
            return Response({"detail": "Months must be a positive integer."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = Decimal(str(request.data.get('amount', 0)))
            if amount < 0:
                raise ValueError()
        except (InvalidOperation, ValueError):
            return Response({"detail": "Amount must be a positive decimal."}, status=status.HTTP_400_BAD_REQUEST)

        # Tarifni topish: avval tariff_id bo'yicha, keyin nom bo'yicha
        tariff = None
        if tariff_id:
            tariff = Tariff.objects.filter(id=tariff_id).first()
        if not tariff and plan_name:
            tariff = Tariff.objects.filter(name__iexact=plan_name, months=months).first()
            if not tariff:
                tariff = Tariff.objects.filter(name__iexact=plan_name).first()

        if not tariff:
            return Response({"detail": "Tarif rejasi topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        # Allaqachon pending so'rov borligini tekshirish
        existing_pending = SubscriptionRequest.objects.filter(
            organization=org,
            status='pending'
        ).first()
        if existing_pending:
            return Response({
                "status": "warning",
                "detail": "Sizda allaqachon ko'rib chiqilayotgan so'rov mavjud. Iltimos, javobini kuting."
            }, status=status.HTTP_400_BAD_REQUEST)

        # SubscriptionRequest yaratish (tasdiqlash kutayotgan so'rov)
        sub_request = SubscriptionRequest.objects.create(
            organization=org,
            tariff=tariff,
            months=months,
            amount=amount,
            status='pending',
            comment=f"Foydalanuvchi tomonidan tanlangan: {tariff.name} ({months} oy)"
        )

        return Response({
            "status": "success",
            "detail": "Obunani faollashtirish so'rovi qabul qilindi. Tez orada sotuvchilarimiz siz bilan bog'lanishadi.",
            "request_id": sub_request.id,
        }, status=status.HTTP_201_CREATED)


class SubscriptionRequestListView(APIView):
    """Foydalanuvchi o'z tashkilotining obuna so'rovlarini ko'radi"""
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        summary="Tashkilotning obuna so'rovlari ro'yxati",
        description="Tashkilot tomonidan yuborilgan barcha obuna so'rovlari (kutilmoqda, tasdiqlangan, rad etilgan) va ularning holatini qaytaradi.",
        responses={
            200: inline_serializer(
                name="SubscriptionRequestItemResponse",
                many=True,
                fields={
                    "id": serializers.IntegerField(),
                    "tariff_name": serializers.CharField(),
                    "months": serializers.IntegerField(),
                    "amount": serializers.CharField(),
                    "status": serializers.CharField(),
                    "status_display": serializers.CharField(),
                    "comment": serializers.CharField(),
                    "created_at": serializers.CharField(),
                }
            )
        },
        tags=["Billing"],
    )
    def get(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response([])
        requests = SubscriptionRequest.objects.filter(
            organization=org
        ).select_related('tariff').order_by('-created_at')
        data = []
        for req in requests:
            data.append({
                "id": req.id,
                "tariff_name": req.tariff.name if req.tariff else "-",
                "months": req.months,
                "amount": str(req.amount),
                "status": req.status,
                "status_display": req.get_status_display(),
                "comment": req.comment or "",
                "created_at": req.created_at.isoformat() if req.created_at else "",
            })
        return Response(data)

