from django.urls import path

from apps.engine.views import EvaluateDebugView, EvaluateView, ExperimentUserDebugView, UserAssignmentsView

urlpatterns = [
    path("evaluate/", EvaluateView.as_view(), name="evaluate"),
    path("evaluate/debug/", EvaluateDebugView.as_view(), name="evaluate-debug"),
    path("users/<str:user_id>/assignments/", UserAssignmentsView.as_view(), name="user-assignments"),
    path(
        "experiments/<uuid:experiment_id>/users/<str:user_id>/debug/",
        ExperimentUserDebugView.as_view(),
        name="experiment-user-debug",
    ),
]
