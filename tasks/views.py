from rest_framework import viewsets, permissions, serializers
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from drf_spectacular.types import OpenApiTypes

from organizations.mixins import TenantViewSetMixin
from tasks.models import Board, Column, Item, Comment, TaskPermission, Label, Checklist, ChecklistItem, Attachment, TaskHistory
from tasks.serializers import (
    BoardSerializer, ColumnSerializer, ItemSerializer, CommentSerializer, TaskPermissionSerializer,
    LabelSerializer, ChecklistSerializer, ChecklistItemSerializer, AttachmentSerializer, TaskHistorySerializer
)
from tasks.permissions import HasBoardPermission, IsCommentOwnerOrReadOnly

def log_task_activity(item, user, action, details="", organization=None, branch=None):
    from tasks.models import TaskHistory
    org = organization or getattr(item, 'organization', None)
    br = branch or getattr(item, 'branch', None)
    
    TaskHistory.objects.create(
        item=item,
        user=user if (user and user.is_authenticated) else None,
        action=action,
        details=details,
        organization=org,
        branch=br
    )


@extend_schema_view(
    list=extend_schema(summary="Loyiha taxtalari (Boards) ro'yxati", tags=['Tasks & Boards']),
    create=extend_schema(summary="Yangi doska yaratish", tags=['Tasks & Boards']),
    retrieve=extend_schema(summary="Doska tafsilotlari (Ustunlar va vazifalari bilan)", tags=['Tasks & Boards']),
    update=extend_schema(summary="Doskani to'liq yangilash", tags=['Tasks & Boards']),
    partial_update=extend_schema(summary="Doskani qisman yangilash", tags=['Tasks & Boards']),
    destroy=extend_schema(summary="Doskani o'chirish", tags=['Tasks & Boards']),
)
class BoardViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Tasks'
    queryset = Board.objects.all()
    serializer_class = BoardSerializer
    permission_classes = [permissions.IsAuthenticated, HasBoardPermission]

    def get_queryset(self):
        return super().get_queryset().prefetch_related(
            'columns__items__assigned_to',
            'columns__items__members',
            'columns__items__labels'
        )


@extend_schema_view(
    list=extend_schema(summary="Ustunlar (Columns) ro'yxati", tags=['Tasks & Columns']),
    create=extend_schema(summary="Doskaga yangi ustun qo'shish", tags=['Tasks & Columns']),
    retrieve=extend_schema(summary="Ustun tafsilotlari", tags=['Tasks & Columns']),
    update=extend_schema(summary="Ustunni to'liq yangilash", tags=['Tasks & Columns']),
    partial_update=extend_schema(summary="Ustunni qisman yangilash (Nomi, Tartibi)", tags=['Tasks & Columns']),
    destroy=extend_schema(summary="Ustunni o'chirish", tags=['Tasks & Columns']),
)
class ColumnViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Tasks'
    queryset = Column.objects.all()
    serializer_class = ColumnSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['board_id']
    permission_classes = [permissions.IsAuthenticated, HasBoardPermission]

    def get_queryset(self):
        return super().get_queryset().prefetch_related(
            'items__assigned_to',
            'items__members',
            'items__labels'
        )


