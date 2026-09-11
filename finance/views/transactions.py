from django.db import transaction as db_transaction
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import viewsets, permissions, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response

from organizations.mixins import TenantViewSetMixin
from finance.models import Transaction, TransactionCategory, Cashbox, CashTransaction
from finance.serializers import (
    TransactionSerializer, TransactionCategorySerializer,
    CashTransactionSerializer, CashTransferSerializer
)


@extend_schema_view(
    list=extend_schema(summary="Barcha tranzaksiyalar ro'yxati", tags=['Finance - Transactions']),
    create=extend_schema(summary="Yangi tranzaksiya yaratish", tags=['Finance - Transactions']),
    retrieve=extend_schema(summary="Tranzaksiya tafsilotlari", tags=['Finance - Transactions']),
    update=extend_schema(summary="Tranzaksiyani to'liq yangilash", tags=['Finance - Transactions']),
    partial_update=extend_schema(summary="Tranzaksiyani qisman yangilash", tags=['Finance - Transactions']),
    destroy=extend_schema(summary="Tranzaksiyani o'chirish", tags=['Finance - Transactions']),
)
class TransactionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = Transaction.objects.select_related('organization', 'branch', 'cashbox', 'student', 'employee')
    serializer_class = TransactionSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['type', 'category', 'cashbox']
    search_fields = ['description', 'student__first_name', 'student__last_name', 'employee__username']
    ordering_fields = ['created_at', 'amount']
    ordering = ['-created_at']


@extend_schema(
    tags=['Finance - Transactions'],
    summary="Tranzaksiya turlari va kategoriyalari ro'yxati",
    description="Tizimda mavjud bo'lgan barcha tranzaksiya turlari (kirim, chiqim va h.k.) va kategoriyalar tanlovini qaytaradi.",
    responses={200: OpenApiTypes.OBJECT}
)
class TransactionTypesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        types = [{"key": key, "label": label} for key, label in Transaction.TRANSACTION_TYPES]
        categories = [{"key": key, "label": label} for key, label in Transaction.CATEGORY_CHOICES]
        return Response({"types": types, "categories": categories}, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(summary="Tranzaksiya kategoriyalari ro'yxati", tags=['Finance - Transactions']),
    create=extend_schema(summary="Yangi tranzaksiya kategoriyasi yaratish", tags=['Finance - Transactions']),
    retrieve=extend_schema(summary="Tranzaksiya kategoriyasi tafsiloti", tags=['Finance - Transactions']),
    update=extend_schema(summary="Tranzaksiya kategoriyasini to'liq yangilash", tags=['Finance - Transactions']),
    partial_update=extend_schema(summary="Tranzaksiya kategoriyasini qisman yangilash", tags=['Finance - Transactions']),
    destroy=extend_schema(summary="Tranzaksiya kategoriyasini o'chirish", tags=['Finance - Transactions']),
)
class TransactionCategoryViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = TransactionCategory.objects.all()
    serializer_class = TransactionCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['type']


@extend_schema(
    tags=['Finance - Transactions'],
    summary="Kassa tranzaksiyasini yaratish (Kirim/Chiqim)",
    description="Kassaga kirim yoki chiqim tranzaksiyasini yozish va kassa balansini avtomatik yangilash.",
    request=CashTransactionSerializer,
    responses={201: CashTransactionSerializer}
)
class TransactionCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        
        if not data.get('cashbox') and not data.get('cashbox_id'):
            cb = Cashbox.objects.filter(organization=request.user.organization).first()
            if cb:
                data['cashbox'] = cb.id

        serializer = CashTransactionSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            with db_transaction.atomic():
                cashbox = serializer.validated_data.get('cashbox')
                tx_type = serializer.validated_data.get('transaction_type')
                amount = serializer.validated_data.get('amount')
                if tx_type == 'chiqim' and cashbox and amount:
                    cb = Cashbox.objects.select_for_update().get(id=cashbox.id)
                    if cb.balance < amount:
                        bal_str = f"{int(cb.balance):,} UZS".replace(",", " ")
                        amt_str = f"{int(amount):,} UZS".replace(",", " ")
                        return Response({
                            "detail": f"Kassada mablag' yetarli emas! Kassadagi joriy balans: {bal_str}. Chiqim summasi: {amt_str}",
                            "cashbox": f"Kassada mablag' yetarli emas! (Balans: {bal_str})"
                        }, status=status.HTTP_400_BAD_REQUEST)

                serializer.save(organization=request.user.organization)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Finance - Transactions'],
    summary="Kassalararo pul o'tkazmasi (Transfer)",
    description="Bir kassadan ikkinchi kassaga pul o'tkazish (chiqim va kirim tranzaksiyalarini atomik ravishda yaratadi).",
    request=CashTransferSerializer,
    responses={201: OpenApiTypes.OBJECT}
)
class CashTransferAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)

        if 'from_cashbox' not in data:
            if 'cashbox' in data:
                data['from_cashbox'] = data['cashbox']
            elif 'from_cashbox_id' in data:
                data['from_cashbox'] = data['from_cashbox_id']

        if 'to_cashbox' not in data and 'to_cashbox_id' in data:
            data['to_cashbox'] = data['to_cashbox_id']

        if 'comment' not in data:
            if 'description' in data:
                data['comment'] = data['description']
            elif 'izoh' in data:
                data['comment'] = data['izoh']

        serializer = CashTransferSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            from_cashbox = serializer.validated_data['from_cashbox']
            to_cashbox = serializer.validated_data['to_cashbox']
            amount = serializer.validated_data['amount']
            comment = serializer.validated_data.get('comment') or "Kassalararo o'tkazma"

            with db_transaction.atomic():
                from_box = Cashbox.objects.select_for_update().get(id=from_cashbox.id)
                to_box = Cashbox.objects.select_for_update().get(id=to_cashbox.id)

                if from_box.balance < amount:
                    return Response(
                        {"detail": f"'{from_box.name}' kassasida yetarli mablag' yo'q (Balans: {from_box.balance})!"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                CashTransaction.objects.create(
                    organization=request.user.organization,
                    cashbox=from_box,
                    amount=amount,
                    transaction_type='chiqim',
                    payment_method='naqd',
                    date=timezone.now().date(),
                    employee=request.user,
                    category_name="Kassalararo o'tkazma",
                    comment=f"Kassalararo o'tkazma chiqim: {from_box.name} -> {to_box.name}. Izoh: {comment}"
                )

                CashTransaction.objects.create(
                    organization=request.user.organization,
                    cashbox=to_box,
                    amount=amount,
                    transaction_type='kirim',
                    payment_method='naqd',
                    date=timezone.now().date(),
                    employee=request.user,
                    category_name="Kassalararo o'tkazma",
                    comment=f"Kassalararo o'tkazma kirim: {from_box.name} -> {to_box.name}. Izoh: {comment}"
                )

            # Muvaffaqiyatli javob qaytarish
            return Response({
                "detail": f"{amount} UZS kassalararo muvaffaqiyatli o'tkazildi!",
                "from_cashbox": from_box.id,
                "to_cashbox": to_box.id,
                "amount": float(amount)
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

