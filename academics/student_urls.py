from django.urls import path, include
from rest_framework.routers import DefaultRouter
from academics.views import StudentViewSet, ParentViewSet, StudentAddressViewSet

router = DefaultRouter()
router.register(r'parents', ParentViewSet, basename='student-parent')
router.register(r'addresses', StudentAddressViewSet, basename='student-address')
router.register(r'', StudentViewSet, basename='student-direct')

urlpatterns = [
    path('', include(router.urls)),
]