@extend_schema_view(
    list=extend_schema(summary="Vazifalar (Tasks / Items) ro'yxati", tags=['Tasks & Items']),
    create=extend_schema(summary="Yangi vazifa yaratish", tags=['Tasks & Items']),
    retrieve=extend_schema(summary="Vazifa tafsilotlari", tags=['Tasks & Items']),
    update=extend_schema(summary="Vazifani to'liq yangilash", tags=['Tasks & Items']),
    partial_update=extend_schema(summary="Vazifani qisman yangilash", tags=['Tasks & Items']),
    destroy=extend_schema(summary="Vazifani o'chirish", tags=['Tasks & Items']),
    move=extend_schema(
        summary="Vazifani boshqa ustunga yoki tartibga ko'chirish (Drag & Drop)",
        tags=['Tasks & Items'],
        request=inline_serializer(
            name='TaskMoveRequest',
            fields={
                'column_id': serializers.IntegerField(required=False, help_text="Yangi ustun ID raqami"),
                'order': serializers.IntegerField(required=False, help_text="Ustun ichidagi tartib indeksi")
            }
        ),
        responses={200: OpenApiTypes.OBJECT}
    ),
    history=extend_schema(
        summary="Vazifa o'zgarishlari va harakatlari tarixi",
        tags=['Tasks & Items'],
        responses={200: TaskHistorySerializer(many=True)}
    )
)
class ItemViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Tasks'
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['column_id', 'board_id', 'assigned_to']
    search_fields = ['title', 'description']
    permission_classes = [permissions.IsAuthenticated, HasBoardPermission]

    def get_queryset(self):
        return super().get_queryset().select_related(
            'assigned_to', 'column', 'board'
        ).prefetch_related(
            'members', 'labels'
        )

    def perform_create(self, serializer):
        super().perform_create(serializer)
        item = serializer.instance
        log_task_activity(
            item=item,
            user=self.request.user,
            action="created",
            details=f"Yangi vazifa yaratildi: '{item.title}'"
        )

    def perform_update(self, serializer):
        old_item = Item.objects.get(pk=serializer.instance.pk)
        
        # Get original lists of IDs for m2m comparison
        old_members_ids = list(old_item.members.values_list('id', flat=True))
        old_labels_ids = list(old_item.labels.values_list('id', flat=True))
        
        super().perform_update(serializer)
        item = serializer.instance
        
        changes = []
        if old_item.title != item.title:
            changes.append(f"nomi o'zgartirildi ('{old_item.title}' -> '{item.title}')")
        if old_item.description != item.description:
            changes.append("tavsifi o'zgartirildi")
        if old_item.column != item.column:
            changes.append(f"ustuni o'zgartirildi ('{old_item.column.name}' -> '{item.column.name}')")
        if old_item.assigned_to != item.assigned_to:
            old_assignee = old_item.assigned_to.get_full_name() if old_item.assigned_to else "Hech kim"
            new_assignee = item.assigned_to.get_full_name() if item.assigned_to else "Hech kim"
            changes.append(f"mas'ul shaxs o'zgartirildi ('{old_assignee}' -> '{new_assignee}')")
        if old_item.due_date != item.due_date:
            old_due = old_item.due_date.strftime('%Y-%m-%d %H:%M') if old_item.due_date else "Belgilanmagan"
            new_due = item.due_date.strftime('%Y-%m-%d %H:%M') if item.due_date else "Belgilanmagan"
            changes.append(f"bajarilish muddati o'zgartirildi ('{old_due}' -> '{new_due}')")
        if old_item.start_date != item.start_date:
            old_start = old_item.start_date.strftime('%Y-%m-%d %H:%M') if old_item.start_date else "Belgilanmagan"
            new_start = item.start_date.strftime('%Y-%m-%d %H:%M') if item.start_date else "Belgilanmagan"
            changes.append(f"boshlanish vaqti o'zgartirildi ('{old_start}' -> '{new_start}')")
        if old_item.is_completed != item.is_completed:
            status = "bajarildi" if item.is_completed else "bajarilmagan"
            changes.append(f"holati '{status}' deb belgilandi")

        # Compare m2m members
        new_members = list(item.members.all())
        for m in new_members:
            if m.id not in old_members_ids:
                changes.append(f"yangi a'zo qo'shildi: {m.get_full_name()}")
        for m_id in old_members_ids:
            if m_id not in [m.id for m in new_members]:
                from accounts.models import User
                try:
                    m_user = User.objects.get(id=m_id)
                    changes.append(f"a'zo olib tashlandi: {m_user.get_full_name()}")
                except User.DoesNotExist:
                    changes.append("a'zo olib tashlandi")

        # Compare m2m labels
        new_labels = list(item.labels.all())
        for l in new_labels:
            if l.id not in old_labels_ids:
                changes.append(f"yangi teg qo'shildi: '{l.name}'")
        for l_id in old_labels_ids:
            if l_id not in [lbl.id for lbl in new_labels]:
                from tasks.models import Label
                try:
                    lbl = Label.objects.get(id=l_id)
                    changes.append(f"teg olib tashlandi: '{lbl.name}'")
                except Label.DoesNotExist:
                    changes.append("teg olib tashlandi")

        if changes:
            details = ", ".join(changes)
            log_task_activity(
                item=item,
                user=self.request.user,
                action="updated",
                details=f"Vazifa o'zgartirildi: {details}"
            )

    @action(detail=True, methods=['post'])
    def move(self, request, pk=None):
        item = self.get_object()
        old_column = item.column
        new_column_id = request.data.get('column_id')
        new_order = request.data.get('order')

        if new_column_id is not None:
            try:
                new_column = Column.objects.get(id=new_column_id, board_id=item.board_id)
                item.column = new_column
            except Column.DoesNotExist:
                return Response({'error': 'Ustun topilmadi yoki boshqa doskaga tegishli.'}, status=400)

        if new_order is not None:
            item.order = int(new_order)
            
        item.save()
         
        # Log the column move activity
        details = "Vazifa ko'chirildi"
        if new_column_id is not None and old_column != item.column:
            details += f" ('{old_column.name}' -> '{item.column.name}')"
        log_task_activity(
            item=item,
            user=self.request.user,
            action="moved",
            details=details
        )
        return Response({'status': 'muvaffaqiyatli ko\'chirildi'})

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        # 1. get_object_or_404 o'rniga self.get_object() ishlating.
        # Bu miksindagi barcha tashkilot filtrlarini avtomatik to'g'ri hisoblaydi.
        item = self.get_object()

        # 2. Shu vazifaga tegishli tarixni olamiz
        history = TaskHistory.objects.filter(item=item).order_by('-created_at')

        # 3. Agar pagination (sahifalash) bo'lsa, uni qo'llaymiz
        page = self.paginate_queryset(history)
        if page is not None:
            serializer = TaskHistorySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = TaskHistorySerializer(history, many=True)
        return Response(serializer.data)

