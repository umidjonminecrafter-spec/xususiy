from django.urls import path
from .views import GlobalAttendanceAPIView, AttendanceAnalyticsAPIView, UnmarkedGroupsAPIView, BranchStatusAPIView

urlpatterns = [
    path('global-attendance/', GlobalAttendanceAPIView.as_view(), name='global-attendance'),
    path('attendance-stats/', AttendanceAnalyticsAPIView.as_view(), name='attendance-stats'),
    path('unmarked-groups/', UnmarkedGroupsAPIView.as_view(), name='unmarked-groups'),
    path('branch-status/', BranchStatusAPIView.as_view(), name='branch-status'),
]