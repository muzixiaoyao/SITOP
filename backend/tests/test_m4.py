from unittest.mock import patch, MagicMock
from django.test import TestCase

from apps.accounts.models import Tenant, User, SSHCredential
from apps.servers.models import ServerGroup, Server
from apps.scripts.models import Script
from apps.scripts.signing import compute_signature, verify_signature
from apps.executor.ssh import ExecutionResult
from apps.tasks.models import InitTemplate, TemplateStep, InitJob
from apps.tasks import engine


class SigningTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="t1")
        self.user = User.objects.create_user(username="u", password="p", tenant=self.tenant)

    def test_signature_auto_computed_on_save(self):
        script = Script.objects.create(
            tenant=self.tenant, name="s", script_type="init_step",
            content="echo hi", created_by=self.user,
        )
        self.assertEqual(script.signature, compute_signature("echo hi"))
        self.assertTrue(script.verify_signature())

    def test_tampered_content_fails_verification(self):
        script = Script.objects.create(
            tenant=self.tenant, name="s", script_type="init_step",
            content="echo hi", created_by=self.user,
        )
        # Simulate direct DB tampering (bypass save)
        Script.objects.filter(id=script.id).update(content="rm -rf /")
        script.refresh_from_db()
        self.assertFalse(script.verify_signature())

    def test_verify_signature_helper(self):
        sig = compute_signature("hello world")
        self.assertTrue(verify_signature("hello world", sig))
        self.assertFalse(verify_signature("hello world", "bad-signature"))


class WebhookTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="t1")
        self.user = User.objects.create_user(username="u", password="p", tenant=self.tenant)
        self.group = ServerGroup.objects.create(tenant=self.tenant, name="g", created_by=self.user)
        self.server = Server.objects.create(hostname="s1", ip="10.0.0.1")
        self.server.groups.add(self.group)

    @patch("apps.tasks.webhooks.requests.post")
    def test_webhook_payload_on_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        template = InitTemplate.objects.create(
            tenant=self.tenant, name="tpl", created_by=self.user,
            webhook_url="http://example.com/hook",
        )
        job = InitJob.objects.create(
            tenant=self.tenant, template=template, group=self.group,
            triggered_by=self.user, status="success",
            summary={"total": 1, "success": 1, "failed": 0},
        )
        from apps.tasks.webhooks import notify_job_finished
        notify_job_finished(job)

        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["job_id"], str(job.id))
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["success_count"], 1)

    @patch("apps.tasks.webhooks.requests.post")
    def test_webhook_failure_does_not_raise(self, mock_post):
        mock_post.side_effect = Exception("connection refused")
        template = InitTemplate.objects.create(
            tenant=self.tenant, name="tpl", created_by=self.user,
            webhook_url="http://example.com/hook",
        )
        job = InitJob.objects.create(
            tenant=self.tenant, template=template, group=self.group,
            triggered_by=self.user, status="failed",
        )
        from apps.tasks.webhooks import notify_job_finished
        # Should not raise
        notify_job_finished(job)


class PatrolTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="t1")
        self.user = User.objects.create_user(username="u", password="p", tenant=self.tenant)
        self.group = ServerGroup.objects.create(tenant=self.tenant, name="g", created_by=self.user)
        self.server = Server.objects.create(hostname="s1", ip="10.0.0.1")
        self.server.groups.add(self.group)

    @patch("apps.executor.ssh.SSHExecutor")
    def test_patrol_updates_connectivity(self, MockExecutor):
        executor = MagicMock()
        executor.check_connectivity.return_value = ExecutionResult(0, "SITOP_CONNECTIVITY_OK", "")
        executor.__enter__ = MagicMock(return_value=executor)
        executor.__exit__ = MagicMock(return_value=False)
        MockExecutor.return_value = executor

        from apps.servers.patrol import patrol_group
        counts = patrol_group(self.group)
        self.assertEqual(counts, {"total": 1, "success": 1, "failed": 0})
        self.server.refresh_from_db()
        self.assertEqual(self.server.connectivity_status, "success")

    @patch("apps.executor.ssh.SSHExecutor")
    def test_patrol_failure_marks_failed(self, MockExecutor):
        executor = MagicMock()
        executor.check_connectivity.return_value = ExecutionResult(-1, "", "timeout")
        executor.__enter__ = MagicMock(return_value=executor)
        executor.__exit__ = MagicMock(return_value=False)
        MockExecutor.return_value = executor

        from apps.servers.patrol import patrol_group
        counts = patrol_group(self.group)
        self.assertEqual(counts["failed"], 1)
        self.server.refresh_from_db()
        self.assertEqual(self.server.connectivity_status, "failed")


