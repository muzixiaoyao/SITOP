import logging
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.servers.models import ServerGroup
from apps.accounts.audit import audit
from apps.accounts.permissions import WriteRequiresOperator
from apps.accounts.throttles import JobCreateThrottle
from .models import InitTemplate, InitJob
from .serializers import (
    InitTemplateSerializer, InitTemplateCreateSerializer,
    InitJobSerializer, InitJobListSerializer,
)
from .celery_tasks import run_job_task
from .progress import publish_job_update

logger = logging.getLogger(__name__)


def get_tenant(request):
    return getattr(request, "tenant", None) or getattr(request.user, "tenant", None)


class TemplateListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, WriteRequiresOperator]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return InitTemplateCreateSerializer
        return InitTemplateSerializer

    def get_queryset(self):
        return InitTemplate.objects.filter(tenant=get_tenant(self.request))

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request), created_by=self.request.user)


class TemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, WriteRequiresOperator]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return InitTemplateCreateSerializer
        return InitTemplateSerializer

    def get_queryset(self):
        return InitTemplate.objects.filter(tenant=get_tenant(self.request))


class JobListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, WriteRequiresOperator]
    throttle_classes = [JobCreateThrottle]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return InitJobSerializer
        return InitJobListSerializer

    def get_queryset(self):
        return InitJob.objects.filter(tenant=get_tenant(self.request))

    def create(self, request, *args, **kwargs):
        """Create a job and dispatch it to the task queue."""
        tenant = get_tenant(request)
        template_id = request.data.get("template")
        group_id = request.data.get("group")

        try:
            template = InitTemplate.objects.get(id=template_id, tenant=tenant)
        except InitTemplate.DoesNotExist:
            return Response({"detail": "Template not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            group = ServerGroup.objects.get(id=group_id, tenant=tenant)
        except ServerGroup.DoesNotExist:
            return Response({"detail": "Server group not found"}, status=status.HTTP_404_NOT_FOUND)

        if not group.servers.exists():
            return Response({"detail": "No servers in this group"}, status=status.HTTP_400_BAD_REQUEST)

        job = InitJob.objects.create(
            tenant=tenant,
            template=template,
            group=group,
            triggered_by=request.user,
            status="pending",
        )

        # Dispatch to Celery (eager in dev, real worker in production)
        run_job_task.delay(str(job.id))
        audit(request, "job.create", "job", job.id,
              {"template": template.name, "group": group.name})

        job.refresh_from_db()
        serializer = InitJobSerializer(job)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class JobDetailView(generics.RetrieveAPIView):
    serializer_class = InitJobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return InitJob.objects.filter(tenant=get_tenant(self.request))


class JobCancelView(APIView):
    """Cancel a pending/running job. Cooperative — the engine checks status."""
    permission_classes = [IsAuthenticated, WriteRequiresOperator]

    def post(self, request, pk):
        tenant = get_tenant(request)
        try:
            job = InitJob.objects.get(id=pk, tenant=tenant)
        except InitJob.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if job.status not in ("pending", "running"):
            return Response(
                {"detail": f"Job is already {job.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        job.status = "cancelled"
        job.end_time = timezone.now()
        job.save(update_fields=["status", "end_time"])
        job.server_tasks.filter(status__in=["pending", "running"]).update(status="cancelled")
        publish_job_update(job.id, "job.cancelled")
        audit(request, "job.cancel", "job", job.id)
        return Response({"detail": "Job cancelled"})


class CompletionMatrixView(APIView):
    """Server × step completion matrix built from completion check results."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        tenant = get_tenant(request)
        try:
            job = InitJob.objects.get(id=pk, tenant=tenant)
        except InitJob.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        steps = list(job.template.steps.all().order_by("step_order")) if job.template else []
        step_names = [f"step{s.step_order}: {s.script.name}" for s in steps]

        rows = []
        for task in job.server_tasks.select_related("server").all():
            completion = task.completion_result or {}
            step_results = completion.get("steps", {})
            row = {
                "server_id": str(task.server.id),
                "hostname": task.server.hostname,
                "ip": task.server.ip,
                "task_status": task.status,
                "steps": {},
            }
            for i, name in enumerate(step_names, start=1):
                # Match by explicit key, positional key, or fallback unknown
                row["steps"][name] = (
                    step_results.get(name)
                    or step_results.get(f"step{i}")
                    or step_results.get(str(i))
                    or ("unknown" if completion else task.status)
                )
            rows.append(row)

        return Response({"step_names": step_names, "rows": rows})
