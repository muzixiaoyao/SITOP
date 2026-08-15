from django.http import HttpResponse
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import ServerGroup, Server, get_or_create_default_group
from .serializers import (
    ServerGroupSerializer, ServerGroupListSerializer,
    ServerSerializer, ServerBatchCreateSerializer,
    ServerBatchCredentialUpdateSerializer, ServerBatchDeleteSerializer,
    ServerBatchGroupSerializer,
)
from ..accounts.permissions import IsOperatorOrAbove, WriteRequiresOperator
from ..accounts.audit import audit


def get_tenant(request):
    """Get tenant from request, supporting both middleware and JWT auth."""
    return getattr(request, "tenant", None) or getattr(request.user, "tenant", None)


class ServerGroupListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, WriteRequiresOperator]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return ServerGroupListSerializer
        return ServerGroupSerializer

    def get_queryset(self):
        return ServerGroup.objects.filter(tenant=get_tenant(self.request))

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request), created_by=self.request.user)


class ServerGroupDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ServerGroupSerializer
    permission_classes = [IsAuthenticated, WriteRequiresOperator]

    def get_queryset(self):
        return ServerGroup.objects.filter(tenant=get_tenant(self.request))

    def perform_destroy(self, instance):
        from .models import DEFAULT_GROUP_NAME, get_or_create_default_group
        from django.db import transaction
        from rest_framework.exceptions import ValidationError

        if instance.name == DEFAULT_GROUP_NAME:
            raise ValidationError("默认分组不可删除")

        with transaction.atomic():
            servers = list(instance.servers.all())
            if servers:
                default_group = get_or_create_default_group(instance.tenant)
                default_group.servers.add(*servers)
            instance.delete()


class ServerListView(generics.ListAPIView):
    serializer_class = ServerSerializer

    def get_queryset(self):
        group_id = self.kwargs["group_pk"]
        return Server.objects.filter(
            groups__id=group_id, groups__tenant=get_tenant(self.request),
        ).distinct()


class ServerAllView(generics.ListAPIView):
    """List all servers for the current tenant (across all groups)."""
    serializer_class = ServerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_tenant(self.request)
        return Server.objects.filter(groups__tenant=tenant).distinct()


