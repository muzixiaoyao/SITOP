from datetime import timedelta

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tasks.models import InitJob
from apps.servers.models import Server, ServerGroup
from .generators import generate_csv_report, generate_pdf_report


def get_tenant(request):
    return getattr(request, "tenant", None) or getattr(request.user, "tenant", None)


def _get_job(request, pk):
    try:
        return InitJob.objects.get(id=pk, tenant=get_tenant(request))
    except InitJob.DoesNotExist:
        return None


class JobReportView(APIView):
    """Download a job report as CSV or PDF."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        job = _get_job(request, pk)
        if job is None:
            return Response({"detail": "Job not found"}, status=404)

        fmt = request.query_params.get("format", "csv").lower()
        if fmt == "pdf":
            content = generate_pdf_report(job)
            response = HttpResponse(content, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="sitop_report_{job.id}.pdf"'
            return response

        content = generate_csv_report(job)
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="sitop_report_{job.id}.csv"'
        return response


class JobSummaryView(APIView):
    """Structured summary: success rate, phase timing, failed servers."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        job = _get_job(request, pk)
        if job is None:
            return Response({"detail": "Job not found"}, status=404)

        qs = job.server_tasks
        total = qs.count()
        success = qs.filter(status="success").count()
        failed_tasks = qs.filter(status__in=["failed", "timeout"])

        duration = None
        if job.start_time and job.end_time:
            duration = (job.end_time - job.start_time).total_seconds()

        return Response({
            "job_id": str(job.id),
            "status": job.status,
            "total": total,
            "success": success,
            "failed": failed_tasks.count(),
            "success_rate": round(success / total * 100, 1) if total else 0,
            "duration_seconds": duration,
            "failed_servers": [
                {"hostname": t.server.hostname, "ip": t.server.ip, "status": t.status}
                for t in failed_tasks.select_related("server")
            ],
        })


class DashboardStatsView(APIView):
    """Aggregated statistics for the dashboard."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        now = timezone.now()
        jobs = InitJob.objects.filter(tenant=tenant)
        recent = jobs.filter(created_at__gte=now - timedelta(days=7))

        finished = jobs.filter(status__in=["success", "failed", "cancelled"])
        success_count = finished.filter(status="success").count()

        # Last 7 days trend: per-day total and success
        trend = []
        for i in range(6, -1, -1):
            day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            day_jobs = jobs.filter(created_at__gte=day_start, created_at__lt=day_end)
            trend.append({
                "date": day_start.strftime("%m-%d"),
                "total": day_jobs.count(),
                "success": day_jobs.filter(status="success").count(),
            })

        status_dist = {}
        for s in ["pending", "running", "success", "failed", "cancelled"]:
            status_dist[s] = jobs.filter(status=s).count()

        return Response({
            "total_jobs": jobs.count(),
            "recent_jobs": recent.count(),
            "success_count": success_count,
            "success_rate": round(success_count / finished.count() * 100, 1) if finished.exists() else 0,
            "total_servers": Server.objects.filter(groups__tenant=tenant).distinct().count(),
            "total_groups": ServerGroup.objects.filter(tenant=tenant).count(),
            "trend": trend,
            "status_distribution": status_dist,
        })
