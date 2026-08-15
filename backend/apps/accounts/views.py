from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import User, SSHCredential, AuditLog
from .serializers import (
    UserSerializer, UserCreateSerializer,
    SSHCredentialSerializer, MeSerializer, AuditLogSerializer,
)
from .permissions import IsAdmin


def get_tenant(request):
    """Get tenant from request, supporting both middleware and JWT auth."""
    return getattr(request, "tenant", None) or getattr(request.user, "tenant", None)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = MeSerializer(request.user)
        return Response(serializer.data)


class UserListView(generics.ListCreateAPIView):
    def get_queryset(self):
        return User.objects.filter(tenant=get_tenant(self.request))

    def get_serializer_class(self):
        if self.request.method == "POST":
            return UserCreateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdmin()]
        return [IsAuthenticated()]


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(tenant=get_tenant(self.request))

    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            return [IsAdmin()]
        return [IsAuthenticated()]


class SSHCredentialListView(generics.ListCreateAPIView):
    serializer_class = SSHCredentialSerializer

    def get_queryset(self):
        return SSHCredential.objects.filter(tenant=get_tenant(self.request))


class SSHCredentialDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SSHCredentialSerializer

    def get_queryset(self):
        return SSHCredential.objects.filter(tenant=get_tenant(self.request))


class AuditLogListView(generics.ListAPIView):
    """Admin-only, read-only audit trail with filtering."""
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
        qs = AuditLog.objects.filter(tenant=get_tenant(self.request))
        action = self.request.query_params.get("action")
        resource_type = self.request.query_params.get("resource_type")
        if action:
            qs = qs.filter(action__icontains=action)
        if resource_type:
            qs = qs.filter(resource_type=resource_type)
        return qs
