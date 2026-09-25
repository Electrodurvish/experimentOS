from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import APIKeyCreateView, APIKeyRevokeView, MeView, RegisterView, ThrottledTokenObtainPairView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("api-keys/", APIKeyCreateView.as_view(), name="api-keys"),
    path("api-keys/<uuid:key_id>/", APIKeyRevokeView.as_view(), name="api-key-revoke"),
]
