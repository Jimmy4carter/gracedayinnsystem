from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HousekeepingTaskViewSet, MaintenanceTicketViewSet

router = DefaultRouter()
router.register('housekeeping-tasks', HousekeepingTaskViewSet, basename='housekeeping-task')
router.register('maintenance-tickets', MaintenanceTicketViewSet, basename='maintenance-ticket')

urlpatterns = [path('', include(router.urls))]