@extend_schema_view(
    list=extend_schema(summary="Vazifa sharhlari (Comments) ro'yxati", tags=['Tasks & Comments']),
    create=extend_schema(summary="Vazifaga yangi sharh qo'shish", tags=['Tasks & Comments']),
    retrieve=extend_schema(summary="Sharh tafsiloti", tags=['Tasks & Comments']),
    update=extend_schema(summary="Sharhni to'liq yangilash", tags=['Tasks & Comments']),
    partial_update=extend_schema(summary="Sharhni qisman yangilash", tags=['Tasks & Comments']),
    destroy=extend_schema(summary="Sharhni o'chirish", tags=['Tasks & Comments']),
)
class CommentViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Tasks'
    queryset = Comment.objects.all()
    serializer_class = CommentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['item_id']
    permission_classes = [permissions.IsAuthenticated, IsCommentOwnerOrReadOnly]

    def perform_create(self, serializer):
        org_id = self.get_organization_id()
        branch_id = self.get_branch_id()
        comment = serializer.save(organization_id=org_id, branch_id=branch_id, user=self.request.user)
        log_task_activity(
            item=comment.item,
            user=self.request.user,
            action="comment_added",
            details=f"Yangi sharh qo'shildi: '{comment.text[:50]}...'" if len(comment.text) > 50 else f"Yangi sharh qo'shildi: '{comment.text}'"
        )
        if comment.item.assigned_to and comment.item.assigned_to != self.request.user:
            try:
                from communication.models import Notification
                lang = getattr(comment.item.assigned_to, 'telegram_language', 'uz') or 'uz'
                author_name = self.request.user.get_full_name() or self.request.user.username
                if lang == 'ru':
                    title = f"💬 Новый комментарий: {comment.item.title}"
                    msg = f"Оставлен новый комментарий к задаче '{comment.item.title}':\n{author_name}: {comment.text}"
                else:
                    title = f"💬 Yangi sharh: {comment.item.title}"
                    msg = f"'{comment.item.title}' vazifasiga yangi sharh qoldirildi:\n{author_name}: {comment.text}"

                Notification.objects.create(
                    organization=comment.organization,
                    user=comment.item.assigned_to,
                    title=title,
                    message=msg,
                    type='info'
                )
            except Exception:
                pass

    def perform_destroy(self, instance):
        item = instance.item
        comment_text = instance.text
        instance.delete()
        log_task_activity(
            item=item,
            user=self.request.user,
            action="comment_deleted",
            details=f"Sharh o'chirildi: '{comment_text[:50]}...'" if len(comment_text) > 50 else f"Sharh o'chirildi: '{comment_text}'"
        )


