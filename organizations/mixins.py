from django.db import models as db_models
from rest_framework import exceptions
from organizations.models import Organization, Branch
from organizations.permissions import HasOrganizationPagePermission


class TenantViewSetMixin:
    """
    Mixin for viewsets to filter and inject organization + branch context.
    
    Organization: from user's profile (mandatory).
    Branch: from X-Branch-ID header, or fallback to user's branch.
    """

    def get_organization_id(self):
        """Get the organization ID from the authenticated user, or query params/headers ONLY if superuser."""
        # Agar foydalanuvchi tizimga kirgan bo'lsa va superuser bo'lmasa, faqat uning o'z tashkiloti ID sini qaytaramiz
        if self.request.user and self.request.user.is_authenticated:
            if not self.request.user.is_superuser:
                return getattr(self.request.user, 'organization_id', None)
        
        # Faqat superuserlar query params yoki headers orqali tashkilot context'ini override qila oladi
        org_id = self.request.query_params.get('org_id')
        if not org_id:
            org_id = self.request.META.get('HTTP_X_ORG_ID') or self.request.headers.get('x-org-id')
        if not org_id and self.request.user and self.request.user.is_authenticated:
            org_id = getattr(self.request.user, 'organization_id', None)
        return org_id

    def get_branch_id(self):
        """
        Get branch ID from query parameters or headers (set by frontend navbar),
        request.data (during POST/PUT/PATCH), or fallback to the user's assigned branch.
        """
        # 1. Check query parameters
        branch_id = self.request.query_params.get('branch') or self.request.query_params.get('branch_id')
        
        # 2. Check X-Branch-ID or x-branch-id headers
        if not branch_id:
            branch_id = self.request.headers.get('x-branch-id') or self.request.headers.get('X-Branch-ID')
        if not branch_id:
            branch_id = self.request.META.get('HTTP_X_BRANCH_ID')
        
        # 3. Check request.data (for POST/PUT/PATCH calls)
        if not branch_id and hasattr(self.request, 'data'):
            try:
                data = self.request.data
                if isinstance(data, dict):
                    branch_id = data.get('branch') or data.get('branch_id')
            except Exception:
                pass

        # 4. Fallback to user's branch
        if not branch_id and self.request.user and self.request.user.is_authenticated:
            branch_id = getattr(self.request.user, 'branch_id', None)
        
        # 5. Validate branch belongs to user's organization & check user permissions
        if branch_id:
            org_id = self.get_organization_id()
            if org_id:
                try:
                    b_id = branch_id.id if hasattr(branch_id, 'id') else int(branch_id)
                    branch = Branch.objects.get(id=b_id, organization_id=org_id)
                    
                    # Agar foydalanuvchi superuser, owner yoki admin bo'lmasa, faqat o'ziga biriktirilgan filialga cheklaymiz
                    u = self.request.user
                    if u and u.is_authenticated and not u.is_superuser and getattr(u, 'role', '') not in ('owner', 'admin'):
                        assigned_branch_ids = set()
                        if u.branch_id:
                            assigned_branch_ids.add(u.branch_id)
                        if hasattr(u, 'branches'):
                            assigned_branch_ids.update(u.branches.values_list('id', flat=True))
                        if assigned_branch_ids and branch.id not in assigned_branch_ids:
                            return u.branch_id or branch.id

                    return branch.id
                except (Branch.DoesNotExist, ValueError, TypeError):
                    return None
            return branch_id
        
        return None

    def get_queryset(self):
        queryset = super().get_queryset()
        model = queryset.model

        # === Organization filter (mandatory) ===
        if hasattr(model, 'organization'):
            org_id = self.get_organization_id()
            if org_id:
                queryset = queryset.filter(organization_id=org_id)
            else:
                return queryset.none()

        # === Branch filter ===
        if hasattr(model, 'branch'):
            from organizations.models import Branch
            if model is not Branch:
                branch_id = self.get_branch_id()
                if branch_id:
                    if model.__name__ == 'User':
                        # User (Employee/Teacher/Staff) can be assigned to multiple branches
                        # Owners should be visible in all branches
                        queryset = queryset.filter(
                            db_models.Q(branches=branch_id) |
                            db_models.Q(branch_id=branch_id) |
                            db_models.Q(role='owner')
                        ).distinct()
                    else:
                        # Tashkilot miqyosidagi umumiy sozlamalar (barcha filiallar uchun umumiy bo'lishi mumkin bo'lgan kataloglar)
                        global_catalog_models = [
                            'Subscription', 'Tariff', 'ReceiptSetting', 'BackupSetting',
                            'StudentFieldSetting', 'FAQCategory', 'FAQItem', 'SmsProvider',
                            'ExamSetting', 'TelegramNotificationSetting'
                        ]
                        if model.__name__ in global_catalog_models:
                            queryset = queryset.filter(
                                db_models.Q(branch_id=branch_id) | db_models.Q(branch__isnull=True)
                            )
                        else:
                            # BARCHA OPERATSION MODELLAR (Student, Group, Lead, Payment, Expense,
                            # Attendance, LessonSchedule, GroupLesson, Homework, Exam, Room,
                            # Building, SchoolClass, ClassStudent, Parent, Cashbox, Transaction,
                            # Board, Item, StudentGroup va boshqalar) qat'iy filialga ajratiladi!
                            queryset = queryset.filter(branch_id=branch_id)

        return queryset

    def perform_create(self, serializer):
        """Automatically inject organization and branch on create."""
        model_class = serializer.Meta.model
        extra_kwargs = {}

        # Inject organization
        if hasattr(model_class, 'organization'):
            org_id = self.get_organization_id()
            if not org_id:
                raise exceptions.ValidationError(
                    {"detail": "Organization context is required."}
                )
            try:
                org = Organization.objects.get(id=org_id)
            except Organization.DoesNotExist:
                raise exceptions.ValidationError(
                    {"detail": f"Organization with ID {org_id} does not exist."}
                )
            extra_kwargs['organization'] = org

        # Inject branch
        if hasattr(model_class, 'branch'):
            # Faqat serializerda branch berilmagan bo'lsa avtomatik kiritamiz
            branch_val = getattr(serializer, 'validated_data', {}).get('branch', None)
            if not branch_val:
                branch_id = self.get_branch_id()
                if branch_id:
                    try:
                        branch = Branch.objects.get(id=branch_id)
                        extra_kwargs['branch'] = branch
                    except Branch.DoesNotExist:
                        pass  # Don't fail — branch is optional

        if extra_kwargs:
            serializer.save(**extra_kwargs)
        else:
            serializer.save()

    def get_permissions(self):
        permissions = super().get_permissions()
        if getattr(self, 'permission_page_name', None):
            permissions.append(HasOrganizationPagePermission())
        return permissions