class JumpHostTestCase(TestCase):
    def test_proxy_channel_created_when_jump_configured(self):
        from apps.executor.ssh import SSHExecutor

        credential = MagicMock()
        credential.jump_host = "bastion.example.com"
        credential.jump_port = 22
        credential.jump_username = "jumpuser"
        credential.auth_type = "password"
        credential.username = "root"
        credential.get_password.return_value = "pw"

        server = MagicMock()
        server.ip = "10.0.0.5"
        server.ssh_port = 22

        executor = SSHExecutor(connect_timeout=5)
        with patch("apps.executor.ssh.paramiko.SSHClient") as MockClient:
            jump_client = MagicMock()
            MockClient.return_value = jump_client
            channel = executor._open_jump_channel(server, credential)

        # Jump client connected to the bastion
        connect_kwargs = jump_client.connect.call_args.kwargs
        self.assertEqual(connect_kwargs["hostname"], "bastion.example.com")
        self.assertEqual(connect_kwargs["username"], "jumpuser")
        # Channel opened to the target through the bastion
        jump_client.get_transport.return_value.open_channel.assert_called_once_with(
            "direct-tcpip", ("10.0.0.5", 22), ("127.0.0.1", 0),
        )

    def test_no_jump_when_field_empty(self):
        from apps.executor.ssh import SSHExecutor

        credential = MagicMock()
        credential.jump_host = ""
        credential.auth_type = "password"
        credential.username = "root"
        credential.get_password.return_value = "pw"

        server = MagicMock()
        server.ip = "10.0.0.5"
        server.ssh_port = 22

        executor = SSHExecutor(connect_timeout=5)
        with patch("apps.executor.ssh.paramiko.SSHClient") as MockClient:
            client = MagicMock()
            MockClient.return_value = client
            executor._connect(server, credential)
        connect_kwargs = client.connect.call_args.kwargs
        self.assertNotIn("sock", connect_kwargs)


class SignatureEngineTestCase(TestCase):
    """Engine refuses to execute tampered scripts."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="t1")
        self.user = User.objects.create_user(username="u", password="p", tenant=self.tenant)
        self.group = ServerGroup.objects.create(tenant=self.tenant, name="g", created_by=self.user)
        self.server = Server.objects.create(hostname="s1", ip="10.0.0.1")
        self.server.groups.add(self.group)
        self.step = Script.objects.create(
            tenant=self.tenant, name="step", script_type="init_step",
            content="echo ok", created_by=self.user,
        )
        self.template = InitTemplate.objects.create(
            tenant=self.tenant, name="tpl", created_by=self.user,
        )
        TemplateStep.objects.create(template=self.template, step_order=1, script=self.step)

    @patch("apps.tasks.engine.SSHExecutor")
    def test_tampered_script_refused(self, MockExecutor):
        executor = MagicMock()
        executor.check_connectivity.return_value = ExecutionResult(0, "SITOP_CONNECTIVITY_OK", "")
        executor.__enter__ = MagicMock(return_value=executor)
        executor.__exit__ = MagicMock(return_value=False)
        MockExecutor.return_value = executor

        # Tamper without triggering save() (bypasses auto re-sign)
        Script.objects.filter(id=self.step.id).update(content="echo hacked")

        job = InitJob.objects.create(
            tenant=self.tenant, template=self.template, group=self.group,
            triggered_by=self.user, status="pending",
        )
        engine.run_job(job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        # The tampered script was never sent to the executor
        executor.execute_script.assert_not_called()
        task = job.server_tasks.first()
        logs = list(task.step_logs.all())
        self.assertTrue(any("signature" in (l.error or "") for l in logs))
