from django.urls import path

from apps.decisions import views

urlpatterns = [
    path("experiments/<uuid:experiment_id>/guardrails/", views.GuardrailListCreateView.as_view(),
         name="guardrail-list"),
    path("experiments/<uuid:experiment_id>/guardrails/<uuid:guardrail_id>/", views.GuardrailDetailView.as_view(),
         name="guardrail-detail"),
    path("experiments/<uuid:experiment_id>/rollout-policy/", views.RolloutPolicyView.as_view(),
         name="rollout-policy"),
    path("experiments/<uuid:experiment_id>/rollout/", views.RolloutView.as_view(), name="rollout"),
    path("experiments/<uuid:experiment_id>/rollback/", views.RollbackView.as_view(), name="rollback"),
    path("experiments/<uuid:experiment_id>/decision/", views.DecisionView.as_view(), name="decision"),
    path("experiments/<uuid:experiment_id>/decisions/", views.DecisionHistoryView.as_view(), name="decision-history"),
    path("experiments/<uuid:experiment_id>/anomalies/", views.AnomalyView.as_view(), name="anomalies"),
]
