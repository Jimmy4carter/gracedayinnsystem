from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import UserProfileViewSet, GuestProfileViewSet

router = DefaultRouter()
router.register('users', UserProfileViewSet, basename='user')
router.register('guests', GuestProfileViewSet, basename='guest')

urlpatterns = [
    path('', include(router.urls)),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
