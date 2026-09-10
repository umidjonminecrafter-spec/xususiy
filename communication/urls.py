from django.urls import path, include
from rest_framework.routers import DefaultRouter
from communication.views import (
    SmsProviderViewSet, SMSMessagesViewSet, SmsSchedulesViewSet, SmsTemplatesViewSet,
    NotificationView, NotificationScheduleViewSet, StudentSMSHistoryAPIView
)

router = DefaultRouter()
router.register(r'providers', SmsProviderViewSet, basename='sms-provider')
router.register(r'sms-messages', SMSMessagesViewSet, basename='sms-message')
router.register(r'messages', SMSMessagesViewSet, basename='comm-message')
router.register(r'sms-schedules', SmsSchedulesViewSet, basename='sms-schedule')
router.register(r'schedules', SmsSchedulesViewSet, basename='comm-schedule')
router.register(r'sms-templates', SmsTemplatesViewSet, basename='sms-template')
router.register(r'templates', SmsTemplatesViewSet, basename='comm-template')
router.register(r'notification-schedules', NotificationScheduleViewSet, basename='notification-schedule')

urlpatterns = [
    path('', include(router.urls)),
    path('notifications/', NotificationView.as_view(), name='notifications'),
    path('student-sms-history/<int:student_id>/', StudentSMSHistoryAPIView.as_view(), name='student-sms-history'),
]
