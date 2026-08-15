from unittest.mock import patch, MagicMock
import pytest
from apps.executor.ssh import SSHExecutor


@pytest.fixture
def executor():
    return SSHExecutor(connect_timeout=5, exec_timeout=30)


class TestSSHExecutor:
    def test_check_connectivity_no_credential(self, executor):
        server = MagicMock()
        server.resolve_credential.return_value = None
        server.ip = "10.0.0.1"
        result = executor.check_connectivity(server)
        assert result.exit_code == -1
        assert "No SSH credential" in result.error

    def test_check_connectivity_success(self, executor):
        mock_client = MagicMock()
        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stdout.read.return_value = b"SITOP_CONNECTIVITY_OK"
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)
        mock_client.get_transport.return_value.send_ignore.return_value = None

        credential = MagicMock()
        credential.auth_type = "password"
        credential.username = "root"
        credential.get_password.return_value = "pass"

        server = MagicMock()
        server.ip = "10.0.0.1"
        server.ssh_port = 22
        server.resolve_credential.return_value = credential

        with patch.object(executor, "_connect", return_value=mock_client):
            result = executor.check_connectivity(server)

        assert result.exit_code == 0
        assert "SITOP_CONNECTIVITY_OK" in result.output

    def test_execute_command_no_credential(self, executor):
        server = MagicMock()
        server.resolve_credential.return_value = None
        result = executor.execute_command(server, "ls")
        assert result.exit_code == -1

    def test_execute_script_no_credential(self, executor):
        server = MagicMock()
        server.resolve_credential.return_value = None
        result = executor.execute_script(server, "#!/bin/bash\necho hello")
        assert result.exit_code == -1
