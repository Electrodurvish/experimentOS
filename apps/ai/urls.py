from django.urls import path

from apps.ai.views import AskView, ExplainView, PortfolioQueryView

urlpatterns = [
    path("experiments/<uuid:experiment_id>/explain/", ExplainView.as_view(), name="experiment-explain"),
    path("experiments/<uuid:experiment_id>/ask/", AskView.as_view(), name="experiment-ask"),
    path("ai/query/", PortfolioQueryView.as_view(), name="ai-query"),
]
