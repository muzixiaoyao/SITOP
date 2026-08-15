from unittest.mock import patch, MagicMock
from django.test import TestCase

from apps.accounts.models import Tenant, User
from apps.servers.models import ServerGroup, Server, SSHCredential
from apps.scripts.models import Script
from apps.executor.ssh import ExecutionResult
from apps.tasks.models import InitTemplate, TemplateStep, InitJob
from apps.tasks import engine


def ok(output=""):
    return ExecutionResult(0, output, "")


def fail(output="", error="boom"):
    return ExecutionResult(1, output, error)


class EngineTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="t1")
        self.user = User.objects.create_user(
            username="op", password="p", tenant=self.tenant, role="operator"
        )
        self.group = ServerGroup.objects.create(tenant=self.tenant, name="g1", created_by=self.user)
        self.s1 = Server.objects.create(hostname="s1", ip="10.0.0.1")
        self.s1.groups.add(self.group)
        self.s2 = Server.objects.create(hostname="s2", ip="10.0.0.2")
        self.s2.groups.add(self.group)

        self.health = Script.objects.create(
            tenant=self.tenant, name="health", script_type="health_check",
            content='echo {"status":"ok"}', created_by=self.user,
        )
        self.step1 = Script.objects.create(
            tenant=self.tenant, name="step1", script_type="init_step",
            content="echo step1", created_by=self.user,
        )
        self.completion = Script.objects.create(
            tenant=self.tenant, name="completion", script_type="completion_check",
            content='echo {"step1":"ok"}', created_by=self.user,
        )
        self.template = InitTemplate.objects.create(
            tenant=self.tenant, name="tpl", created_by=self.user,
            health_check_script=self.health, completion_check_script=self.completion,
        )
        TemplateStep.objects.create(
            template=self.template, step_order=1, script=self.step1,
            on_failure="abort",
        )

    def _create_job(self):
        return InitJob.objects.create(
            tenant=self.tenant, template=self.template, group=self.group,
            triggered_by=self.user, status="pending",
        )

    @patch("apps.tasks.engine.SSHExecutor")
    def test_full_success_flow(self, MockExecutor):
        executor = MagicMock()
        executor.check_connectivity.return_value = ok("SITOP_CONNECTIVITY_OK")
        executor.execute_script.side_effect = [
            ok('{"status": "ok"}'),   # health s1
            ok('{"status": "ok"}'),   # health s2
            ok("done"),               # init step1 s1
            ok("done"),               # init step1 s2
            ok('{"step1": "ok"}'),    # completion s1
            ok('{"step1": "ok"}'),    # completion s2
        ]
        executor.__enter__ = MagicMock(return_value=executor)
        executor.__exit__ = MagicMock(return_value=False)
        MockExecutor.return_value = executor

        job = self._create_job()
        engine.run_job(job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, "success")
        self.assertEqual(job.summary["success"], 2)
        self.assertEqual(job.summary["failed"], 0)
        for task in job.server_tasks.all():
            self.assertEqual(task.status, "success")
            self.assertEqual(task.completion_result["steps"], {"step1": "ok"})

    @patch("apps.tasks.engine.SSHExecutor")
    def test_connectivity_failure_skips_later_phases(self, MockExecutor):
        executor = MagicMock()
        executor.check_connectivity.side_effect = [
            ok("SITOP_CONNECTIVITY_OK"), fail(error="timeout"),
        ]
        executor.execute_script.return_value = ok('{"status": "ok"}')
        executor.__enter__ = MagicMock(return_value=executor)
        executor.__exit__ = MagicMock(return_value=False)
        MockExecutor.return_value = executor

        job = self._create_job()
        engine.run_job(job.id)

        job.refresh_from_db()
        tasks = {t.server.hostname: t for t in job.server_tasks.all()}
        self.assertEqual(tasks["s1"].status, "success")
        self.assertEqual(tasks["s2"].status, "failed")
        # s2 failed at connectivity, should have only 1 step log (connectivity)
        self.assertEqual(tasks["s2"].step_logs.count(), 1)

    @patch("apps.tasks.engine.SSHExecutor")
    def test_health_failure_marks_task_failed(self, MockExecutor):
        executor = MagicMock()
        executor.check_connectivity.return_value = ok("SITOP_CONNECTIVITY_OK")
        executor.execute_script.return_value = fail('{"status": "failed"}')
        executor.__enter__ = MagicMock(return_value=executor)
        executor.__exit__ = MagicMock(return_value=False)
        MockExecutor.return_value = executor

        job = self._create_job()
        engine.run_job(job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        for task in job.server_tasks.all():
            self.assertEqual(task.status, "failed")

    @patch("apps.tasks.engine.SSHExecutor")
    def test_init_step_abort_policy(self, MockExecutor):
        executor = MagicMock()
        executor.check_connectivity.return_value = ok("SITOP_CONNECTIVITY_OK")
        # health passes, init fails
        executor.execute_script.side_effect = [
            ok('{"status": "ok"}'), ok('{"status": "ok"}'),
            fail(error="step exploded"), fail(error="step exploded"),
        ]
        executor.__enter__ = MagicMock(return_value=executor)
        executor.__exit__ = MagicMock(return_value=False)
        MockExecutor.return_value = executor

        job = self._create_job()
        engine.run_job(job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        for task in job.server_tasks.all():
            self.assertEqual(task.status, "failed")

    @patch("apps.tasks.engine.SSHExecutor")
    def test_cancel_before_execution(self, MockExecutor):
        executor = MagicMock()
        executor.__enter__ = MagicMock(return_value=executor)
        executor.__exit__ = MagicMock(return_value=False)
        MockExecutor.return_value = executor

        job = self._create_job()
        job.status = "cancelled"
        job.save()

        engine.run_job(job.id)
        job.refresh_from_db()
        self.assertEqual(job.status, "cancelled")


class ScriptVersionTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="t1")
        self.user = User.objects.create_user(
            username="op", password="p", tenant=self.tenant, role="operator"
        )

    def test_version_snapshot_on_create(self):
        script = Script.objects.create(
            tenant=self.tenant, name="s", script_type="init_step",
            content="v1 content", created_by=self.user,
        )
        script.save_version_snapshot()
        self.assertEqual(script.versions.count(), 1)
        self.assertEqual(script.versions.first().content, "v1 content")

    def test_version_bump_keeps_history(self):
        script = Script.objects.create(
            tenant=self.tenant, name="s", script_type="init_step",
            content="v1", created_by=self.user,
        )
        script.save_version_snapshot()
        # Simulate update: bump version, snapshot again
        script.content = "v2"
        script.version = 2
        script.save()
        script.save_version_snapshot()
        self.assertEqual(script.versions.count(), 2)
        self.assertEqual(script.versions.get(version=1).content, "v1")
        self.assertEqual(script.versions.get(version=2).content, "v2")
