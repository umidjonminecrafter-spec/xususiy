from django.urls import path, include
from rest_framework.routers import DefaultRouter
from accounts.views import (
    CustomTokenObtainPairView, CustomTokenRefreshView, RegisterView,
    CurrentUserView, ProfileUpdateView, ChangePasswordView, LogoutView,
    EmployeeViewSet, RoleListView, OrganizationMembersView, MessageEmployeesView,
    PasswordResetRequestView, PasswordResetCheckStatusView, PasswordResetConfirmView
)

router = DefaultRouter()
router.register(r'employees', EmployeeViewSet, basename='employee')

urlpatterns = [
    path('login/', CustomTokenObtainPairView.as_view(), name='account-login'),
    path('login/refresh/', CustomTokenRefreshView.as_view(), name='account-login-refresh'),
    path('register/', RegisterView.as_view(), name='account-register'),
    path('current-user/', CurrentUserView.as_view(), name='account-current-user'),
    path('profile/', ProfileUpdateView.as_view(), name='account-profile'),
    path('change-password/', ChangePasswordView.as_view(), name='account-change-password'),
    
    # 🔐 Telegram Bot Password Reset Endpoints
    path('forgot-password/request/', PasswordResetRequestView.as_view(), name='forgot-password-request'),
    path('forgot-password/check-status/', PasswordResetCheckStatusView.as_view(), name='forgot-password-check-status'),
    path('forgot-password/confirm/', PasswordResetConfirmView.as_view(), name='forgot-password-confirm'),
    path('reset-password/', PasswordResetConfirmView.as_view(), name='reset-password'),
    
    path('logout/', LogoutView.as_view(), name='account-logout'),
    path('roles/', RoleListView.as_view(), name='account-roles'),
    path('members/', OrganizationMembersView.as_view(), name='account-members'),
    path('message-employees/', MessageEmployeesView.as_view(), name='account-message-employees'),
    path('', include(router.urls)),
]
