from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.accounts.permissions import WriteRequiresOperator, IsOperatorOrAbove
from apps.servers.models import Server
from .models import Script, ScriptVersion
from .serializers import ScriptSerializer, ScriptVersionSerializer


def get_tenant(request):
    return getattr(request, "tenant", None) or getattr(request.user, "tenant", None)


class ScriptListView(generics.ListCreateAPIView):
    serializer_class = ScriptSerializer
    permission_classes = [IsAuthenticated, WriteRequiresOperator]

    def get_queryset(self):
        qs = Script.objects.filter(tenant=get_tenant(self.request))
        script_type = self.request.query_params.get("script_type")
        if script_type:
            qs = qs.filter(script_type=script_type)
        return qs

    def perform_create(self, serializer):
        script = serializer.save(
            tenant=get_tenant(self.request),
            created_by=self.request.user,
        )
        # Snapshot v1
        script.save_version_snapshot()


class ScriptDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ScriptSerializer
    permission_classes = [IsAuthenticated, WriteRequiresOperator]

    def get_queryset(self):
        return Script.objects.filter(tenant=get_tenant(self.request))

    def perform_update(self, serializer):
        script = serializer.instance
        new_content = serializer.validated_data.get("content")
        # Bump version when content changes; snapshot the new version
        if new_content is not None and new_content != script.content:
            serializer.save(version=script.version + 1)
            script.refresh_from_db()
            script.save_version_snapshot()
        else:
            serializer.save()


class ScriptVersionListView(generics.ListAPIView):
    serializer_class = ScriptVersionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ScriptVersion.objects.filter(
            script_id=self.kwargs["pk"],
            script__tenant=get_tenant(self.request),
        )


class ScriptTestRunView(APIView):
    """Execute script content on a single server and return the output (M4)."""
    permission_classes = [IsAuthenticated, IsOperatorOrAbove]

    def post(self, request, pk):
        tenant = get_tenant(request)
        try:
            script = Script.objects.get(id=pk, tenant=tenant)
        except Script.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        server_id = request.data.get("server_id")
        content = request.data.get("content") or script.content
        try:
            server = Server.objects.filter(id=server_id, groups__tenant=tenant).distinct().first()
            if not server:
                raise Server.DoesNotExist
        except Server.DoesNotExist:
            return Response({"detail": "Server not found"}, status=status.HTTP_404_NOT_FOUND)

        from apps.executor.ssh import SSHExecutor

        with SSHExecutor(exec_timeout=60) as executor:
            result = executor.execute_script(server, content, script.language)

        return Response({
            "exit_code": result.exit_code,
            "output": result.output[:10000],
            "error": result.error[:5000],
        })
