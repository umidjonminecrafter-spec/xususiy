from rest_framework import status, generics, viewsets, permissions, exceptions, decorators
from rest_framework.response import Response
from organizations.models import Organization
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import IsAdminOrOwnerOrReadOnly
from accounts.serializers import (
    UserSerializer, RegisterSerializer, ChangePasswordSerializer, EmployeeSerializer
)

User = get_user_model()

class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Login endpoint: receives username & password, returns access/refresh tokens and user details.
    Enforces login via phone number only.
    """
    def post(self, request, *args, **kwargs):
        # Print incoming data to help debug
        print("Incoming login request data:", request.data)
        
        # Safely convert request.data to a mutable dict
        if hasattr(request.data, 'copy'):
            data = request.data.copy()
        elif hasattr(request.data, 'dict'):
            data = request.data.dict()
        else:
            data = dict(request.data) if request.data else {}

        credential = data.get('phone') or data.get('phone_number') or data.get('username')
        if not credential:
            return Response({"detail": "Telefon raqami kiritilishi shart."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Clean non-digits
        cleaned = ''.join(c for c in str(credential) if c.isdigit())
        
        if len(cleaned) == 9:
            cleaned = '998' + cleaned
            
        if not cleaned.startswith('998') or len(cleaned) != 12:
            return Response({"detail": "Faqat O'zbekiston telefon raqami orqali tizimga kirish mumkin (format: +998XXXXXXXXX)."}, status=status.HTTP_400_BAD_REQUEST)
            
        formatted_phone = '+' + cleaned
        
        # Tashkilot ID sini header, query params yoki body orqali olamiz
        org_id = request.headers.get('x-org-id') or request.META.get('HTTP_X_ORG_ID') or request.data.get('org_id') or request.query_params.get('org_id')
        
        if org_id:
            data['username'] = f"{formatted_phone}_{org_id}"
        else:
            # Agar tashkilot ID yuborilmagan bo'lsa, telefon bo'yicha qidirib ko'ramiz
            users = User.objects.filter(phone=formatted_phone)
            if users.count() == 1:
                data['username'] = users.first().username
            elif users.count() > 1:
                return Response({
                    "detail": "Ushbu telefon raqami bir nechta tashkilotda ro'yxatdan o'tgan. Iltimos, tashkilotni (org_id yoki x-org-id) ko'rsating."
                }, status=status.HTTP_400_BAD_REQUEST)
            else:
                data['username'] = formatted_phone

        print("Mapped login request data:", data)

        # Authenticate qilamiz
        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            # Fallback 1: eski foydalanuvchilar uchun faqat formatlangan telefon raqami bilan kirib ko'ramiz
            alt_data = data.copy() if hasattr(data, 'copy') else dict(data)
            alt_data['username'] = formatted_phone
            serializer2 = self.get_serializer(data=alt_data)
            try:
                serializer2.is_valid(raise_exception=True)
                serializer = serializer2
            except Exception:
                # Fallback 2: plyussiz raqam bilan urinib ko'ramiz
                alt_data2 = data.copy() if hasattr(data, 'copy') else dict(data)
                alt_data2['username'] = cleaned
                serializer3 = self.get_serializer(data=alt_data2)
                try:
                    serializer3.is_valid(raise_exception=True)
                    serializer = serializer3
                except Exception:
                    print("Login validation failed:", str(e))
                    return Response({"detail": "Telefon raqam yoki parol noto'g'ri."}, status=status.HTTP_400_BAD_REQUEST)
        
        user = serializer.user
        update_last_login(None, user)
        
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'role': user.role,
            'position': user.position or '',
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)

class CustomTokenRefreshView(TokenRefreshView):
    """
    Refresh endpoint: receives refresh token, returns new access/refresh tokens and user details.
    """
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            # Optionally attach user info if access token was decoded
            # (Just matching structure of login/refresh endpoints)
            pass
        return response

class RegisterView(generics.CreateAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)

class CurrentUserView(generics.RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

class ProfileUpdateView(generics.UpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

class ChangePasswordView(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.request.user.set_password(serializer.validated_data['new_password'])
        self.request.user.save()
        return Response({"detail": "Password has been changed successfully."}, status=status.HTTP_200_OK)

class LogoutView(APIView):
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
        except Exception:
            # Even if blacklisting is disabled or token invalid, return success to let frontend clear storage
            return Response({"detail": "Logout completed."}, status=status.HTTP_200_OK)

class EmployeeViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Xodimlar sozlamalari'
    serializer_class = EmployeeSerializer
    queryset = User.objects.all()

    def get_queryset(self):
        from django.db.models import Q
        qs = super().get_queryset().exclude(is_superuser=True).exclude(role='student')
        role = self.request.query_params.get('role')
        if role:
            if role.lower() in ['teacher', "o'qituvchi", "oqituvchi", "ustoz"]:
                qs = qs.filter(
                    Q(role__iexact='teacher') |
                    Q(position__icontains="o'qituvchi") |
                    Q(position__icontains="oqituvchi") |
                    Q(position__icontains="teacher") |
                    Q(position__icontains="ustoz")
                )
            else:
                qs = qs.filter(role=role)
        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance == request.user:
            raise exceptions.ValidationError({"detail": "CEO yoki xodim o'zini o'zi o'chira olmaydi!"})

        reason = request.query_params.get('reason') or request.data.get('reason') or "O'chirib tashlangan"
        comment = request.query_params.get('comment') or request.data.get('comment') or ""

        # Save to StudentArchive
        from academics.models import StudentArchive
        role_name = instance.position if instance.position else instance.role

        StudentArchive.objects.create(
            organization=instance.organization,
            branch=instance.branch,
            first_name=instance.first_name,
            last_name=instance.last_name,
            phone=instance.phone,
            email=instance.email,
            role=role_name or "employee",
            reason=reason,
            comment=comment,
            archived_by=request.user.get_full_name() or request.user.username if request.user.is_authenticated else "Tizim"
        )
        return super().destroy(request, *args, **kwargs)


    def perform_create(self, serializer):
        org_id = self.get_organization_id()
        if not org_id:
            raise exceptions.ValidationError({"detail": "Organization context is required."})
        try:
            org = Organization.objects.get(id=org_id)
        except Organization.DoesNotExist:
            raise exceptions.ValidationError({"detail": f"Organization with ID {org_id} does not exist."})
        
        # Use the mixin's branch resolution (X-Branch-ID header -> user's branch)
        branch = None
        branch_id = self.get_branch_id()
        if branch_id:
            from organizations.models import Branch
            try:
                branch = Branch.objects.get(id=branch_id)
            except Branch.DoesNotExist:
                pass
            
        serializer.save(organization=org, branch=branch)

    @decorators.action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        employee = self.get_object()
        logs = []
        
        # 1. Employee created
        logs.append({
            "action": "Ro'yxatdan o'tish",
            "description": f"Xodim tizimda ro'yxatdan o'tkazildi. Roli: {employee.get_role_display() if hasattr(employee, 'get_role_display') else employee.role}.",
            "created_at": employee.date_joined
        })
        
        # 2. Group assignments
        from academics.models import GroupTeacher
        for gt in GroupTeacher.objects.filter(teacher=employee).select_related('group'):
            logs.append({
                "action": "Guruh biriktirildi",
                "description": f"O'qituvchi '{gt.group.name}' guruhiga dars berish uchun biriktirildi.",
                "created_at": gt.created_at
            })
            
        # 3. Salary payments
        from academics.models import TeacherSalaryPayment
        for sp in TeacherSalaryPayment.objects.filter(teacher=employee):
            logs.append({
                "action": "Maosh to'landi",
                "description": f"{sp.period} oyi uchun {sp.amount} UZS to'landi.",
                "created_at": sp.paid_at
            })
            
        # 4. Salary calculations
        from finance.models import TeacherSalaryCalculation
        for sc in TeacherSalaryCalculation.objects.filter(teacher=employee):
            logs.append({
                "action": "Maosh hisoblandi",
                "description": f"{sc.period} oyi uchun maosh hisob-kitob qilindi: {sc.calculated_amount} UZS.",
                "created_at": sc.created_at
            })
            
        # 5. Salary rules
        from finance.models import TeacherSalaryRule
        for sr in TeacherSalaryRule.objects.filter(teacher=employee):
            logs.append({
                "action": "Maosh qoidasi",
                "description": f"O'qituvchiga maosh qoidasi biriktirildi ({sr.rule_type}): {sr.rate} UZS.",
                "created_at": sr.created_at
            })
            
        # Convert created_at to ISO string and sort
        for log in logs:
            if hasattr(log['created_at'], 'isoformat'):
                log['created_at'] = log['created_at'].isoformat()
            else:
                log['created_at'] = str(log['created_at'])
                
        logs.sort(key=lambda x: x['created_at'], reverse=True)
        return Response(logs, status=status.HTTP_200_OK)

class RoleListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Sozlamalar'

    def get(self, request):
        roles_data = [{"id": key, "name": value} for key, value in User.ROLE_CHOICES]
        return Response(roles_data, status=status.HTTP_200_OK)


class OrganizationMembersView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Xabarlar'

    def get(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response([], status=status.HTTP_200_OK)

        role = request.query_params.get('role')
        queryset = User.objects.filter(organization=org).exclude(is_superuser=True)
        if role:
            queryset = queryset.filter(role=role)
        serializer = UserSerializer(queryset.order_by('first_name', 'last_name', 'username'), many=True)
        data = serializer.data
        for item in data:
            item['full_name'] = f"{item.get('first_name', '')} {item.get('last_name', '')}".strip() or item.get('username', '')
        return Response(data, status=status.HTTP_200_OK)


class MessageEmployeesView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Xabarlar'

    def get(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response([], status=status.HTTP_200_OK)

        role = request.query_params.get('role')
        queryset = User.objects.filter(organization=org).exclude(is_superuser=True).exclude(role='student')
        if role:
            queryset = queryset.filter(role=role)

        serializer = UserSerializer(queryset.order_by('first_name', 'last_name', 'username'), many=True)
        data = serializer.data
        for item in data:
            item['full_name'] = f"{item.get('first_name', '')} {item.get('last_name', '')}".strip() or item.get('username', '')
        return Response(data, status=status.HTTP_200_OK)
