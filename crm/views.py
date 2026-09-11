from rest_framework import viewsets, permissions, serializers
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer, OpenApiParameter

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import IsAdminOrOwnerOrReadOnly
from crm.models import Pipeline, Source, LostReason, Section, LeadForm, Lead
from crm.serializers import (
    PipelineSerializer, SourceSerializer, LostReasonSerializer,
    SectionSerializer, LeadFormSerializer, LeadSerializer
)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Lead, CRMLeadsHistory
from .serializers import CRMLeadsHistorySerializer, PublicLeadSubmitSerializer, LeadFormCRUDSerializer
from django.contrib.auth.hashers import make_password


@extend_schema_view(
    list=extend_schema(summary="Voronkalar (Pipelines) ro'yxati", description="Tashkilotdagi barcha sotuv voronkalari va ularning ustunlari (Sections) ro'yxati.", tags=["CRM"]),
    retrieve=extend_schema(summary="Voronka tafsilotlari", description="Bitta sotuv voronkasi ma'lumotlarini ko'rish.", tags=["CRM"]),
    create=extend_schema(summary="Yangi voronka yaratish", description="Yangi savdo voronkasi (Pipeline) qo'shadi.", tags=["CRM"]),
    update=extend_schema(summary="Voronkani to'liq yangilash", description="Mavjud voronka nomi va ketma-ketlik tartibini to'liq yangilash.", tags=["CRM"]),
    partial_update=extend_schema(summary="Voronkani qisman yangilash", description="Voronka parametrlarini qisman o'zgartirish.", tags=["CRM"]),
    destroy=extend_schema(summary="Voronkani o'chirish", description="Faol lidlari bo'lmagan voronkani o'chirish.", tags=["CRM"]),
)
class PipelineViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = Pipeline.objects.all()
    serializer_class = PipelineSerializer

    def destroy(self, request, *args, **kwargs):
        pipeline = self.get_object()
        # Check if there are active (not won/lost/archived) leads in this pipeline
        if pipeline.leads.filter(is_archived=False).exists():
            return Response({"detail": "Naborda faol lidlar mavjudligi sababli uni o'chirish mumkin emas. Avval lidlarni boshqa naborga o'tkazing yoki arxivlang."}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)


@extend_schema_view(
    list=extend_schema(summary="Lid manbalari (Sources) ro'yxati", description="Lidlar kelib tushadigan reklama va tavsiya manbalari (Instagram, Telegram, Banner va h.k.).", tags=["CRM"]),
    retrieve=extend_schema(summary="Manba tafsiloti", description="Bitta lid manbasi ma'lumotlarini ko'rish.", tags=["CRM"]),
    create=extend_schema(summary="Yangi manba yaratish", description="Yangi lid manbasini qo'shadi.", tags=["CRM"]),
    update=extend_schema(summary="Manbani to'liq yangilash", description="Mavjud manba nomini to'liq yangilash.", tags=["CRM"]),
    partial_update=extend_schema(summary="Manbani qisman yangilash", description="Mavjud manba nomini qisman yangilash.", tags=["CRM"]),
    destroy=extend_schema(summary="Manbani o'chirish", description="Lid manbasini o'chirish.", tags=["CRM"]),
)
class SourceViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = Source.objects.all()
    serializer_class = SourceSerializer


@extend_schema_view(
    list=extend_schema(summary="Yo'qotish sabablari (Lost Reasons) ro'yxati", description="Mijoz xarid qilmagan yoki rad etgan holatlar uchun sabablar ro'yxati.", tags=["CRM"]),
    retrieve=extend_schema(summary="Yo'qotish sababi tafsiloti", description="Bitta yo'qotish sababi ma'lumotlarini ko'rish.", tags=["CRM"]),
    create=extend_schema(summary="Yangi yo'qotish sababini qo'shish", description="Yangi rad etish/yo'qotish sababini qo'shadi.", tags=["CRM"]),
    update=extend_schema(summary="Yo'qotish sababini to'liq yangilash", description="Mavjud sabab matnini to'liq yangilash.", tags=["CRM"]),
    partial_update=extend_schema(summary="Yo'qotish sababini qisman yangilash", description="Mavjud sabab matnini qisman yangilash.", tags=["CRM"]),
    destroy=extend_schema(summary="Yo'qotish sababini o'chirish", description="Yo'qotish sababini o'chirish.", tags=["CRM"]),
)
class LostReasonViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = LostReason.objects.all()
    serializer_class = LostReasonSerializer


