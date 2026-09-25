from unittest.mock import patch

import pytest


def test_healthz(api_client):
    response = api_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readyz(api_client):
    response = api_client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["database"] == "up"


@pytest.mark.django_db
def test_readyz_database_down(api_client):
    with patch("apps.common.health.connection.cursor", side_effect=Exception("down")):
        response = api_client.get("/readyz")
    assert response.status_code == 503


def test_list_validation_errors_are_wrapped():
    from rest_framework.exceptions import ValidationError

    from apps.common.exceptions import custom_exception_handler

    response = custom_exception_handler(ValidationError("nope"), {})
    assert response.status_code == 400
    assert response.data["detail"] == ["nope"]
    assert response.data["status_code"] == 400
