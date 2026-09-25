import pytest
from unittest.mock import MagicMock, patch

from apps.observability.middleware import MetricsMiddleware


class TestMetricsMiddleware:
    def test_calls_get_response(self):
        mock_response = MagicMock(status_code=200)
        mock_get_response = MagicMock(return_value=mock_response)
        middleware = MetricsMiddleware(mock_get_response)

        mock_request = MagicMock()
        mock_request.path = "/api/v1/test/"
        mock_request.method = "GET"

        with patch("apps.observability.middleware.record_request") as mock_record:
            response = middleware(mock_request)

        assert response == mock_response
        mock_get_response.assert_called_once_with(mock_request)

    def test_records_request_metric(self):
        mock_response = MagicMock(status_code=200)
        mock_get_response = MagicMock(return_value=mock_response)
        middleware = MetricsMiddleware(mock_get_response)

        mock_request = MagicMock()
        mock_request.path = "/api/v1/test/"
        mock_request.method = "GET"

        with patch("apps.observability.middleware.record_request") as mock_record:
            middleware(mock_request)
            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["method"] == "GET"
            assert call_kwargs["status_code"] == 200
            assert call_kwargs["duration"] > 0


class TestNormalizePath:
    def test_replace_uuid(self):
        path = "/api/v1/experiments/550e8400-e29b-41d4-a716-446655440000/results/"
        result = MetricsMiddleware._normalize_path(path)
        assert result == "/api/v1/experiments/{id}/results/"

    def test_replace_numeric_id(self):
        path = "/api/v1/users/12345/profile/"
        result = MetricsMiddleware._normalize_path(path)
        assert result == "/api/v1/users/{id}/profile/"

    def test_no_replacement_needed(self):
        path = "/api/v1/experiments/"
        result = MetricsMiddleware._normalize_path(path)
        assert result == "/api/v1/experiments/"

    def test_multiple_uuids(self):
        path = "/api/v1/experiments/550e8400-e29b-41d4-a716-446655440000/variants/660e8400-e29b-41d4-a716-446655440001/"
        result = MetricsMiddleware._normalize_path(path)
        assert "{id}" in result
        assert "550e8400" not in result
