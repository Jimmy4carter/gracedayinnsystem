from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    # API routes - all under /api/
    path('api/', include('apps.accounts.urls')),
    path('api/', include('apps.rooms.urls')),
    path('api/', include('apps.reservations.urls')),
    path('api/', include('apps.billing.urls')),
    path('api/', include('apps.payments.urls')),
    path('api/', include('apps.services.urls')),
    path('api/', include('apps.housekeeping.urls')),
    path('api/', include('apps.notifications.urls')),
    # Frontend
    path('', include(('apps.frontend.urls', 'frontend'), namespace='frontend')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) \
  + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
