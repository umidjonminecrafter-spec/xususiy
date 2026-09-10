"""
URL configuration for config project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import CustomTokenObtainPairView, CustomTokenRefreshView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from django.http import JsonResponse
from academics.views import TelegramWebhookView, BuildingViewSet
from accounts.views import EmployeeViewSet

def health_check(request):
    return JsonResponse({"status": "healthy", "service": "SmartTalim Backend"})

urlpatterns = [
    path('', health_check, name='health-check'),
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),

    path(
        'api/swagger/',
        SpectacularSwaggerView.as_view(url_name='schema'),
        name='swagger-ui'
    ),

    path(
        'api/redoc/',
        SpectacularRedocView.as_view(url_name='schema'),
        name='redoc'
    ),
    
    # Global JWT Auth tokens (Custom views supporting phone mapping)
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    
    # Direct Telegram Webhook endpoint (supports /api/telegram/webhook/<bot_type>/<token>/)
    path('api/telegram/webhook/<str:bot_type>/<str:token>/', TelegramWebhookView.as_view(), name='telegram-webhook-direct'),
    
    # Versioned app endpoints
    path('api/v1/accounts/', include('accounts.urls')),
    path('api/v1/academics/', include('academics.urls')),
    path('api/v1/students/', include('academics.student_urls')),
    path('api/v1/finance/', include('finance.urls')),
    
    # CRM supports /api/v1/crm/ and /api/v1/crm/crm/
    path('api/v1/crm/', include('crm.urls')),
    path('api/v1/crm/crm/', include('crm.urls')),
    
    # Tasks supports /api/v1/tasks/ and /api/v1/tasks/tasks/
    path('api/v1/tasks/', include('tasks.urls')),
    path('api/v1/tasks/tasks/', include('tasks.urls')),
    
    path('api/v1/organizations/', include('organizations.urls')),
    path('api/v1/audit/', include('audit.urls')),
    path('api/v1/communication/', include('communication.urls')),
    path('api/v1/billing/', include('billing.urls')),
    path('api/v1/analytics/', include('analytics.urls')),
    path('api/v1/support/', include('support.urls')),
    path('api/v1/kpi/', include('kpi.urls')),
    path('api/v1/settings/buildings/', BuildingViewSet.as_view({'get': 'list', 'post': 'create'}), name='settings-buildings-list'),
    path('api/v1/settings/buildings/<int:pk>/', BuildingViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='settings-buildings-detail'),
    path('api/v1/users/teachers/', EmployeeViewSet.as_view({'get': 'list', 'post': 'create'}), name='users-teachers-list'),
    path('api/v1/users/teachers/<int:pk>/', EmployeeViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='users-teachers-detail'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