@extend_schema_view(
    list=extend_schema(summary="Voronka ustunlari (Sections) ro'yxati", description="Voronka ichidagi bosqichlar (ustunlar) ro'yxati.", tags=["CRM"]),
    retrieve=extend_schema(summary="Ustun tafsiloti", description="Bitta voronka ustuni ma'lumotlarini ko'rish.", tags=["CRM"]),
    create=extend_schema(summary="Yangi ustun qo'shish", description="Voronka ichiga yangi bosqich ustunini qo'shadi.", tags=["CRM"]),
    update=extend_schema(summary="Ustunni to'liq yangilash", description="Ustun nomi va tegishli voronkasini to'liq yangilash.", tags=["CRM"]),
    partial_update=extend_schema(summary="Ustunni qisman yangilash", description="Ustun ma'lumotlarini qisman yangilash.", tags=["CRM"]),
    destroy=extend_schema(summary="Ustunni o'chirish", description="Faol lidlari bo'lmagan ustunni o'chirish.", tags=["CRM"]),
)
class SectionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = Section.objects.all()
    serializer_class = SectionSerializer

    def destroy(self, request, *args, **kwargs):
        section = self.get_object()
        if section.leads.filter(is_archived=False).exists():
            return Response({"detail": "Ustunda faol lidlar mavjudligi sababli uni o'chirish mumkin emas. Avval lidlarni boshqa ustunga o'tkazing yoki arxivlang."}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)


@extend_schema_view(
    list=extend_schema(summary="Lid yig'ish formalari ro'yxati", description="Tashkilotning lid yig'ish formalari (Lead Forms) ro'yxati.", tags=["CRM"]),
    retrieve=extend_schema(summary="Lid forma tafsiloti", description="Bitta lid formasi dizayni va maydonlari.", tags=["CRM"]),
    create=extend_schema(summary="Yangi lid forma yaratish", description="Tashqi saytlar yoki landing sahifalar uchun yangi lid yig'ish formasini yaratadi.", tags=["CRM"]),
    update=extend_schema(summary="Lid formani to'liq yangilash", description="Forma sozlamalari, logotipi va ranglarini to'liq yangilash.", tags=["CRM"]),
    partial_update=extend_schema(summary="Lid formani qisman yangilash", description="Forma parametrlarini qisman yangilash.", tags=["CRM"]),
    destroy=extend_schema(summary="Lid formani o'chirish", description="Mavjud lid formasini o'chirish.", tags=["CRM"]),
)
class LeadFormViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = LeadForm.objects.all()
    serializer_class = LeadFormSerializer

from rest_framework import status
from rest_framework.response import Response
from django.utils import timezone
from rest_framework.decorators import action


