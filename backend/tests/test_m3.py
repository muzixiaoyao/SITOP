from unittest.mock import patch, MagicMock
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Tenant, User, AuditLog
from apps.servers.models import ServerGroup, Server
from apps.scripts.models import Script
from apps.executor.ssh import ExecutionResult
from apps.tasks.models import InitTemplate, InitJob


class M3TestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="t1")
        self.admin = User.objects.create_user(
            username="admin", password="p", tenant=self.tenant, role="admin"
        )
        self.operator = User.objects.create_user(
            username="op", password="p", tenant=self.tenant, role="operator"
        )
        self.viewer = User.objects.create_user(
            username="viewer", password="p", tenant=self.tenant, role="viewer"
        )
        self.group = ServerGroup.objects.create(
            tenant=self.tenant, name="g1", created_by=self.admin
        )
        self.server = Server.objects.create(hostname="s1", ip="10.0.0.1")
        self.server.groups.add(self.group)

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c


class TestAuditLog(M3TestCase):
    def test_job_create_writes_audit(self):
        template = InitTemplate.objects.create(
            tenant=self.tenant, name="tpl", created_by=self.admin
        )
        with patch("apps.tasks.views.run_job_task") as mock_task:
            mock_task.delay = MagicMock()
            client = self._client(self.operator)
            resp = client.post("/api/jobs/", {"template": str(template.id), "group": str(self.group.id)})
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(AuditLog.objects.filter(action="job.create").exists())

    def test_audit_log_admin_only(self):
        AuditLog.objects.create(tenant=self.tenant, user=self.admin, action="test", resource_type="job")
        # admin can read
        resp = self._client(self.admin).get("/api/auth/audit-logs/")
        self.assertEqual(resp.status_code, 200)
        # operator cannot
        resp = self._client(self.operator).get("/api/auth/audit-logs/")
        self.assertEqual(resp.status_code, 403)

    def test_audit_cross_tenant_invisible(self):
        other = Tenant.objects.create(name="t2")
        AuditLog.objects.create(tenant=other, action="secret", resource_type="job")
        resp = self._client(self.admin).get("/api/auth/audit-logs/")
        actions = [r["action"] for r in resp.data["results"]]
        self.assertNotIn("secret", actions)


class TestRBAC(M3TestCase):
    def test_viewer_cannot_create_group(self):
        resp = self._client(self.viewer).post("/api/groups/", {"name": "hack"})
        self.assertEqual(resp.status_code, 403)

    def test_viewer_can_read_groups(self):
        resp = self._client(self.viewer).get("/api/groups/")
        self.assertEqual(resp.status_code, 200)

    def test_operator_cannot_manage_users(self):
        resp = self._client(self.operator).post(
            "/api/auth/users/", {"username": "x", "password": "pp1234", "tenant": str(self.tenant.id)}
        )
        self.assertEqual(resp.status_code, 403)

    def test_viewer_cannot_create_job(self):
        template = InitTemplate.objects.create(tenant=self.tenant, name="tpl", created_by=self.admin)
        resp = self._client(self.viewer).post(
            "/api/jobs/", {"template": str(template.id), "group": str(self.group.id)}
        )
        self.assertEqual(resp.status_code, 403)

    def test_viewer_can_download_report(self):
        job = InitJob.objects.create(
            tenant=self.tenant, group=self.group, triggered_by=self.admin, status="success"
        )
        resp = self._client(self.viewer).get(f"/api/jobs/{job.id}/report/?format=csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])


class TestReports(M3TestCase):
    def _finished_job(self):
        job = InitJob.objects.create(
            tenant=self.tenant, group=self.group, triggered_by=self.admin, status="success"
        )
        from apps.tasks.models import JobServerTask
        JobServerTask.objects.create(job=job, server=self.server, status="success")
        return job

    def test_csv_report_contains_server_row(self):
        job = self._finished_job()
        resp = self._client(self.operator).get(f"/api/jobs/{job.id}/report/?format=csv")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8-sig")
        self.assertIn("s1", content)
        self.assertIn("10.0.0.1", content)

    def test_pdf_report_content_type(self):
        job = self._finished_job()
        resp = self._client(self.operator).get(f"/api/jobs/{job.id}/report/?format=pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_job_summary(self):
        job = self._finished_job()
        resp = self._client(self.operator).get(f"/api/jobs/{job.id}/summary/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total"], 1)
        self.assertEqual(resp.data["success"], 1)
        self.assertEqual(resp.data["success_rate"], 100.0)

    def test_dashboard_stats(self):
        self._finished_job()
        resp = self._client(self.viewer).get("/api/stats/dashboard/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total_jobs"], 1)
        self.assertEqual(resp.data["total_servers"], 1)
        self.assertEqual(len(resp.data["trend"]), 7)


class TestThrottling(M3TestCase):
    def test_connectivity_throttle(self):
        client = self._client(self.operator)
        with patch("apps.executor.views.SSHExecutor") as MockExec:
            executor = MagicMock()
            executor.check_connectivity.return_value = ExecutionResult(0, "SITOP_CONNECTIVITY_OK", "")
            executor.__enter__ = MagicMock(return_value=executor)
            executor.__exit__ = MagicMock(return_value=False)
            MockExec.return_value = executor
            for i in range(5):
                resp = client.post(f"/api/groups/{self.group.id}/check-connectivity/")
                self.assertEqual(resp.status_code, 200, f"request {i+1} should pass")
            # 6th request within the same minute should be throttled
            resp = client.post(f"/api/groups/{self.group.id}/check-connectivity/")
            self.assertEqual(resp.status_code, 429)
