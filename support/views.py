from rest_framework import viewsets, permissions, status, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from organizations.mixins import TenantViewSetMixin
from organizations.permissions import IsAdminOrOwnerOrReadOnly
from support.models import FAQCategory, FAQItem, ChatSession, SupportTicket
from support.serializers import (
    FAQCategorySerializer, FAQItemSerializer, ChatSessionSerializer,
    ChatInputSerializer, SupportTicketSerializer
)
from support.services.chat import AIChatService
from django.utils import timezone


@extend_schema_view(
    list=extend_schema(summary="FAQ kategoriyalari ro'yxati", tags=['Support & FAQ']),
    create=extend_schema(summary="Yangi FAQ kategoriya yaratish", tags=['Support & FAQ']),
    retrieve=extend_schema(summary="FAQ kategoriya tafsilotlari", tags=['Support & FAQ']),
    update=extend_schema(summary="FAQ kategoriyani to'liq yangilash", tags=['Support & FAQ']),
    partial_update=extend_schema(summary="FAQ kategoriyani qisman yangilash", tags=['Support & FAQ']),
    destroy=extend_schema(summary="FAQ kategoriyani o'chirish", tags=['Support & FAQ']),
)
class FAQCategoryViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    queryset = FAQCategory.objects.all()
    serializer_class = FAQCategorySerializer


@extend_schema_view(
    list=extend_schema(summary="FAQ savol-javoblar ro'yxati", tags=['Support & FAQ']),
    create=extend_schema(summary="Yangi FAQ savol-javob yaratish", tags=['Support & FAQ']),
    retrieve=extend_schema(summary="FAQ savol-javob tafsiloti", tags=['Support & FAQ']),
    update=extend_schema(summary="FAQ savol-javobni to'liq yangilash", tags=['Support & FAQ']),
    partial_update=extend_schema(summary="FAQ savol-javobni qisman yangilash", tags=['Support & FAQ']),
    destroy=extend_schema(summary="FAQ savol-javobni o'chirish", tags=['Support & FAQ']),
)
class FAQItemViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    queryset = FAQItem.objects.all()
    serializer_class = FAQItemSerializer
    filterset_fields = ['category', 'is_active']
    search_fields = ['question', 'answer']


@extend_schema(
    summary="Sun'iy intellekt (AI) yordamchi bilan suhbat",
    description="Foydalanuvchi xabarlarini qabul qilib, FAQ bazasi yoki LLM orqali AI javobini qaytaradi. Ishonch past bo'lsa yoki operator so'ralsa, avtomatik Support Ticket ochadi.",
    tags=['Support & AI Chat'],
    request=ChatInputSerializer,
    responses={
        200: inline_serializer(
            name='AIChatResponse',
            fields={
                'session_id': serializers.UUIDField(help_text="Suhbat sessiyasi identifikatori"),
                'answer': serializers.CharField(help_text="AI yoki FAQ javob matni"),
                'confidence': serializers.FloatField(help_text="Javob ishonch darajasi (0.0 dan 1.0 gacha)"),
                'source': serializers.CharField(help_text="Javob manbasi ('faq' yoki 'llm')"),
                'ticket_created': serializers.BooleanField(help_text="Yordam chiptasi yaratilganligi holati"),
                'ticket_id': serializers.IntegerField(allow_null=True, help_text="Yaratilgan chipta ID raqami")
            }
        )
    }
)
class ChatAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = ChatInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        session_id = serializer.validated_data.get('session_id')
        message = serializer.validated_data.get('message')
        
        org_id = getattr(request.user, 'organization_id', None)
        if not org_id:
            return Response(
                {"detail": "Foydalanuvchining tashkilot ID si aniqlanmadi."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        result = AIChatService.handle_chat_message(
            session_id_str=str(session_id) if session_id else None,
            message=message,
            user=request.user,
            organization_id=org_id
        )
        
        return Response(result, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(summary="Suhbatlar tarixi ro'yxati", tags=['Support & AI Chat']),
    retrieve=extend_schema(summary="Suhbat tafsiloti va xabarlar tarixi", tags=['Support & AI Chat']),
)
class ChatHistoryViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    queryset = ChatSession.objects.all().prefetch_related('messages')
    serializer_class = ChatSessionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.role not in ('owner', 'admin'):
            # Non-admins can only see their own chat history
            qs = qs.filter(user=user)
        return qs


@extend_schema_view(
    list=extend_schema(summary="Qo'llab-quvvatlash chiptalari (Support Tickets) ro'yxati", tags=['Support & Tickets']),
    create=extend_schema(summary="Yangi qo'llab-quvvatlash chiptasi yaratish", tags=['Support & Tickets']),
    retrieve=extend_schema(summary="Chipta tafsilotlari", tags=['Support & Tickets']),
    update=extend_schema(summary="Chiptani to'liq yangilash (Holat, Administrator, Izoh)", tags=['Support & Tickets']),
    partial_update=extend_schema(summary="Chiptani qisman yangilash", tags=['Support & Tickets']),
    destroy=extend_schema(summary="Chiptani o'chirish", tags=['Support & Tickets']),
)
class SupportTicketViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    queryset = SupportTicket.objects.all()
    serializer_class = SupportTicketSerializer
    filterset_fields = ['status', 'priority']
    search_fields = ['title', 'description']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.role not in ('owner', 'admin'):
            # Regular users only see their own tickets
            qs = qs.filter(user=user)
        return qs

    def perform_create(self, serializer):
        serializer.validated_data['user'] = self.request.user
        super().perform_create(serializer)

    def perform_update(self, serializer):
        instance = self.get_object()
        new_status = serializer.validated_data.get('status', instance.status)
        if new_status in ('resolved', 'closed') and instance.status not in ('resolved', 'closed'):
            serializer.validated_data['resolved_at'] = timezone.now()
        elif new_status not in ('resolved', 'closed'):
            serializer.validated_data['resolved_at'] = None
            
        super().perform_update(serializer)