@extend_schema_view(
    list=extend_schema(summary="Doska ruxsatlari (Permissions) ro'yxati", tags=['Tasks & Permissions']),
    create=extend_schema(summary="Foydalanuvchiga doska bo'yicha tahrirlash ruxsatini berish", tags=['Tasks & Permissions']),
    retrieve=extend_schema(summary="Ruxsat tafsilotlari", tags=['Tasks & Permissions']),
    update=extend_schema(summary="Ruxsatni to'liq yangilash", tags=['Tasks & Permissions']),
    partial_update=extend_schema(summary="Ruxsatni qisman yangilash", tags=['Tasks & Permissions']),
    destroy=extend_schema(summary="Ruxsatni bekor qilish / o'chirish", tags=['Tasks & Permissions']),
)
class TaskPermissionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Tasks'
    queryset = TaskPermission.objects.all()
    serializer_class = TaskPermissionSerializer
    permission_classes = [permissions.IsAuthenticated]


@extend_schema_view(
    list=extend_schema(summary="Teglar / Yorliqlar (Labels) ro'yxati", tags=['Tasks & Labels']),
    create=extend_schema(summary="Yangi teg yaratish", tags=['Tasks & Labels']),
    retrieve=extend_schema(summary="Teg tafsilotlari", tags=['Tasks & Labels']),
    update=extend_schema(summary="Tegni to'liq yangilash", tags=['Tasks & Labels']),
    partial_update=extend_schema(summary="Tegni qisman yangilash", tags=['Tasks & Labels']),
    destroy=extend_schema(summary="Tegni o'chirish", tags=['Tasks & Labels']),
)
class LabelViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Tasks'
    queryset = Label.objects.all()
    serializer_class = LabelSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['board_id']
    permission_classes = [permissions.IsAuthenticated, HasBoardPermission]


@extend_schema_view(
    list=extend_schema(summary="Nazorat ro'yxatlari (Checklists) ro'yxati", tags=['Tasks & Checklists']),
    create=extend_schema(summary="Vazifaga yangi nazorat ro'yxati qo'shish", tags=['Tasks & Checklists']),
    retrieve=extend_schema(summary="Nazorat ro'yxati tafsilotlari", tags=['Tasks & Checklists']),
    update=extend_schema(summary="Nazorat ro'yxatini to'liq yangilash", tags=['Tasks & Checklists']),
    partial_update=extend_schema(summary="Nazorat ro'yxatini qisman yangilash", tags=['Tasks & Checklists']),
    destroy=extend_schema(summary="Nazorat ro'yxatini o'chirish", tags=['Tasks & Checklists']),
)
class ChecklistViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Tasks'
    queryset = Checklist.objects.all()
    serializer_class = ChecklistSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['item_id']
    permission_classes = [permissions.IsAuthenticated, HasBoardPermission]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        checklist = serializer.instance
        log_task_activity(
            item=checklist.item,
            user=self.request.user,
            action="checklist_created",
            details=f"Nazorat ro'yxati (Checklist) qo'shildi: '{checklist.title}'"
        )

    def perform_destroy(self, instance):
        item = instance.item
        checklist_title = instance.title
        instance.delete()
        log_task_activity(
            item=item,
            user=self.request.user,
            action="checklist_deleted",
            details=f"Nazorat ro'yxati (Checklist) o'chirildi: '{checklist_title}'"
        )


