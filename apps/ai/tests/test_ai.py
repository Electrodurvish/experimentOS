import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.ai import llm
from apps.ai.evidence import build_experiment_evidence
from apps.decisions.models import RolloutAction
from apps.decisions.rollout import change_rollout

RESULTS = {
    "control": {"exposures": 70000, "unique_users": 60000, "conversions": 6000, "conversion_rate": 0.10},
    "treatment": {"exposures": 70000, "unique_users": 60000, "conversions": 7200, "conversion_rate": 0.12},
}


@pytest.fixture(autouse=True)
def results():
    with patch("apps.decisions.context.query_experiment_results", return_value=RESULTS):
        yield


@pytest.fixture
def llm_on(settings):
    settings.ANTHROPIC_API_KEY = "sk-test"
    settings.AI_ENABLED = True
    llm._client = None
    yield
    llm._client = None


def fake_response(payload, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=json.dumps(payload))],
        model="claude-opus-5",
        _request_id="req_1",
    )


@pytest.mark.django_db
class TestEvidence:
    def test_bundle_has_numbered_evidence(self, running_experiment):
        change_rollout(running_experiment, 1000, RolloutAction.ROLLBACK, "error_rate_guardrail", automated=True)
        bundle = build_experiment_evidence(running_experiment)
        ids = [e["id"] for e in bundle["evidence"]]
        assert ids == [f"E{i + 1}" for i in range(len(ids))]
        kinds = {e["kind"] for e in bundle["evidence"]}
        assert {"decision", "results", "rollout", "timeline"} <= kinds
        assert bundle["experiment"]["rollout_percentage"] == 10


@pytest.mark.django_db
class TestTemplateFallback:
    def test_explain_without_key(self, authenticated_client, running_experiment):
        response = authenticated_client.get(f"/api/v1/experiments/{running_experiment.id}/explain/")
        assert response.status_code == 200
        assert response.data["generated_by"] == "template"
        assert response.data["cited_evidence"]
        assert response.data["recommendation"] == "COMPLETE"
        for eid in response.data["cited_evidence"]:
            assert f"[{eid}]" in response.data["explanation"]

    def test_ask_prefers_relevant_evidence(self, authenticated_client, running_experiment):
        change_rollout(running_experiment, 1000, RolloutAction.ROLLBACK, "error_rate_guardrail", automated=True)
        response = authenticated_client.post(
            f"/api/v1/experiments/{running_experiment.id}/ask/", {"question": "Why was it rolled back?"},
            format="json",
        )
        assert response.status_code == 200
        assert "error_rate_guardrail" in response.data["answer"]

    def test_portfolio_query(self, authenticated_client, running_experiment):
        change_rollout(running_experiment, 1000, RolloutAction.ROLLBACK, "errors")
        response = authenticated_client.post("/api/v1/ai/query/", {"question": "Which experiments were rolled back?"},
                                             format="json")
        assert response.status_code == 200
        assert response.data["experiments"][0]["key"] == running_experiment.key

    def test_requires_auth(self, api_client, running_experiment):
        assert api_client.get(f"/api/v1/experiments/{running_experiment.id}/explain/").status_code == 401

    def test_question_required(self, authenticated_client, running_experiment):
        response = authenticated_client.post(f"/api/v1/experiments/{running_experiment.id}/ask/", {}, format="json")
        assert response.status_code == 400


@pytest.mark.django_db
class TestLLM:
    def test_llm_answer_filters_unknown_citations(self, authenticated_client, running_experiment, llm_on):
        client = MagicMock()
        client.beta.messages.create.return_value = fake_response(
            {"answer": "Treatment wins [E1].", "cited_evidence": ["E1", "E999"]}
        )
        with patch.object(llm, "_get_client", return_value=client):
            response = authenticated_client.get(f"/api/v1/experiments/{running_experiment.id}/explain/")
        assert response.data["generated_by"] == "llm"
        assert response.data["cited_evidence"] == ["E1"]
        assert response.data["model"] == "claude-opus-5"

        kwargs = client.beta.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-opus-5"
        assert kwargs["thinking"] == {"type": "adaptive"}
        assert kwargs["fallbacks"] == "default"
        assert kwargs["output_config"]["format"]["type"] == "json_schema"
        assert "<evidence>" in kwargs["messages"][0]["content"]

    def test_refusal_falls_back_to_template(self, authenticated_client, running_experiment, llm_on):
        client = MagicMock()
        client.beta.messages.create.return_value = fake_response({}, stop_reason="refusal")
        with patch.object(llm, "_get_client", return_value=client):
            response = authenticated_client.get(f"/api/v1/experiments/{running_experiment.id}/explain/")
        assert response.data["generated_by"] == "template"

    def test_api_error_falls_back(self, authenticated_client, running_experiment, llm_on):
        import anthropic

        client = MagicMock()
        client.beta.messages.create.side_effect = anthropic.APIConnectionError(request=MagicMock())
        with patch.object(llm, "_get_client", return_value=client):
            response = authenticated_client.post(
                f"/api/v1/experiments/{running_experiment.id}/ask/", {"question": "why?"}, format="json",
            )
        assert response.data["generated_by"] == "template"

    def test_portfolio_llm_filters_unknown_keys(self, authenticated_client, running_experiment, llm_on):
        client = MagicMock()
        client.beta.messages.create.return_value = fake_response(
            {"answer": "Only one.", "experiment_keys": [running_experiment.key, "ghost"]}
        )
        with patch.object(llm, "_get_client", return_value=client):
            response = authenticated_client.post("/api/v1/ai/query/", {"question": "what is running?"},
                                                 format="json")
        assert [e["key"] for e in response.data["experiments"]] == [running_experiment.key]
