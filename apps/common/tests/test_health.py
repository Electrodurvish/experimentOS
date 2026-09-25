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
