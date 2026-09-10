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
        falling back to the user's assigned branch.
        """
        # 1. Check query parameters
        branch_id = self.request.query_params.get('branch') or self.request.query_params.get('branch_id')
        
        # 2. Check X-Branch-ID or x-branch-id headers
        if not branch_id:
            branch_id = self.request.headers.get('x-branch-id') or self.request.headers.get('X-Branch-ID')
        if not branch_id:
            branch_id = self.request.META.get('HTTP_X_BRANCH_ID')
        
        # 3. Fallback to user's branch
        if not branch_id and self.request.user and self.request.user.is_authenticated:
            branch_id = getattr(self.request.user, 'branch_id', None)
        
        # 4. Validate branch belongs to user's organization
        if branch_id:
            org_id = self.get_organization_id()
            if org_id:
                try:
                    branch = Branch.objects.get(id=branch_id, organization_id=org_id)
                    return branch.id
                except (Branch.DoesNotExist, ValueError):
                    # Branch doesn't belong to this org or is invalid
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
                            db_models.Q(role='owner') |
                            db_models.Q(branch__isnull=True, branches__isnull=True)
                        ).distinct()
                    else:
                        # Model lists that must be strictly isolated to the branch
                        strict_models = [
                            'Group', 'Room', 'LessonSchedule', 'Payment', 'Expense', 
                            'Sale', 'Bonus', 'Fine', 'Salary', 'TeacherSalaryPayment',
                            'StudentGroup', 'FinanceAction', 'Cashbox', 'Transaction'
                        ]
                        if model.__name__ in strict_models:
                            queryset = queryset.filter(branch_id=branch_id)
                        else:
                            queryset = queryset.filter(
                                db_models.Q(branch_id=branch_id) | db_models.Q(branch__isnull=True)
                            )

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