class ServerBatchCreateView(APIView):
    permission_classes = [IsAuthenticated, IsOperatorOrAbove]

    def post(self, request, group_pk=None):
        tenant = get_tenant(request)
        group = None
        if group_pk:
            try:
                group = ServerGroup.objects.get(id=group_pk, tenant=tenant)
            except ServerGroup.DoesNotExist:
                return Response(status=status.HTTP_404_NOT_FOUND)

        # 预检 IP 唯一性：剔除重复项（含批内重复），返回部分成功语义
        servers_data = request.data.get("servers")
        if not isinstance(servers_data, list) or not all(isinstance(s, dict) for s in servers_data):
            return Response({"detail": "servers 必须是对象数组"}, status=status.HTTP_400_BAD_REQUEST)
        existing_ips = set(
            Server.objects.filter(ip__in=[s.get("ip") for s in servers_data if s.get("ip")])
            .values_list("ip", flat=True)
        )
        filtered, errors = [], []
        for index, item in enumerate(servers_data):
            ip = item.get("ip")
            if ip and ip in existing_ips:
                errors.append({"index": index, "ip": ip, "error": "IP 地址已存在，不允许重复添加"})
                continue
            filtered.append(item)
            if ip:
                existing_ips.add(ip)

        serializer = ServerBatchCreateSerializer(
            data={"servers": filtered},
            context={"group": group, "tenant": tenant, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        servers = serializer.save()
        # 合并并发窗口下数据库约束触发的兜底错误（serializer.create 内捕获）
        errors += getattr(serializer, "_errors", [])
        audit(
            request, "server.batch_create", "server", "",
            {"count": len(servers), "group": group.name if group else "multi",
             "errors": len(errors)},
        )
        return Response(
            {
                "created": ServerSerializer(servers, many=True).data,
                "errors": errors,
            },
            status=status.HTTP_201_CREATED,
        )


class ServerDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ServerSerializer
    permission_classes = [IsAuthenticated, WriteRequiresOperator]

    def get_queryset(self):
        return Server.objects.filter(groups__tenant=get_tenant(self.request)).distinct()


class GroupPatrolView(APIView):
    """Manually trigger a connectivity patrol for a group (M4)."""
    permission_classes = [IsAuthenticated, IsOperatorOrAbove]

    def post(self, request, pk):
        tenant = get_tenant(request)
        try:
            group = ServerGroup.objects.get(id=pk, tenant=tenant)
        except ServerGroup.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        from .patrol import patrol_group

        counts = patrol_group(group)
        return Response(counts)


class ServerBatchOperationView(APIView):
    """Base view for batch operations on servers."""
    permission_classes = [IsAuthenticated, IsOperatorOrAbove]

    def get_servers(self, request, server_ids):
        """Get servers by IDs, ensuring they belong to the user's tenant."""
        tenant = get_tenant(request)
        servers = Server.objects.filter(
            id__in=server_ids, groups__tenant=tenant,
        ).distinct()
        found_ids = set(str(s.id) for s in servers)
        missing = [sid for sid in server_ids if str(sid) not in found_ids]
        return servers, missing


class ServerBatchConnectivityView(ServerBatchOperationView):
    """Batch connectivity test for selected servers."""

    def post(self, request):
        serializer = ServerBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        server_ids = serializer.validated_data["server_ids"]
        servers, missing = self.get_servers(request, server_ids)

        if missing:
            return Response({"detail": f"Servers not found: {missing}"}, status=status.HTTP_404_NOT_FOUND)

        from apps.executor.ssh import SSHExecutor
        from django.utils import timezone

        results = []
        with SSHExecutor(connect_timeout=10) as executor:
            for server in servers:
                result = executor.check_connectivity(server)
                is_ok = result.exit_code == 0 and "SITOP_CONNECTIVITY_OK" in result.output
                server.connectivity_status = "success" if is_ok else "failed"
                server.last_check_time = timezone.now()
                server.save(update_fields=["connectivity_status", "last_check_time"])
                results.append({
                    "server_id": str(server.id),
                    "hostname": server.hostname,
                    "status": "success" if is_ok else "failed",
                })

        audit(request, "server.batch_connectivity", "server", "", {"count": len(results)})
        return Response({"results": results, "total": len(results)})


class ServerBatchCredentialUpdateView(ServerBatchOperationView):
    """Batch update credentials for selected servers."""

    def post(self, request):
        serializer = ServerBatchCredentialUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        server_ids = serializer.validated_data["server_ids"]
        credential_id = serializer.validated_data["credential_id"]
        servers, missing = self.get_servers(request, server_ids)

        if missing:
            return Response({"detail": f"Servers not found: {missing}"}, status=status.HTTP_404_NOT_FOUND)

        from apps.accounts.models import SSHCredential
        try:
            credential = SSHCredential.objects.get(id=credential_id, tenant=get_tenant(request))
        except SSHCredential.DoesNotExist:
            return Response({"detail": "Credential not found"}, status=status.HTTP_404_NOT_FOUND)

        updated = servers.update(ssh_credential=credential)
        audit(request, "server.batch_credential_update", "server", "", {"count": updated, "credential": credential.name})
        return Response({"updated": updated})


class ServerBatchDeleteView(ServerBatchOperationView):
    """Batch delete selected servers."""

    def post(self, request):
        serializer = ServerBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        server_ids = serializer.validated_data["server_ids"]
        servers, missing = self.get_servers(request, server_ids)

        if missing:
            return Response({"detail": f"Servers not found: {missing}"}, status=status.HTTP_404_NOT_FOUND)

        deleted_count = servers.count()
        servers.delete()
        audit(request, "server.batch_delete", "server", "", {"count": deleted_count})
        return Response({"deleted": deleted_count})


class ServerBatchGroupMoveView(ServerBatchOperationView):
    """Move servers to target groups (replace all existing groups)."""

    def post(self, request):
        serializer = ServerBatchGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        server_ids = serializer.validated_data["server_ids"]
        group_ids = serializer.validated_data["group_ids"]
        servers, missing = self.get_servers(request, server_ids)

        if missing:
            return Response({"detail": f"Servers not found: {missing}"}, status=status.HTTP_404_NOT_FOUND)

        tenant = get_tenant(request)
        target_groups = ServerGroup.objects.filter(id__in=group_ids, tenant=tenant)
        if target_groups.count() != len(group_ids):
            return Response({"detail": "部分目标分组不存在"}, status=status.HTTP_404_NOT_FOUND)

        for server in servers:
            server.groups.set(target_groups)

        audit(
            request, "server.batch_group_move", "server", "",
            {"count": servers.count(), "target_groups": list(target_groups.values_list("name", flat=True))},
        )
        return Response({"updated": servers.count()})


class ServerBatchGroupAddView(ServerBatchOperationView):
    """Add servers to additional groups (keep existing groups)."""

    def post(self, request):
        serializer = ServerBatchGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        server_ids = serializer.validated_data["server_ids"]
        group_ids = serializer.validated_data["group_ids"]
        servers, missing = self.get_servers(request, server_ids)

        if missing:
            return Response({"detail": f"Servers not found: {missing}"}, status=status.HTTP_404_NOT_FOUND)

        tenant = get_tenant(request)
        target_groups = ServerGroup.objects.filter(id__in=group_ids, tenant=tenant)
        if target_groups.count() != len(group_ids):
            return Response({"detail": "部分目标分组不存在"}, status=status.HTTP_404_NOT_FOUND)

        for server in servers:
            server.groups.add(*target_groups)

        audit(
            request, "server.batch_group_add", "server", "",
            {"count": servers.count(), "added_groups": list(target_groups.values_list("name", flat=True))},
        )
        return Response({"updated": servers.count()})


class ServerImportView(APIView):
    """Import servers from CSV file."""
    permission_classes = [IsAuthenticated, IsOperatorOrAbove]

    def post(self, request, group_pk):
        tenant = get_tenant(request)
        try:
            group = ServerGroup.objects.get(id=group_pk, tenant=tenant)
        except ServerGroup.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        csv_file = request.FILES.get("file")
        if not csv_file:
            return Response({"detail": "No file uploaded"}, status=status.HTTP_400_BAD_REQUEST)

        from .batch import import_servers_csv, CSVDecodeError
        csv_content = csv_file.read()
        try:
            created, errors = import_servers_csv(csv_content, group, tenant, request.user)
        except CSVDecodeError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        audit(request, "server.import", "server", "", {"created": created, "errors": len(errors), "group": group.name})
        return Response({"created": created, "errors": errors}, status=status.HTTP_201_CREATED)


class ServerExportView(APIView):
    """Export servers to CSV file."""
    permission_classes = [IsAuthenticated]

    def get(self, request, group_pk):
        tenant = get_tenant(request)
        try:
            group = ServerGroup.objects.get(id=group_pk, tenant=tenant)
        except ServerGroup.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        servers = group.servers.all()
        from .batch import export_servers_csv
        csv_content = export_servers_csv(servers)

        response = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="servers_{group.name}.csv"'
        return response
