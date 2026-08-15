from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views

urlpatterns = [
    path("login/", TokenObtainPairView.as_view(), name="token_obtain"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", views.MeView.as_view(), name="me"),
    path("users/", views.UserListView.as_view(), name="user-list"),
    path("users/<uuid:pk>/", views.UserDetailView.as_view(), name="user-detail"),
    path("credentials/", views.SSHCredentialListView.as_view(), name="credential-list"),
    path("credentials/<uuid:pk>/", views.SSHCredentialDetailView.as_view(), name="credential-detail"),
    path("audit-logs/", views.AuditLogListView.as_view(), name="audit-log-list"),
]