@extend_schema_view(
    list=extend_schema(summary="Faol lidlar ro'yxati", description="Filtrlar (voronka, manba, status, moderator, ustun) bo'yicha saralangan faol lidlar ro'yxati.", tags=["CRM"]),
    retrieve=extend_schema(summary="Lid tafsilotlari", description="Bitta lidning barcha ma'lumotlari, kontaktlari va biriktirilgan mas'ullarini ko'rish.", tags=["CRM"]),
    create=extend_schema(summary="Yangi lid yaratish", description="CRM tizimiga yangi potensial mijoz (Lid) qo'shadi.", tags=["CRM"]),
    update=extend_schema(summary="Lidni to'liq yangilash", description="Lid ma'lumotlarini to'liq tahrirlash.", tags=["CRM"]),
    partial_update=extend_schema(summary="Lidni qisman yangilash (bosqich/status o'zgartirish)", description="Lidning ustunini (drag-and-drop), statusini yoki izohini qisman yangilash.", tags=["CRM"]),
    destroy=extend_schema(summary="Lidni arxivlash yoki butunlay o'chirish", description="Faol lidni arxivlaydi, agar allaqachon arxivda bo'lsa butunlay o'chiradi.", tags=["CRM"]),
)
class LeadViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    serializer_class = LeadSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['pipeline', 'source', 'status','moderator']
    search_fields = ['name', 'phone', 'email']

    def perform_create(self, serializer):
        org_id = self.get_organization_id()
        if not org_id:
            from rest_framework import exceptions
            raise exceptions.ValidationError({"detail": "Organization context is required."})

        kwargs = {'organization_id': org_id}
        if self.request.user and self.request.user.is_authenticated:
            kwargs['created_by'] = self.request.user

        branch_id = self.get_branch_id()
        if branch_id:
            kwargs['branch_id'] = branch_id

        serializer.save(**kwargs)

    def get_queryset(self):
        org_id = self.get_organization_id()
        if not org_id:
            return Lead.objects.none()

        from django.db.models import Q
        branch_id = self.get_branch_id()

        # select_related orqali barcha bog'liqliklar bitta SQL JOINda olinadi
        queryset = Lead.objects.filter(organization_id=org_id).select_related(
            'pipeline', 'source', 'section', 'lost_reason', 'created_by', 'moderator', 'referred_by', 'branch'
        )

        # Branch filtri
        if branch_id:
            queryset = queryset.filter(Q(branch_id=branch_id) | Q(branch__isnull=True))

        if self.action == 'archived':
            return queryset.filter(is_archived=True)

        if self.action in ['destroy', 'retrieve', 'partial_update', 'update']:
            return queryset

        queryset = queryset.filter(is_archived=False)

        section_param = self.request.query_params.get('section')
        if section_param is not None:
            if section_param in ['null', 'None', '']:
                queryset = queryset.filter(section__isnull=True)
            else:
                queryset = queryset.filter(section_id=section_param)
                
        return queryset

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_archived:
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            reason = request.query_params.get('reason') or request.data.get('reason') or "O'chirilgan"
            instance.is_archived = True
            instance.archive_reason = reason
            instance.archive_date = timezone.now()
            instance.archived_by = request.user.get_full_name() or request.user.username
            instance.save(update_fields=['is_archived', 'archive_reason', 'archive_date', 'archived_by'])
            return Response({"detail": "Lead archived successfully.", "id": instance.id}, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Arxivlangan lidlar ro'yxati",
        description="Arxivga olingan yoki o'chirilgan barcha lidlar ro'yxatini qaytaradi.",
        responses={200: LeadSerializer(many=True)},
        tags=["CRM"],
    )
    @action(detail=False, methods=['get'], url_path='archived')
    def archived(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Lidlarni ommaviy yuklash (Excel / Bulk Import)",
        description="Tashqi fayl yoki ro'yxatdan kelgan ko'plab lidlarni bir vaqtning o'zida bazaga yuklaydi va hisobotini qaytaradi.",
        request=inline_serializer(
            name="LeadBulkCreateRequest",
            fields={
                "leads": serializers.ListField(child=serializers.DictField(), help_text="Lidlar ob'ektlari ro'yxati")
            }
        ),
        responses={
            200: inline_serializer(
                name="LeadBulkCreateResponse",
                fields={
                    "success_count": serializers.IntegerField(),
                    "failed_count": serializers.IntegerField(),
                    "errors": serializers.ListField(child=serializers.DictField()),
                }
            ),
            400: inline_serializer(
                name="LeadBulkCreateError",
                fields={"detail": serializers.CharField()}
            ),
        },
        tags=["CRM"],
    )
    @action(detail=False, methods=['post'], url_path='bulk-create')
    def bulk_create(self, request):
        leads_data = request.data.get('leads', [])
        if not isinstance(leads_data, list):
            return Response({"detail": "Leads must be a list"}, status=status.HTTP_400_BAD_REQUEST)
            
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        branch_id = self.get_branch_id()

        success_count = 0
        failed_count = 0
        errors = []
        
        for idx, item in enumerate(leads_data):
            row_num = item.get('row', idx + 1)
            # Use serializer to validate
            serializer = self.get_serializer(data=item)
            if serializer.is_valid():
                try:
                    kwargs = {'organization_id': org_id}
                    if request.user and request.user.is_authenticated:
                        kwargs['created_by'] = request.user
                    if branch_id:
                        kwargs['branch_id'] = branch_id
                    serializer.save(**kwargs)
                    success_count += 1
                except Exception as e:
                    failed_count += 1
                    errors.append({
                        "row": row_num,
                        "name": item.get('name', item.get('full_name', '')),
                        "detail": str(e)
                    })
            else:
                failed_count += 1
                # Format validation errors
                err_msg = ""
                for field, msgs in serializer.errors.items():
                    err_msg += f"{field}: {', '.join([str(m) for m in msgs])}; "
                errors.append({
                    "row": row_num,
                    "name": item.get('name', item.get('full_name', '')),
                    "detail": err_msg
                })
                
        return Response({
            "success_count": success_count,
            "failed_count": failed_count,
            "errors": errors
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Lid uchun talaba yoki ota-ona login/parolini o'rnatish",
        description="Lid botga yoki shaxsiy kabinetga kirishi uchun login va parolini o'rnatadi.",
        request=inline_serializer(
            name="LeadSetLoginPasswordRequest",
            fields={
                "type": serializers.ChoiceField(choices=["student", "parent"], help_text="Foydalanuvchi turi"),
                "login": serializers.CharField(help_text="Login"),
                "password": serializers.CharField(help_text="Parol"),
            }
        ),
        responses={
            200: inline_serializer(name="LeadSetLoginPasswordResponse", fields={"message": serializers.CharField()}),
            400: inline_serializer(name="LeadSetLoginPasswordError", fields={"error": serializers.CharField()}),
        },
        tags=["CRM"],
    )
    @action(detail=True, methods=['post'], url_path='set-login-password')
    def set_login_password(self, request, pk=None):
        lead = self.get_object()
        user_type = request.data.get('type')  # frontend 'student' yoki 'parent' yuboradi
        login = request.data.get('login')
        password = request.data.get('password')

        if not login or not password:
            return Response({"error": "Login va parol yuborilishi majburiy!"}, status=status.HTTP_400_BAD_REQUEST)

        # Parolni xavfsiz shifrlab saqlaymiz
        encrypted_password = make_password(password)

        if user_type == 'student':
            lead.student_login = login
            lead.student_password = encrypted_password
            lead.save()
            return Response({"message": "Talaba uchun login va parol muvaffaqiyatli o'rnatildi."},
                            status=status.HTTP_200_OK)

        elif user_type == 'parent':
            lead.parent_login = login
            lead.parent_password = encrypted_password
            lead.save()
            return Response({"message": "Ota-ona uchun login va parol muvaffaqiyatli o'rnatildi."},
                            status=status.HTTP_200_OK)

        return Response({"error": "Noto'g'ri 'type' yuborildi. ('student' yoki 'parent' bo'lishi kerak)"},
                        status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Lidga mas'ul moderator biriktirish",
        description="Lid bo'yicha muloqot qiluvchi xodimni (moderator) tayinlaydi.",
        request=inline_serializer(
            name="LeadAssignModeratorRequest",
            fields={
                "moderator_id": serializers.IntegerField(help_text="Xodim (Moderator) ID si"),
            }
        ),
        responses={
            200: inline_serializer(name="LeadAssignModeratorResponse", fields={"message": serializers.CharField()}),
            400: inline_serializer(name="LeadAssignModeratorError", fields={"error": serializers.CharField()}),
        },
        tags=["CRM"],
    )
    @action(detail=True, methods=['post'], url_path='assign-moderator')
    def assign_moderator(self, request, pk=None):
        lead = self.get_object()
        moderator_id = request.data.get('moderator_id')  # frontend xodimning ID sini yuboradi

        if not moderator_id:
            return Response({"error": "Moderator ID si yuborilmadi!"}, status=status.HTTP_400_BAD_REQUEST)

        lead.moderator_id = moderator_id
        lead.save()
        return Response({"message": "Mas'ul moderator muvaffaqiyatli biriktirildi."}, status=status.HTTP_200_OK)


from rest_framework import mixins

class CreateListRetrieveViewSet(mixins.CreateModelMixin,
                                mixins.ListModelMixin,
                                mixins.RetrieveModelMixin,
                                viewsets.GenericViewSet):
    """
    Ruxsatnomalarga ko'ra faqat yaratish, ro'yxatni olish va bittalik ko'rishga 
    ruxsat beruvchi, lekin tahrirlash (update) va o'chirishni (delete) cheklovchi maxsus ViewSet.
    """
    pass

from crm.models import CRMActivity, CRMLeadsHistory, CRMLeadLost
from crm.serializers import CRMActivitySerializer, CRMLeadsHistorySerializer, CRMLeadLostSerializer


@extend_schema_view(
    list=extend_schema(summary="CRM harakatlari (Activities) ro'yxati", description="Lidlar bo'yicha amalga oshirilgan qo'ng'iroqlar, uchrashuvlar va vazifalar.", tags=["CRM"]),
    retrieve=extend_schema(summary="CRM harakati tafsiloti", description="Bitta harakat tafsilotlarini ko'rish.", tags=["CRM"]),
    create=extend_schema(summary="Yangi CRM harakati qo'shish", description="Lidga yangi qo'ng'iroq yoki eslatma harakatini biriktiradi.", tags=["CRM"]),
    update=extend_schema(summary="CRM harakatini to'liq yangilash", description="Harakat ma'lumotlarini to'liq yangilash.", tags=["CRM"]),
    partial_update=extend_schema(summary="CRM harakatini qisman yangilash", description="Harakat parametrlarini qisman yangilash.", tags=["CRM"]),
    destroy=extend_schema(summary="CRM harakatini o'chirish", description="Mavjud CRM harakatini o'chirish.", tags=["CRM"]),
)
class CRMActivityViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = CRMActivity.objects.all()
    serializer_class = CRMActivitySerializer


class LeadHistoryAPIView(APIView):
    """
    Muayyan lidning yoki umumiy lidlar tarixini (o'zgarishlar xronologiyasini) olib beruvchi API
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Lidning o'zgarishlar tarixi (Xronologiya)",
        description="Muayyan lid (lead_id) yoki tashkilotdagi umumiy lidlar o'zgarishlari xronologiyasini qaytaradi.",
        parameters=[
            OpenApiParameter(name="lead_id", type=int, required=False, description="Muayyan lid ID si"),
            OpenApiParameter(name="lead", type=int, required=False, description="Muayyan lid ID si (alias)"),
        ],
        responses={
            200: inline_serializer(
                name="LeadHistoryResponse",
                fields={
                    "lead_id": serializers.IntegerField(required=False),
                    "lead_name": serializers.CharField(required=False),
                    "history": CRMLeadsHistorySerializer(many=True, required=False),
                }
            ),
            404: inline_serializer(name="LeadHistoryNotFound", fields={"error": serializers.CharField()}),
        },
        tags=["CRM"],
    )
    def get(self, request):
        lead_id = request.query_params.get('lead_id') or request.query_params.get('lead')
        org_id = getattr(request.user, 'organization_id', None)

        if lead_id and str(lead_id).isdigit():
            try:
                lead = Lead.objects.get(id=lead_id)
                history = CRMLeadsHistory.objects.filter(lead=lead).order_by('-created_at')
                serializer = CRMLeadsHistorySerializer(history, many=True)
                return Response({
                    "lead_id": lead.id,
                    "lead_name": lead.name,
                    "history": serializer.data
                }, status=status.HTTP_200_OK)
            except Lead.DoesNotExist:
                return Response(
                    {"error": "Lid topilmadi!"},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Umumiy lidlar tarixi (lead_id ko'rsatilmaganda)
        qs = CRMLeadsHistory.objects.all()
        if org_id:
            qs = qs.filter(lead__organization_id=org_id)
        history = qs.order_by('-created_at')[:100]
        serializer = CRMLeadsHistorySerializer(history, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(summary="Yo'qotilgan lidlar (Lost Leads) ro'yxati", description="Sotuv jarayonida rad etilgan/yo'qotilgan lidlar jurnali.", tags=["CRM"]),
    retrieve=extend_schema(summary="Yo'qotilgan lid tafsiloti", description="Bitta yo'qotilgan lid tafsilotlarini ko'rish.", tags=["CRM"]),
    create=extend_schema(summary="Lidni yo'qotilgan deb belgilash", description="Lidni yo'qotilgan sababi bilan jurnalga yozadi.", tags=["CRM"]),
)
class CRMLeadLostViewSet(TenantViewSetMixin, CreateListRetrieveViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = CRMLeadLost.objects.all()
    serializer_class = CRMLeadLostSerializer


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from academics.models import BotMessageTemplate, Student
from crm.models import Lead, Section
from .serializers import SMSBotTemplateSerializer
from django.contrib.auth import get_user_model

User = get_user_model()


@extend_schema_view(
    list=extend_schema(summary="SMS Bot shablonlari ro'yxati", description="Bot va SMS orqali yuboriladigan shablonlar ro'yxati.", tags=["CRM"]),
    create=extend_schema(summary="Yangi SMS Bot shabloni yaratish", description="Yangi bot yoki SMS shablonini qo'shadi.", tags=["CRM"]),
)
class SMSTemplateListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = SMSBotTemplateSerializer

    def get_queryset(self):
        queryset = BotMessageTemplate.objects.all()
        audience = self.request.query_params.get('audience')
        if audience:
            queryset = queryset.filter(target_audience=audience)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        organization = getattr(user, 'organization', None)

        if organization:
            serializer.save(organization=organization)
        else:
            from organizations.models import Organization
            first_org = Organization.objects.first()
            serializer.save(organization=first_org)


@extend_schema_view(
    retrieve=extend_schema(summary="SMS Bot shabloni tafsiloti", description="Bitta bot xabari shablonini ko'rish.", tags=["CRM"]),
    update=extend_schema(summary="SMS Bot shablonini to'liq yangilash", description="Shablon matni va maqsadli auditoriyasini to'liq yangilash.", tags=["CRM"]),
    partial_update=extend_schema(summary="SMS Bot shablonini qisman yangilash", description="Shablonni qisman yangilash.", tags=["CRM"]),
    destroy=extend_schema(summary="SMS Bot shablonini o'chirish", description="Mavjud shablonni o'chirib tashlash.", tags=["CRM"]),
)
class SMSTemplateRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = BotMessageTemplate.objects.all()
    serializer_class = SMSBotTemplateSerializer


class SendBulkSMSAPIView(APIView):

    @extend_schema(
        summary="Ommaviy SMS / Telegram xabar yuborish",
        description="Lidlar, talabalar yoki xodimlarga tanlangan shablon yoki erkin matn asosida Telegram/SMS xabar tarqatadi.",
        request=inline_serializer(
            name="SendBulkSMSRequest",
            fields={
                "target": serializers.ChoiceField(choices=["leads", "students", "staff"], help_text="Maqsadli guruh"),
                "section_id": serializers.IntegerField(required=False, help_text="Lidlar uchun ustun ID si"),
                "template_id": serializers.IntegerField(required=False, help_text="Shablon ID si"),
                "text": serializers.CharField(required=False, help_text="Xabar matni"),
            }
        ),
        responses={
            200: inline_serializer(
                name="SendBulkSMSResponse",
                fields={
                    "message": serializers.CharField(),
                    "total_recipients": serializers.IntegerField(),
                    "bot_registered_count": serializers.IntegerField(),
                    "bot_not_registered_count": serializers.IntegerField(),
                    "details": serializers.ListField(child=serializers.DictField()),
                }
            ),
            400: inline_serializer(name="SendBulkSMSError400", fields={"error": serializers.CharField()}),
            404: inline_serializer(name="SendBulkSMSError404", fields={"error": serializers.CharField()}),
        },
        tags=["CRM"],
    )
    def post(self, request):
        target = request.data.get('target')  # 'leads', 'students', 'staff'
        section_id = request.data.get('section_id')  # Agar 'leads' tanlansa, qaysi kanyatener (Section) id-si
        shablon_id = request.data.get('template_id')  # Tanlangan tayyor shablon IDsi (ixtiyoriy)
        custom_text = request.data.get('text')  # Qo'lda yozilgan matn (shablon tanlanmasa)

        if not target:
            return Response({"error": "target (leads, students, staff) yuborilishi majburiy!"},
                            status=status.HTTP_400_BAD_REQUEST)

        msg_text = custom_text
        if shablon_id:
            try:
                shablon = BotMessageTemplate.objects.get(id=shablon_id)
                msg_text = shablon.text
            except BotMessageTemplate.DoesNotExist:
                return Response({"error": "Tanlangan shablon topilmadi!"}, status=status.HTTP_404_NOT_FOUND)

        if not msg_text:
            return Response({"error": "Xabar matni bo'sh bo'lishi mumkin emas!"}, status=status.HTTP_400_BAD_REQUEST)

        recipients = []

        if target == 'leads':
            leads_query = Lead.objects.filter(is_archived=False)
            if section_id:
                leads_query = leads_query.filter(section_id=section_id)

            for lead in leads_query:
                recipients.append({
                    "id": lead.id,
                    "name": lead.name,
                    "phone": lead.phone,
                    "chat_id": None,
                    "context": {"{first_name}": lead.name, "{section_name}": lead.section.name if lead.section else ""}
                })

        elif target == 'students':
            students_query = Student.objects.filter(is_archived=False)
            for student in students_query:
                chat_id = student.telegram_chat_id or student.father_telegram_chat_id or student.mother_telegram_chat_id
                recipients.append({
                    "id": student.id,
                    "name": f"{student.first_name} {student.last_name or ''}".strip(),
                    "phone": student.phone,
                    "chat_id": chat_id,
                    "context": {"{first_name}": student.first_name, "{balance}": str(student.balance)}
                })

        elif target == 'staff':
            staff_query = User.objects.filter(is_active=True).exclude(role='student')
            for member in staff_query:
                chat_id = getattr(member, 'telegram_chat_id', None)
                recipients.append({
                    "id": member.id,
                    "name": member.get_full_name() or member.username,
                    "phone": getattr(member, 'phone', ''),
                    "chat_id": chat_id,
                    "context": {"{first_name}": member.username}
                })

        # 🚀 XABARLARNI ETKAZIB BERISH SIKLI VA BOTGA A'ZOLIK TEKSHIRUVI
        bot_registered_count = 0
        bot_not_registered_count = 0
        details = []

        from academics.telegram_bot import get_student_bot_token, get_report_bot_token, send_telegram_message
        from organizations.models import TelegramNotificationSetting

        for r in recipients:
            final_text = msg_text
            for placeholder, value in r['context'].items():
                final_text = final_text.replace(placeholder, str(value))

            is_bot_registered = bool(r['chat_id'])

            if is_bot_registered:
                bot_registered_count += 1
                try:
                    if target == 'students':
                        token = get_student_bot_token()
                    else:
                        setting = TelegramNotificationSetting.objects.first()
                        token = setting.staff_bot_token if (setting and setting.staff_bot_token) else get_report_bot_token()

                    sent = send_telegram_message(token, r['chat_id'], final_text)
                    status_str = "Botdan ro'yxatdan o'tgan — Telegram orqali yuborildi" if sent else "Botdan ro'yxatdan o'tgan, lekin yetkazishda xatolik"
                except Exception as e:
                    status_str = f"Botdan ro'yxatdan o'tgan — Xatolik: {str(e)}"
            else:
                bot_not_registered_count += 1
                status_str = "Botdan ro'yxatdan o'tmagan"

            details.append({
                "id": r.get('id'),
                "name": r['name'],
                "phone": r['phone'],
                "is_bot_registered": is_bot_registered,
                "status": status_str
            })

        return Response({
            "message": "Xabarlar yetkazib berish va bot ro'yxatdan o'tish tekshiruvi yakunlandi",
            "total_recipients": len(recipients),
            "bot_registered_count": bot_registered_count,
            "bot_not_registered_count": bot_not_registered_count,
            "details": details
        }, status=status.HTTP_200_OK)

from rest_framework.permissions import AllowAny
# ================= 1. ADMIN PANEL UCHUN (CRUD) =================
@extend_schema_view(
    list=extend_schema(summary="Lid formalari ro'yxati (Admin)", description="Adminlar uchun formalarni shakllantirish va ro'yxatini olish.", tags=["CRM"]),
    create=extend_schema(summary="Yangi lid forma yaratish (Admin)", description="Yangi tashqi forma yaratadi.", tags=["CRM"]),
)
class LeadFormListCreateAPIView(generics.ListCreateAPIView):
    """Adminlar uchun formalarni shakllantirish va ro'yxatini olish"""
    queryset = LeadForm.objects.all()
    serializer_class = LeadFormCRUDSerializer


@extend_schema_view(
    retrieve=extend_schema(summary="Lid forma tafsiloti (Admin)", description="Bitta forma parametrlarini ko'rish.", tags=["CRM"]),
    update=extend_schema(summary="Lid formani to'liq yangilash (Admin)", description="Formani to'liq yangilash.", tags=["CRM"]),
    partial_update=extend_schema(summary="Lid formani qisman yangilash (Admin)", description="Formani qisman yangilash.", tags=["CRM"]),
    destroy=extend_schema(summary="Lid formani o'chirish (Admin)", description="Formani o'chirish.", tags=["CRM"]),
)
class LeadFormRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Adminlar uchun formani tahrirlash (Edit), o'chirish (Delete) va bitta formani ko'rish"""
    queryset = LeadForm.objects.all()
    serializer_class = LeadFormCRUDSerializer


# ================= 2. TASHQI DUNYO (PUBLIC) UCHUN APILAR =================
@extend_schema_view(
    retrieve=extend_schema(summary="Ochiq lid formasi ko'rinishi (Public View)", description="Avtorizatsiyasiz ishlaydi. Landing sahifa formani chizishi uchun stil va fieldlarni oladi.", tags=["CRM Public"]),
)
class PublicLeadFormDetailAPIView(generics.RetrieveAPIView):
    """Avtorizatsiyasiz ishlaydi. Landing sahifa formani chizishi uchun stil va fieldlarni oladi"""
    queryset = LeadForm.objects.all()
    serializer_class = LeadFormCRUDSerializer
    permission_classes = [AllowAny] # Login shart emas!


class PublicLeadSubmitAPIView(APIView):
    """Mijoz formani to'ldirib 'Sumbit' qilganda ishlaydigan API"""
    permission_classes = [AllowAny] # Login shart emas!

    @extend_schema(
        summary="Ochiq formadan yangi lid yuborish (Public Submit)",
        description="Landing sahifadagi tashrif buyuruvchi formani to'ldirib yuborganda avtomatik yangi lid yaratadi (Login talab qilinmaydi).",
        request=PublicLeadSubmitSerializer,
        responses={
            201: inline_serializer(
                name="PublicLeadSubmitSuccessResponse",
                fields={
                    "success": serializers.BooleanField(),
                    "message": serializers.CharField(),
                }
            ),
            400: inline_serializer(
                name="PublicLeadSubmitErrorResponse",
                fields={"detail": serializers.CharField(required=False)}
            ),
        },
        tags=["CRM Public"],
    )
    def post(self, request):
        serializer = PublicLeadSubmitSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "success": True,
                "message": "Ma'lumotlar qabul qilindi, tez orada aloqaga chiqamiz!"
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

