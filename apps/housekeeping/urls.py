from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HousekeepingTaskViewSet

router = DefaultRouter()
router.register('housekeeping-tasks', HousekeepingTaskViewSet, basename='housekeeping-task')

urlpatterns = [path('', include(router.urls))]
