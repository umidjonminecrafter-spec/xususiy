from django.urls import path, include
from rest_framework.routers import DefaultRouter
from crm.views import (
    PipelineViewSet, SourceViewSet, LostReasonViewSet, SectionViewSet, LeadFormViewSet, LeadViewSet,
    CRMActivityViewSet, CRMLeadLostViewSet, CRMLeadsHistoryViewSet
)

from crm.views import SMSTemplateListCreateAPIView, SMSTemplateRetrieveUpdateDestroyAPIView, \
    SendBulkSMSAPIView

from crm.views import LeadHistoryAPIView

from crm.views import LeadFormListCreateAPIView, PublicLeadFormDetailAPIView, \
    LeadFormRetrieveUpdateDestroyAPIView, PublicLeadSubmitAPIView

router = DefaultRouter()
router.register(r'pipelines', PipelineViewSet, basename='pipeline')
router.register(r'leads', LeadViewSet, basename='lead')
router.register(r'sources', SourceViewSet, basename='source')
router.register(r'crm-lost-reasons', LostReasonViewSet, basename='lost-reason')
router.register(r'sections', SectionViewSet, basename='section')
router.register(r'lead-forms', LeadFormViewSet, basename='lead-form')
router.register(r'activities', CRMActivityViewSet, basename='activity')
router.register(r'lost-leads', CRMLeadLostViewSet, basename='lost-lead')
router.register(r'crm-leads-history', CRMLeadsHistoryViewSet, basename='crm-leads-history')

urlpatterns = [
    path('', include(router.urls)),
# 📋 Shablonlarni boshqarish (CRUD) oynasi uchun yo'llar
    path('sms-templates/', SMSTemplateListCreateAPIView.as_view(), name='sms-template-list-create'),
    path('sms-templates/<int:pk>/', SMSTemplateRetrieveUpdateDestroyAPIView.as_view(), name='sms-template-detail'),

    # 🚀 Ommaviy xabar yuborish (SMS yuborish tugmasi)
    path('sms/send-bulk/', SendBulkSMSAPIView.as_view(), name='sms-send-bulk'),
    path('lead/history/', LeadHistoryAPIView.as_view(), name='crm-lead-history'),

# Adminlar paneli uchun yo'llar
    path('forms/', LeadFormListCreateAPIView.as_view(), name='lead-form-list-create'),
    path('forms/<int:pk>/', LeadFormRetrieveUpdateDestroyAPIView.as_view(), name='lead-form-detail'),

    # Tashqi foydalanuvchilar (Mijozlar) uchun public yo'llar
    path('public/forms/<int:pk>/', PublicLeadFormDetailAPIView.as_view(), name='public-form-detail'),
    path('public/forms/submit/', PublicLeadSubmitAPIView.as_view(), name='public-form-submit'),
]