@extend_schema_view(
    list=extend_schema(summary="Nazorat ro'yxati elementlari (Checklist Items) ro'yxati", tags=['Tasks & Checklists']),
    create=extend_schema(summary="Nazorat ro'yxatiga yangi band qo'shish", tags=['Tasks & Checklists']),
    retrieve=extend_schema(summary="Nazorat bandi tafsilotlari", tags=['Tasks & Checklists']),
    update=extend_schema(summary="Nazorat bandini to'liq yangilash", tags=['Tasks & Checklists']),
    partial_update=extend_schema(summary="Nazorat bandini qisman yangilash (Bajarilganlik belgisi, Sarlavha)", tags=['Tasks & Checklists']),
    destroy=extend_schema(summary="Nazorat bandini o'chirish", tags=['Tasks & Checklists']),
)
class ChecklistItemViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Tasks'
    queryset = ChecklistItem.objects.all()
    serializer_class = ChecklistItemSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['checklist_id']
    permission_classes = [permissions.IsAuthenticated, HasBoardPermission]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        chk_item = serializer.instance
        log_task_activity(
            item=chk_item.checklist.item,
            user=self.request.user,
            action="checklist_item_created",
            details=f"Nazorat ro'yxatiga element qo'shildi: '{chk_item.title}'"
        )

    def perform_update(self, serializer):
        old_chk_item = ChecklistItem.objects.get(pk=serializer.instance.pk)
        super().perform_update(serializer)
        chk_item = serializer.instance
        
        if old_chk_item.is_completed != chk_item.is_completed:
            status = "bajarildi" if chk_item.is_completed else "bajarilmagan"
            log_task_activity(
                item=chk_item.checklist.item,
                user=self.request.user,
                action="checklist_item_toggled",
                details=f"Nazorat ro'yxati elementi '{chk_item.title}' {status} deb belgilandi"
            )
        elif old_chk_item.title != chk_item.title:
            log_task_activity(
                item=chk_item.checklist.item,
                user=self.request.user,
                action="checklist_item_updated",
                details=f"Nazorat ro'yxati elementi nomi o'zgartirildi: '{old_chk_item.title}' -> '{chk_item.title}'"
            )

    def perform_destroy(self, instance):
        item = instance.checklist.item
        chk_item_title = instance.title
        instance.delete()
        log_task_activity(
            item=item,
            user=self.request.user,
            action="checklist_item_deleted",
            details=f"Nazorat ro'yxati elementi o'chirildi: '{chk_item_title}'"
        )


@extend_schema_view(
    list=extend_schema(summary="Vazifa biriktirilgan fayllari (Attachments) ro'yxati", tags=['Tasks & Attachments']),
    create=extend_schema(summary="Vazifaga fayl yuklash / biriktirish", tags=['Tasks & Attachments']),
    retrieve=extend_schema(summary="Biriktirilgan fayl tafsilotlari", tags=['Tasks & Attachments']),
    update=extend_schema(summary="Faylni to'liq yangilash", tags=['Tasks & Attachments']),
    partial_update=extend_schema(summary="Faylni qisman yangilash", tags=['Tasks & Attachments']),
    destroy=extend_schema(summary="Biriktirilgan faylni o'chirish", tags=['Tasks & Attachments']),
)
class AttachmentViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Tasks'
    queryset = Attachment.objects.all()
    serializer_class = AttachmentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['item_id']
    permission_classes = [permissions.IsAuthenticated, HasBoardPermission]

    def perform_create(self, serializer):
        org_id = self.get_organization_id()
        branch_id = self.get_branch_id()
        attachment = serializer.save(organization_id=org_id, branch_id=branch_id, uploaded_by=self.request.user)
        file_name = attachment.file.name.split('/')[-1] if attachment.file else "Fayl"
        log_task_activity(
            item=attachment.item,
            user=self.request.user,
            action="attachment_added",
            details=f"Fayl biriktirildi: '{file_name}'"
        )

    def perform_destroy(self, instance):
        item = instance.item
        file_name = instance.file.name.split('/')[-1] if instance.file else "Fayl"
        instance.delete()
        log_task_activity(
            item=item,
            user=self.request.user,
            action="attachment_removed",
            details=f"Biriktirilgan fayl o'chirildi: '{file_name}'"
        )


@extend_schema_view(
    list=extend_schema(summary="Vazifalar o'zgarish tarixi ro'yxati", tags=['Tasks & History']),
    retrieve=extend_schema(summary="Tarix yozuvi tafsiloti", tags=['Tasks & History']),
)
class TaskHistoryViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    permission_page_name = 'Tasks'
    queryset = TaskHistory.objects.all()
    serializer_class = TaskHistorySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['item_id']
    permission_classes = [permissions.IsAuthenticated, HasBoardPermission]

