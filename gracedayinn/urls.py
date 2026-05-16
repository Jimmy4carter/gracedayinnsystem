from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/accounts/', include('apps.accounts.urls')),
    path('api/rooms/', include('apps.rooms.urls')),
    path('api/reservations/', include('apps.reservations.urls')),
    path('api/billing/', include('apps.billing.urls')),
    path('api/payments/', include('apps.payments.urls')),
    path('api/services/', include('apps.services.urls')),
    path('api/housekeeping/', include('apps.housekeeping.urls')),
    path('api/notifications/', include('apps.notifications.urls')),
    path('', include('apps.frontend.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) \
  + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
