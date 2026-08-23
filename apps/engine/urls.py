from django.urls import path

from apps.engine.views import EvaluateDebugView, EvaluateView

urlpatterns = [
    path("evaluate/", EvaluateView.as_view(), name="evaluate"),
    path("evaluate/debug/", EvaluateDebugView.as_view(), name="evaluate-debug"),
]
