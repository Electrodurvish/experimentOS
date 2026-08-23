from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.experiments.views import ExperimentViewSet

router = DefaultRouter()
router.register("experiments", ExperimentViewSet, basename="experiment")

urlpatterns = [
    path("", include(router.urls)),
]
