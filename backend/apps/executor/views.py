import time
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.servers.models import ServerGroup
from .serializers import (
    ConnectivityCheckResultSerializer,
    CommandExecutionRequestSerializer,
    CommandExecutionResultSerializer,
)
from .ssh import SSHExecutor
from ..accounts.permissions import IsOperatorOrAbove
from ..accounts.throttles import ConnectivityThrottle


class ConnectivityCheckView(APIView):
    permission_classes = [IsAuthenticated, IsOperatorOrAbove]
    throttle_classes = [ConnectivityThrottle]

    def post(self, request, group_pk):
        tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)
        try:
            group = ServerGroup.objects.get(id=group_pk, tenant=tenant)
        except ServerGroup.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        servers = group.servers.all()
        if not servers:
            return Response({"detail": "No servers in this group"}, status=400)

        with SSHExecutor(connect_timeout=10) as executor:
            results = []
            for server in servers:
                start = time.time()
                result = executor.check_connectivity(server)
                latency_ms = int((time.time() - start) * 1000)
                is_ok = result.exit_code == 0 and "SITOP_CONNECTIVITY_OK" in result.output
                server.connectivity_status = "success" if is_ok else "failed"
                server.last_check_time = timezone.now()
                server.save(update_fields=["connectivity_status", "last_check_time"])
                results.append({
                    "server_id": str(server.id),
                    "hostname": server.hostname,
                    "ip": server.ip,
                    "status": "success" if is_ok else "failed",
                    "message": result.output if is_ok else result.error,
                    "latency_ms": latency_ms if is_ok else None,
                })

        return Response(ConnectivityCheckResultSerializer(results, many=True).data)


class CommandExecutionView(APIView):
    permission_classes = [IsAuthenticated, IsOperatorOrAbove]

    def post(self, request, group_pk):
        tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)
        try:
            group = ServerGroup.objects.get(id=group_pk, tenant=tenant)
        except ServerGroup.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        req_serializer = CommandExecutionRequestSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)
        command = req_serializer.validated_data["command"]

        servers = group.servers.all()
        with SSHExecutor(exec_timeout=120) as executor:
            results = []
            for server in servers:
                result = executor.execute_command(server, command)
                results.append({
                    "server_id": str(server.id),
                    "hostname": server.hostname,
                    "exit_code": result.exit_code,
                    "output": result.output,
                    "error": result.error,
                })

        return Response(CommandExecutionResultSerializer(results, many=True).data)
