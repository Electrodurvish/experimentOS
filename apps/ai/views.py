from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.ai.evidence import build_experiment_evidence, build_portfolio_evidence
from apps.ai.llm import answer_experiment_question, answer_portfolio_question
from apps.experiments.models import Experiment
from apps.organizations.models import Role
from apps.organizations.permissions import accessible_organization_ids

EXPLAIN_QUESTION = (
    "Summarize this experiment for a product team: what result it produced, why "
    "(which segments, metrics or production signals drove it), whether the result is trustworthy, "
    "and what the platform recommends next."
)


class QuestionSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=1000)
    segments = serializers.ListField(child=serializers.DictField(), required=False, default=list)


class _AIView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"
    rbac_write_role = Role.ANALYST

    def get_experiment(self, experiment_id):
        return get_object_or_404(
            Experiment.objects.select_related("current_version").prefetch_related(
                "current_version__variants", "guardrails",
            ),
            id=experiment_id,
        )


class ExplainView(_AIView):
    """
    GET /api/v1/experiments/{id}/explain/
    Evidence-based summary of the experiment.
    """

    def get(self, request, experiment_id):
        experiment = self.get_experiment(experiment_id)
        bundle = build_experiment_evidence(experiment)
        result = answer_experiment_question(bundle, EXPLAIN_QUESTION)
        return Response({
            "experiment_id": str(experiment.id),
            "experiment_key": experiment.key,
            "summary": bundle["decision"]["summary"],
            "recommendation": bundle["decision"]["recommendation"],
            "explanation": result["answer"],
            "cited_evidence": result["cited_evidence"],
            "evidence": bundle["evidence"],
            "generated_by": result["generated_by"],
            "model": result["model"],
        })


class AskView(_AIView):
    """
    POST /api/v1/experiments/{id}/ask/  {question, segments?}
    Root-cause and follow-up questions about one experiment.
    """

    def post(self, request, experiment_id):
        serializer = QuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        experiment = self.get_experiment(experiment_id)
        bundle = build_experiment_evidence(experiment, segments=serializer.validated_data["segments"])
        result = answer_experiment_question(bundle, serializer.validated_data["question"])
        return Response({
            "experiment_id": str(experiment.id),
            "experiment_key": experiment.key,
            "question": serializer.validated_data["question"],
            "answer": result["answer"],
            "cited_evidence": result["cited_evidence"],
            "evidence": bundle["evidence"],
            "generated_by": result["generated_by"],
            "model": result["model"],
        })


class PortfolioQueryView(_AIView):
    """
    POST /api/v1/ai/query/  {question}
    Natural-language questions across experiments, e.g. "Which experiments were rolled back this week?"
    """

    def post(self, request):
        serializer = QuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        queryset = Experiment.objects.exclude(status="ARCHIVED")
        if not request.user.is_superuser:
            queryset = queryset.filter(project__organization_id__in=accessible_organization_ids(request.user))
        experiments = list(queryset.order_by("-updated_at")[:100])
        rows = build_portfolio_evidence(experiments)
        result = answer_portfolio_question(rows, serializer.validated_data["question"])
        by_key = {e.key: e for e in experiments}
        return Response({
            "question": serializer.validated_data["question"],
            "answer": result["answer"],
            "experiments": [
                {"id": str(by_key[k].id), "key": k, "status": by_key[k].status}
                for k in result["experiment_keys"] if k in by_key
            ],
            "generated_by": result["generated_by"],
            "model": result["model"],
        }, status=status.HTTP_200_OK)
