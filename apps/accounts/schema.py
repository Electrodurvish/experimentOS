"""OpenAPI (drf-spectacular) helpers: the API key security scheme and shared response components."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.utils import OpenApiResponse, inline_serializer
from rest_framework import serializers

# Security requirement for SDK endpoints (drf-spectacular passes `auth` through verbatim).
API_KEY_AUTH = [{"ApiKeyAuth": []}]


class APIKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.APIKeyAuthentication"
    name = "ApiKeyAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "Project API key used by SDKs and application services.",
        }


ErrorDetailSerializer = inline_serializer(
    name="ErrorDetail",
    fields={"detail": serializers.CharField()},
)


def error_response(description):
    return OpenApiResponse(response=ErrorDetailSerializer, description=description)
