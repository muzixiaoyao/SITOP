import io
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import paramiko

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    exit_code: int
    output: str
    error: str


class SSHExecutor:
    def __init__(self, connect_timeout: int = 15, exec_timeout: int = 600, max_retries: int = 2):
        self.connect_timeout = connect_timeout
        self.exec_timeout = exec_timeout
        self.max_retries = max_retries
        self._client: Optional[paramiko.SSHClient] = None
        self._current_server = None
        self._current_credential = None

    def _get_client(self, server, credential) -> paramiko.SSHClient:
        """Get or create a reusable SSH client."""
        if (self._client is not None and
            self._current_server == server and
            self._current_credential == credential):
            try:
                self._client.get_transport().send_ignore()
                return self._client
            except Exception:
                self._close_client()

        self._close_client()
        self._client = self._connect(server, credential)
        self._current_server = server
        self._current_credential = credential
        return self._client

    def _close_client(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
            self._current_server = None
            self._current_credential = None

    def close(self):
        """Explicitly close the connection."""
        self._close_client()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _execute_with_retry(self, server, credential, func):
        """Execute a function with retry logic for transient SSH failures."""
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                client = self._get_client(server, credential)
                return func(client)
            except (paramiko.ssh_exception.SSHException, EOFError, OSError) as e:
                last_error = e
                logger.warning("SSH attempt %d/%d failed for %s: %s", attempt + 1, self.max_retries + 1, server.ip, e)
                self._close_client()
                if attempt < self.max_retries:
                    time.sleep(1 * (attempt + 1))
            except Exception as e:
                last_error = e
                logger.error("Non-retryable error on %s: %s", server.ip, e)
                break
        return ExecutionResult(-1, "", str(last_error) if last_error else "Unknown error")

    def check_connectivity(self, server) -> ExecutionResult:
        credential = server.resolve_credential()
        if not credential:
            return ExecutionResult(-1, "", "No SSH credential configured for this server")

        def _check(client):
            stdin, stdout, stderr = client.exec_command("echo SITOP_CONNECTIVITY_OK", timeout=10)
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8", errors="replace").strip()
            return ExecutionResult(exit_code, output, "")

        return self._execute_with_retry(server, credential, _check)

    def execute_command(self, server, command: str) -> ExecutionResult:
        credential = server.resolve_credential()
        if not credential:
            return ExecutionResult(-1, "", "No SSH credential configured")

        def _exec(client):
            stdin, stdout, stderr = client.exec_command(command, timeout=self.exec_timeout)
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8", errors="replace")
            error = stderr.read().decode("utf-8", errors="replace")
            return ExecutionResult(exit_code, output, error)

        return self._execute_with_retry(server, credential, _exec)

    def execute_script(self, server, script_content: str, language: str = "shell") -> ExecutionResult:
        credential = server.resolve_credential()
        if not credential:
            return ExecutionResult(-1, "", "No SSH credential configured")

        # 自动注入软件仓库变量块（仓库不可达时返回空串，不阻塞执行）
        # shell：置于头部（export 需在命令前）；python：置于末尾（避免破坏编码声明/__future__ 导入）
        from apps.repository.client import build_repo_env_block
        env_block = build_repo_env_block(language)
        if env_block:
            if language == "python":
                script_content = f"{script_content}\n\n{env_block}"
            else:
                script_content = f"{env_block}\n\n{script_content}"

        remote_path = f"/tmp/sitop_{uuid.uuid4().hex}.sh"
        interpreter = "bash" if language == "shell" else "python3"

        def _exec_script(client):
            sftp = client.open_sftp()
            try:
                with sftp.open(remote_path, "w") as f:
                    f.write(script_content)
                sftp.chmod(remote_path, 0o755)
                stdin, stdout, stderr = client.exec_command(
                    f"{interpreter} {remote_path}", timeout=self.exec_timeout,
                )
                exit_code = stdout.channel.recv_exit_status()
                output = stdout.read().decode("utf-8", errors="replace")
                error = stderr.read().decode("utf-8", errors="replace")
                return ExecutionResult(exit_code, output, error)
            finally:
                try:
                    sftp.remove(remote_path)
                except Exception:
                    pass
                sftp.close()

        return self._execute_with_retry(server, credential, _exec_script)

    def _connect(self, server, credential):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs = {
            "hostname": server.ip,
            "port": server.ssh_port,
            "username": credential.username,
            "timeout": self.connect_timeout,
            "banner_timeout": self.connect_timeout,
        }
        if credential.auth_type == "password":
            connect_kwargs["password"] = credential.get_password()
        elif credential.auth_type == "key":
            key_content = credential.get_private_key()
            if key_content:
                key_file = io.StringIO(key_content)
                passphrase = credential.passphrase
                if passphrase:
                    from apps.accounts.crypto import decrypt_value
                    passphrase = decrypt_value(bytes(passphrase))
                try:
                    pkey = paramiko.Ed25519Key.from_private_key(key_file, password=passphrase)
                except Exception:
                    key_file.seek(0)
                    try:
                        pkey = paramiko.RSAKey.from_private_key(key_file, password=passphrase)
                    except Exception:
                        key_file.seek(0)
                        pkey = paramiko.ECDSAKey.from_private_key(key_file, password=passphrase)
                connect_kwargs["pkey"] = pkey

        # Jump host support (M4): tunnel through the bastion via direct-tcpip
        jump_host = getattr(credential, "jump_host", "") or ""
        if jump_host:
            connect_kwargs["sock"] = self._open_jump_channel(server, credential)

        client.connect(**connect_kwargs)
        return client

    def _open_jump_channel(self, server, credential):
        """Open a direct-tcpip channel through the jump host to the target."""
        jump_client = paramiko.SSHClient()
        jump_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        jump_kwargs = {
            "hostname": credential.jump_host,
            "port": getattr(credential, "jump_port", 22) or 22,
            "username": getattr(credential, "jump_username", "") or credential.username,
            "timeout": self.connect_timeout,
            "banner_timeout": self.connect_timeout,
        }
        # Reuse the same credential material for the jump hop
        if credential.auth_type == "password":
            jump_kwargs["password"] = credential.get_password()
        elif credential.auth_type == "key" and "pkey" not in jump_kwargs:
            key_content = credential.get_private_key()
            if key_content:
                jump_kwargs["password"] = None
                jump_kwargs["key_filename"] = None
                # Load key via StringIO (same fallback chain as main connect)
                key_file = io.StringIO(key_content)
                try:
                    jump_kwargs["pkey"] = paramiko.Ed25519Key.from_private_key(key_file)
                except Exception:
                    key_file.seek(0)
                    try:
                        jump_kwargs["pkey"] = paramiko.RSAKey.from_private_key(key_file)
                    except Exception:
                        key_file.seek(0)
                        jump_kwargs["pkey"] = paramiko.ECDSAKey.from_private_key(key_file)
                jump_kwargs.pop("password", None)
                jump_kwargs.pop("key_filename", None)
        jump_client.connect(**jump_kwargs)
        transport = jump_client.get_transport()
        channel = transport.open_channel(
            "direct-tcpip",
            (server.ip, server.ssh_port),
            ("127.0.0.1", 0),
        )
        # Keep a reference so the jump client isn't garbage-collected
        channel._sitop_jump_client = jump_client  # type: ignore[attr-defined]
        return channel
