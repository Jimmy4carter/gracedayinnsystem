from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import UserProfileViewSet, GuestProfileViewSet

router = DefaultRouter()
router.register('users', UserProfileViewSet, basename='user')
router.register('guests', GuestProfileViewSet, basename='guest')

urlpatterns = [
    # Auth shortcuts
    path('auth/login/', UserProfileViewSet.as_view({'post': 'login'}), name='api-login'),
    path('auth/logout/', UserProfileViewSet.as_view({'post': 'logout'}), name='api-logout'),
    path('auth/register/', UserProfileViewSet.as_view({'post': 'register'}), name='api-register'),
    path('auth/me/', UserProfileViewSet.as_view({'get': 'me', 'put': 'update_me', 'patch': 'update_me'}), name='api-me'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('', include(router.urls)),
]
