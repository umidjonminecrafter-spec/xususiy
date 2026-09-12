from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CourseViewSet, RoomViewSet, StudentViewSet, GroupViewSet,
    StudentGroupViewSet, GroupTeacherViewSet, TeacherSalaryPaymentViewSet,
    StudentTransactionsView, GroupAttendanceView, LessonScheduleViewSet,
    StudentBalancesViewSet, BalanceHistoryViewSet, ExamViewSet, ExamResultViewSet,
    LeaveReasonViewSet, LessonTimeViewSet, OnlineLessonViewSet, StudentGroupLeaveViewSet,
    StudentPricingViewSet, StudentArchiveViewSet, AttendanceViewSet, HolidayViewSet, HomeworkViewSet, SendCodeAPIView,
    VerifyCodeAPIView, StudentProfileAPIView, StudentLessonsAPIView, ParentStudentsAPIView, ParentStudentDetailsAPIView,
    StaffProfileAPIView, StaffScheduleAPIView, BotMessageTemplateViewSet, TelegramWebhookView, SetLessonTopicAPIView,
    CancelOrRestoreLessonAPIView, RescheduleLessonAPIView, GroupLessonListAPIView, BirthdayCalendarAPIView,
    StudentEvaluationLevelViewSet, CourseMaterialViewSet, CheckBotRegistrationAPIView,
    TeacherViewSet, LessonCalendarAPIView, LessonStatisticsAPIView,
    CoursesReportAPIView, LeaveReasonsReportAPIView, TeachersReportAPIView
)
from .views import StudentFieldSettingViewSet
from finance.views import TeacherSalaryCalculationViewSet, TeacherSalaryRuleViewSet


student_field_settings = StudentFieldSettingViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

student_field_setting_detail = StudentFieldSettingViewSet.as_view({
    'get': 'retrieve',
    'patch': 'partial_update',
    'put': 'update',
    'delete': 'destroy'
})
router = DefaultRouter()
router.register(r'students', StudentViewSet, basename='student')
router.register(r'classes', GroupViewSet, basename='class')
router.register(r'courses', CourseViewSet, basename='course')
router.register(r'rooms', RoomViewSet, basename='room')
router.register(r'student-classes', StudentGroupViewSet, basename='student-class')
router.register(r'class-teachers', GroupTeacherViewSet, basename='class-teacher')
router.register(r'lesson-schedules', LessonScheduleViewSet, basename='lesson-schedule')
router.register(r'student-balances', StudentBalancesViewSet, basename='student-balance')
router.register(r'attendances', AttendanceViewSet, basename='attendance')

# New ViewSets
router.register(r'holidays', HolidayViewSet, basename='holiday')
router.register(r'balance-history', BalanceHistoryViewSet, basename='balance-history')
router.register(r'exams', ExamViewSet, basename='exam')
router.register(r'exam-results', ExamResultViewSet, basename='exam-result')
router.register(r'leave-reasons', LeaveReasonViewSet, basename='leave-reason')
router.register(r'lesson-times', LessonTimeViewSet, basename='lesson-time')
router.register(r'online-lessons', OnlineLessonViewSet, basename='online-lesson')
router.register(r'student-group-leaves', StudentGroupLeaveViewSet, basename='student-group-leave')
router.register(r'student-pricings', StudentPricingViewSet, basename='student-pricing')
router.register(r'archive', StudentArchiveViewSet, basename='student-archive')
router.register(r'homeworks', HomeworkViewSet, basename='homework')
router.register(r'bot-message-templates', BotMessageTemplateViewSet, basename='bot-message-template')

# Teachers nested routes (to match /api/v1/academics/teachers/...)
router.register(r'teachers/salary-calculations', TeacherSalaryCalculationViewSet, basename='academic-teacher-salary-calc')
router.register(r'teachers/salary-payments', TeacherSalaryPaymentViewSet, basename='academic-teacher-salary-payment')
router.register(r'teachers/salary-rules', TeacherSalaryRuleViewSet, basename='academic-teacher-salary-rule')
router.register(r'teachers', TeacherViewSet, basename='academic-teacher')
router.register(r'evaluation-levels', StudentEvaluationLevelViewSet, basename='evaluation-levels')
router.register(r'course-materials', CourseMaterialViewSet, basename='course-material')

urlpatterns = [
    path('student-transactions/', StudentTransactionsView.as_view(), name='student-transactions'),
    path('attendances/class/<int:group_id>/', GroupAttendanceView.as_view(), name='class-attendance'),
    path('classes/calendar/', LessonCalendarAPIView.as_view(), name='classes-calendar'),
    path('lessons/<int:lesson_id>/statistics/', LessonStatisticsAPIView.as_view(), name='lesson-statistics'),
    path('reports/courses/', CoursesReportAPIView.as_view(), name='reports-courses'),
    path('reports/leave-reasons/', LeaveReasonsReportAPIView.as_view(), name='reports-leave-reasons'),
    path('reports/teachers/', TeachersReportAPIView.as_view(), name='reports-teachers'),
    path(
        'student-field-settings/',
        student_field_settings,
        name='student-field-settings'
    ),


    path(
        'student-field-settings/<int:pk>/',
        student_field_setting_detail,
        name='student-field-setting-detail'
    ),
    path('', include(router.urls)),
    path('auth/send-code/', SendCodeAPIView.as_view(), name='send-verification-code'),
    path('auth/verify-code/', VerifyCodeAPIView.as_view(), name='verify-verification-code'),
    path('student/profile/', StudentProfileAPIView.as_view(), name='bot-student-profile'),
    path('student/lessons/', StudentLessonsAPIView.as_view(), name='bot-student-lessons'),
    path('parent/students/', ParentStudentsAPIView.as_view(), name='bot-parent-students'),
    path('parent/student-details/', ParentStudentDetailsAPIView.as_view(), name='bot-parent-student-details'),
    path('staff/profile/', StaffProfileAPIView.as_view(), name='bot-staff-profile'),
    path('staff/schedule/', StaffScheduleAPIView.as_view(), name='bot-staff-schedule'),
    path('telegram/webhook/<str:bot_type>/<str:token>/', TelegramWebhookView.as_view(), name='telegram-webhook'),
    path('lessons/<int:lesson_id>/set-topic/', SetLessonTopicAPIView.as_view(), name='set-lesson-topic'),
    path('lessons/<int:lesson_id>/cancel-or-restore/', CancelOrRestoreLessonAPIView.as_view(), name='cancel-restore-lesson'),
    path('lessons/<int:lesson_id>/reschedule/', RescheduleLessonAPIView.as_view(), name='reschedule-lesson'),
    path('lessons/', GroupLessonListAPIView.as_view(), name='group-lessons-list'),
    path('birthdays/', BirthdayCalendarAPIView.as_view(), name='birthday-calendar'),
    path('check-bot-registration/', CheckBotRegistrationAPIView.as_view(), name='check-bot-registration'),
]

