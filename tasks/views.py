from rest_framework import viewsets, permissions
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from rest_framework.decorators import action
from rest_framework.response import Response

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
            except Exception as e:
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

class TaskPermissionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Tasks'
    queryset = TaskPermission.objects.all()
    serializer_class = TaskPermissionSerializer
    permission_classes = [permissions.IsAuthenticated]

class LabelViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Tasks'
    queryset = Label.objects.all()
    serializer_class = LabelSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['board_id']
    permission_classes = [permissions.IsAuthenticated, HasBoardPermission]

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

class TaskHistoryViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    permission_page_name = 'Tasks'
    queryset = TaskHistory.objects.all()
    serializer_class = TaskHistorySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['item_id']
    permission_classes = [permissions.IsAuthenticated, HasBoardPermission]
