"""Tests for the software repository module (apps/repository)."""
import io
import json
import stat
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Tenant, User
from apps.repository.client import (
    RepositoryClient, UploadTooLargeError,
    is_relative_safe, variable_name, get_repo_variables, build_repo_env_block,
    _reset_repo_vars_cache, _repo_vars_cache,
)


class FakeSFTP:
    """Minimal SFTP client fake: in-memory filesystem."""

    def __init__(self):
        self.files = {}   # path -> bytes
        self.dirs = {"/data/initpackages": {}}  # path -> {name: is_dir}
        self.uploads = []  # (path, bytes)

    def seed(self, rel_path, content=b"data", is_dir=False):
        full = f"/data/initpackages/{rel_path}" if rel_path else "/data/initpackages"
        parent = "/".join(full.split("/")[:-1])
        name = full.split("/")[-1]
        self.dirs.setdefault(parent, {})[name] = is_dir
        if not is_dir:
            self.files[full] = content
        return full

    def listdir_attr(self, path):
        attrs = []
        for name, is_dir in self.dirs.get(path, {}).items():
            a = mock.MagicMock()
            a.filename = name
            a.st_mode = stat.S_IFDIR if is_dir else stat.S_IFREG
            a.st_size = len(self.files.get(f"{path}/{name}", b""))
            a.st_mtime = 1700000000.0
            attrs.append(a)
        return attrs

    def listdir(self, path):
        return list(self.dirs.get(path, {}))

    def remove(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        parent, name = path.rsplit("/", 1)
        self.dirs.get(parent, {}).pop(name, None)
        del self.files[path]

    def rmdir(self, path):
        if path not in self.dirs:
            raise FileNotFoundError(path)
        if self.dirs[path]:
            raise OSError(f"directory not empty: {path}")
        parent, name = path.rsplit("/", 1)
        self.dirs.get(parent, {}).pop(name, None)
        del self.dirs[path]

    def stat(self, path):
        if path in self.files:
            a = mock.MagicMock()
            a.st_mode = stat.S_IFREG
            return a
        for dir_path, entries in self.dirs.items():
            if path == dir_path or path in entries:
                a = mock.MagicMock()
                a.st_mode = stat.S_IFDIR
                return a
        raise FileNotFoundError(path)

    def open(self, path, mode="r"):
        if "w" in mode:
            return _FakeWriteFile(self, path)
        if path not in self.files:
            raise FileNotFoundError(path)
        return io.BytesIO(self.files[path])

    def chmod(self, path, mode):
        pass

    def close(self):
        pass


class _FakeWriteFile:
    def __init__(self, sftp, path):
        self.sftp = sftp
        self.path = path
        self.chunks = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.sftp.files[self.path] = b"".join(self.chunks)
        self.sftp.uploads.append((self.path, self.sftp.files[self.path]))

    def write(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.chunks.append(data)


class FakeSSHClient:
    def __init__(self, sftp):
        self.sftp = sftp

    def set_missing_host_key_policy(self, policy):
        pass

    def connect(self, **kwargs):
        pass

    def open_sftp(self):
        return self.sftp

    def close(self):
        pass


def make_client(sftp):
    client = RepositoryClient()
    patcher = mock.patch.object(
        RepositoryClient, "_connect", return_value=FakeSSHClient(sftp),
    )
    patcher.start()
    # 现有 SFTP 测试：让 HTTP 路径失败，强制走 SFTP 回退
    http_patcher = mock.patch(
        "urllib.request.urlopen",
        side_effect=OSError("no http in tests"),
    )
    http_patcher.start()
    return client, [patcher, http_patcher]


class FakeHttpResponse:
    """Mimics urllib response with read()."""

    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


NGINX_JSON = json.dumps([
    {"name": "subdir", "type": "directory", "mtime": "Thu, 13 Aug 2026 01:50:08 GMT"},
    {"name": "app.tar.gz", "type": "file", "mtime": "Thu, 13 Aug 2026 01:50:08 GMT", "size": 12345},
]).encode("utf-8")


class TestListDirHttp(SimpleTestCase):
    @override_settings(REPO_HTTP_URL="http://192.168.1.1:8081/")
    def test_http_parses_nginx_json(self):
        client = RepositoryClient()
        with mock.patch(
            "urllib.request.urlopen", return_value=FakeHttpResponse(NGINX_JSON),
        ) as m:
            items = client.list_dir("")
        self.assertEqual(m.call_args[0][0], "http://192.168.1.1:8081/")
        names = [(i.name, i.is_dir) for i in items]
        self.assertEqual(names, [("subdir", True), ("app.tar.gz", False)])
        self.assertEqual(items[0].size, 0)
        self.assertEqual(items[1].size, 12345)
        self.assertIsInstance(items[1].mtime, float)
        self.assertGreater(items[1].mtime, 0)
        self.assertEqual(items[1].variable, "PKG_APP_TAR_GZ")
        self.assertEqual(items[1].rel_path, "app.tar.gz")

    @override_settings(REPO_HTTP_URL="http://192.168.1.1:8081/")
    def test_http_subdir_url_uses_rel_path(self):
        client = RepositoryClient()
        with mock.patch(
            "urllib.request.urlopen", return_value=FakeHttpResponse(b"[]"),
        ) as m:
            client.list_dir("sub/dir")
        self.assertEqual(m.call_args[0][0], "http://192.168.1.1:8081/sub/dir/")

    @override_settings(REPO_HTTP_URL="http://192.168.1.1:8081/")
    def test_http_empty_dir_returns_empty(self):
        client = RepositoryClient()
        with mock.patch(
            "urllib.request.urlopen", return_value=FakeHttpResponse(b"[]"),
        ) as m:
            items = client.list_dir("")
        self.assertEqual(items, [])

    @override_settings(REPO_HTTP_URL="http://192.168.1.1:8081/")
    def test_http_failure_falls_back_to_sftp(self):
        sftp = FakeSFTP()
        sftp.seed("mysql-8.0.26.tar.gz", b"x" * 10)
        client = RepositoryClient()
        with mock.patch.object(
            RepositoryClient, "_connect", return_value=FakeSSHClient(sftp),
        ), mock.patch(
            "urllib.request.urlopen", side_effect=OSError("http down"),
        ):
            items = client.list_dir("")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, "mysql-8.0.26.tar.gz")


class TestRepositoryDeleteAPI(TestCase):
    """删除接口：权限（仅管理员）+ 参数校验 + 审计。"""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="delete-tenant")
        self.admin = User.objects.create_user(
            username="del-admin", password="x123456", tenant=self.tenant, role="admin")
        self.operator = User.objects.create_user(
            username="del-op", password="x123456", tenant=self.tenant, role="operator")
        self.sftp = FakeSFTP()
        self.sftp.seed("del.tar.gz")
        self.patcher = mock.patch.object(
            RepositoryClient, "_connect", return_value=FakeSSHClient(self.sftp),
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.http_patcher = mock.patch(
            "urllib.request.urlopen", side_effect=OSError("no http in api tests"),
        )
        self.http_patcher.start()
        self.addCleanup(self.http_patcher.stop)
        self.client = APIClient()

    def _auth(self, user):
        token = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def test_admin_can_delete(self):
        self._auth(self.admin)
        resp = self.client.post("/api/repository/files/delete/", {"paths": ["del.tar.gz"]}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["deleted"], ["del.tar.gz"])
        self.assertNotIn("/data/initpackages/del.tar.gz", self.sftp.files)

    def test_operator_forbidden(self):
        self._auth(self.operator)
        resp = self.client.post("/api/repository/files/delete/", {"paths": ["del.tar.gz"]}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("/data/initpackages/del.tar.gz", self.sftp.files)

    def test_unauthenticated_401(self):
        resp = self.client.post("/api/repository/files/delete/", {"paths": ["x"]}, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_empty_paths_rejected(self):
        self._auth(self.admin)
        resp = self.client.post("/api/repository/files/delete/", {"paths": []}, format="json")
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post("/api/repository/files/delete/", {"paths": "x"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_over_limit_rejected(self):
        self._auth(self.admin)
        resp = self.client.post(
            "/api/repository/files/delete/", {"paths": [f"f{i}" for i in range(501)]}, format="json")
        self.assertEqual(resp.status_code, 400)


class TestVariableName(SimpleTestCase):
    def test_basic(self):
        self.assertEqual(variable_name("mysql-8.0.26.tar.gz"), "PKG_MYSQL_8_0_26_TAR_GZ")

    def test_subdir_path(self):
        self.assertEqual(variable_name("pkgs/foo.tar"), "PKG_PKGS_FOO_TAR")

    def test_no_extension(self):
        self.assertEqual(variable_name("myapp"), "PKG_MYAPP")


class TestPathSafety(SimpleTestCase):
    def test_empty_ok(self):
        self.assertTrue(is_relative_safe(""))

    def test_plain_ok(self):
        self.assertTrue(is_relative_safe("sub/dir/file.tar"))

    def test_absolute_rejected(self):
        self.assertFalse(is_relative_safe("/etc/passwd"))

    def test_parent_traversal_rejected(self):
        self.assertFalse(is_relative_safe("../secret"))
        self.assertFalse(is_relative_safe("a/../../b"))

    def test_empty_segment_rejected(self):
        self.assertFalse(is_relative_safe("a//b"))


class TestRepositoryClient(SimpleTestCase):
    @override_settings(REPO_ROOT_PATH="/data/initpackages")
    def test_list_dir(self):
        sftp = FakeSFTP()
        sftp.seed("mysql-8.0.26.tar.gz", b"x" * 10)
        sftp.seed("sub", is_dir=True)
        sftp.seed("sub/foo.tar", b"y")
        client, patcher = make_client(sftp)
        try:
            items = client.list_dir("")
        finally:
            for p in patcher: p.stop()
        names = [i.name for i in items]
        self.assertEqual(names, ["sub", "mysql-8.0.26.tar.gz"])  # 目录在前
        sub = items[0]
        self.assertTrue(sub.is_dir)
        self.assertEqual(sub.rel_path, "sub")
        file_item = items[1]
        self.assertFalse(file_item.is_dir)
        self.assertEqual(file_item.size, 10)
        self.assertEqual(file_item.variable, "PKG_MYSQL_8_0_26_TAR_GZ")

    @override_settings(REPO_ROOT_PATH="/data/initpackages")
    def test_resolve_upload_name_renames_on_collision(self):
        sftp = FakeSFTP()
        sftp.seed("app.tar.gz")
        sftp.seed("app.tar(1).gz")
        client, patcher = make_client(sftp)
        try:
            name = client.resolve_upload_name("", "app.tar.gz")
        finally:
            for p in patcher: p.stop()
        self.assertEqual(name, "app.tar(2).gz")

    @override_settings(REPO_ROOT_PATH="/data/initpackages", REPO_MAX_UPLOAD_SIZE=100)
    def test_upload_too_large(self):
        sftp = FakeSFTP()
        client, patcher = make_client(sftp)
        try:
            with self.assertRaises(UploadTooLargeError):
                client.upload(io.BytesIO(b"x" * 101), "", "big.tar", 101)
        finally:
            for p in patcher: p.stop()

    @override_settings(REPO_ROOT_PATH="/data/initpackages")
    def test_upload_renames_and_reports_variable(self):
        sftp = FakeSFTP()
        sftp.seed("app.tar.gz")
        client, patcher = make_client(sftp)
        try:
            saved_name, variable = client.upload(io.BytesIO(b"data"), "", "app.tar.gz", 4)
        finally:
            for p in patcher: p.stop()
        self.assertEqual(saved_name, "app.tar(1).gz")
        self.assertEqual(variable, "PKG_APP_TAR_1_GZ")
        self.assertTrue(sftp.files["/data/initpackages/app.tar(1).gz"])

    @override_settings(REPO_ROOT_PATH="/data/initpackages")
    def test_upload_same_name_as_dir_rejected(self):
        sftp = FakeSFTP()
        sftp.seed("tools", is_dir=True)
        client, patcher = make_client(sftp)
        try:
            with self.assertRaises(Exception):
                client.upload(io.BytesIO(b"data"), "", "tools", 4)
        finally:
            for p in patcher: p.stop()

    @override_settings(REPO_ROOT_PATH="/data/initpackages")
    def test_upload_rejects_unsafe_filename(self):
        """文件名含 shell 特殊字符（$、引号、反引号等）时拒绝上传，防注入。"""
        sftp = FakeSFTP()
        client, patcher = make_client(sftp)
        try:
            for bad_name in [
                'mysql"$(touch /tmp/pwned)".tar',
                "a`id`.tar",
                "a; rm -rf /",
                "sp ace.tar",
            ]:
                with self.assertRaises(Exception, msg=bad_name):
                    client.upload(io.BytesIO(b"data"), "", bad_name, 4)
        finally:
            for p in patcher: p.stop()

    @override_settings(REPO_ROOT_PATH="/data/initpackages")
    def test_delete_file_and_dir(self):
        """删除文件与递归删除目录。"""
        sftp = FakeSFTP()
        sftp.seed("app.tar.gz")
        sftp.seed("sub/inner.txt")
        client, patcher = make_client(sftp)
        try:
            result = client.delete(["app.tar.gz", "sub"])
        finally:
            for p in patcher: p.stop()
        self.assertEqual(result["deleted"], ["app.tar.gz", "sub"])
        self.assertEqual(result["errors"], [])
        self.assertNotIn("/data/initpackages/app.tar.gz", sftp.files)
        self.assertNotIn("/data/initpackages/sub", sftp.dirs)

    @override_settings(REPO_ROOT_PATH="/data/initpackages")
    def test_delete_root_rejected(self):
        """拒绝删除仓库根目录。"""
        sftp = FakeSFTP()
        sftp.seed("keep.tar.gz")
        client, patcher = make_client(sftp)
        try:
            result = client.delete([""])
        finally:
            for p in patcher: p.stop()
        self.assertEqual(result["deleted"], [])
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("路径为空", result["errors"][0]["error"])
        self.assertIn("/data/initpackages/keep.tar.gz", sftp.files)

    @override_settings(REPO_ROOT_PATH="/data/initpackages")
    def test_delete_partial_failure_continues(self):
        """批量删除部分失败不中断，返回错误明细。"""
        sftp = FakeSFTP()
        sftp.seed("ok.tar.gz")
        client, patcher = make_client(sftp)
        try:
            result = client.delete(["ok.tar.gz", "missing.tar.gz"])
        finally:
            for p in patcher: p.stop()
        self.assertEqual(result["deleted"], ["ok.tar.gz"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("missing.tar.gz", result["errors"][0]["path"])
        self.assertNotIn("/data/initpackages/ok.tar.gz", sftp.files)

    @override_settings(REPO_ROOT_PATH="/data/initpackages")
    def test_delete_resets_vars_cache(self):
        """删除成功后重置变量缓存（脚本变量立即生效）。"""
        _reset_repo_vars_cache()
        sftp = FakeSFTP()
        sftp.seed("a.tar.gz")
        client, patcher = make_client(sftp)
        try:
            client.delete(["a.tar.gz"])
        finally:
            for p in patcher: p.stop()
        # 缓存已重置：下次获取重新扫描（此处验证无缓存残留）
        self.assertIsNone(_repo_vars_cache)

    @override_settings(REPO_ROOT_PATH="/data/initpackages")
    def test_upload_accepts_chinese_filename(self):
        """中文文件名上传允许（如 补丁包_v1.0.tar.gz）。"""
        sftp = FakeSFTP()
        client, patcher = make_client(sftp)
        try:
            saved_name, variable = client.upload(io.BytesIO(b"data"), "", "补丁包_v1.0.tar.gz", 4)
        finally:
            for p in patcher: p.stop()
        self.assertEqual(saved_name, "补丁包_v1.0.tar.gz")
        self.assertEqual(variable, "PKG_Z_V1_0_TAR_GZ")
        self.assertTrue(sftp.files["/data/initpackages/补丁包_v1.0.tar.gz"])

    @override_settings(REPO_ROOT_PATH="/data/initpackages", REPO_HTTP_URL="http://192.168.1.1:8081/")
    def test_get_repo_variables(self):
        _reset_repo_vars_cache()
        self.addCleanup(_reset_repo_vars_cache)
        sftp = FakeSFTP()
        sftp.seed("mysql-8.0.26.tar.gz", b"x")
        sftp.seed("sub", is_dir=True)
        sftp.seed("sub/foo.tar", b"y")
        with mock.patch.object(RepositoryClient, "_connect", return_value=FakeSSHClient(sftp)):
            variables = get_repo_variables()
        self.assertEqual(variables, {
            "PKG_MYSQL_8_0_26_TAR_GZ": "http://192.168.1.1:8081/mysql-8.0.26.tar.gz",
            "PKG_SUB_FOO_TAR": "http://192.168.1.1:8081/sub/foo.tar",
        })

    @override_settings(REPO_SSH_HOST="10.255.255.254", REPO_SSH_USER="root")
    def test_get_repo_variables_returns_empty_on_failure(self):
        _reset_repo_vars_cache()
        self.addCleanup(_reset_repo_vars_cache)
        with mock.patch.object(
            RepositoryClient, "_connect",
            side_effect=Exception("connection refused"),
        ):
            self.assertEqual(get_repo_variables(), {})

    @override_settings(REPO_ROOT_PATH="/data/initpackages", REPO_HTTP_URL="http://192.168.1.1:8081/")
    def test_get_repo_variables_cached_within_ttl(self):
        _reset_repo_vars_cache()
        self.addCleanup(_reset_repo_vars_cache)
        sftp = FakeSFTP()
        sftp.seed("a.tar", b"x")
        with mock.patch.object(RepositoryClient, "_connect", return_value=FakeSSHClient(sftp)):
            first = get_repo_variables()
            # 第二次调用应命中缓存，不再连接
            with mock.patch.object(RepositoryClient, "_connect", side_effect=Exception("should not connect")):
                second = get_repo_variables()
        self.assertEqual(first, second)
        self.assertIn("PKG_A_TAR", second)

    @override_settings(REPO_HTTP_URL="http://192.168.1.1:8081/")
    def test_build_repo_env_block_shell(self):
        with mock.patch("apps.repository.client.get_repo_variables", return_value={
            "PKG_MYSQL_8_0_26_TAR_GZ": "http://192.168.1.1:8081/mysql-8.0.26.tar.gz",
        }):
            block = build_repo_env_block("shell")
        self.assertIn(
            "export PKG_MYSQL_8_0_26_TAR_GZ='http://192.168.1.1:8081/mysql-8.0.26.tar.gz'",
            block,
        )

    @override_settings(REPO_HTTP_URL="http://192.168.1.1:8081/")
    def test_build_repo_env_block_shell_escapes_special_chars(self):
        """注入块对值做 shell 单引号包裹，命令替换/变量展开不生效（防命令注入）。"""
        malicious = 'http://192.168.1.1:8081/a"$(touch /tmp/pwned)".tar'
        with mock.patch("apps.repository.client.get_repo_variables", return_value={
            "PKG_BAD": malicious,
        }):
            block = build_repo_env_block("shell")
        line = [l for l in block.splitlines() if l.startswith("export PKG_BAD")][0]
        # 单引号包裹整个值：内容原样保留，$(...) 不会执行
        self.assertEqual(line, f"export PKG_BAD='{malicious}'")

    @override_settings(REPO_HTTP_URL="http://192.168.1.1:8081/")
    def test_build_repo_env_block_python_uses_repr(self):
        """python 注入块使用 repr 序列化，特殊字符不破坏语法。"""
        malicious = 'http://x/a"$(touch /tmp/pwned)".tar'
        with mock.patch("apps.repository.client.get_repo_variables", return_value={
            "PKG_BAD": malicious,
        }):
            block = build_repo_env_block("python")
        self.assertIn("os.environ.setdefault('PKG_BAD', " + repr(malicious) + ")", block)
        compile(block, "<injected>", "exec")  # 必须是合法 Python

    @override_settings(REPO_ROOT_PATH="/data/initpackages", REPO_HTTP_URL="http://192.168.1.1:8081/")
    def test_get_repo_variables_urlencodes_filenames(self):
        """变量值 URL 编码文件名特殊字符（空格/引号等），防止注入。"""
        _reset_repo_vars_cache()
        self.addCleanup(_reset_repo_vars_cache)
        sftp = FakeSFTP()
        sftp.seed('my file(1).tar', b"x")
        with mock.patch.object(RepositoryClient, "_connect", return_value=FakeSSHClient(sftp)):
            variables = get_repo_variables()
        self.assertEqual(
            variables["PKG_MY_FILE_1_TAR"],
            "http://192.168.1.1:8081/my%20file(1).tar",
        )

    @override_settings(REPO_HTTP_URL="http://192.168.1.1:8081/")
    def test_build_repo_env_block_python(self):
        with mock.patch("apps.repository.client.get_repo_variables", return_value={
            "PKG_MYSQL_8_0_26_TAR_GZ": "http://192.168.1.1:8081/mysql-8.0.26.tar.gz",
        }):
            block = build_repo_env_block("python")
        self.assertIn(
            "os.environ.setdefault('PKG_MYSQL_8_0_26_TAR_GZ', 'http://192.168.1.1:8081/mysql-8.0.26.tar.gz')",
            block,
        )

    def test_build_repo_env_block_empty_on_failure(self):
        with mock.patch("apps.repository.client.get_repo_variables", return_value={}):
            self.assertEqual(build_repo_env_block("shell"), "")


class TestRepositoryAPI(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="仓库租户")
        self.admin = User.objects.create_user(
            username="admin2", password="testpass123", tenant=self.tenant, role="admin",
        )
        self.viewer = User.objects.create_user(
            username="viewer2", password="testpass123", tenant=self.tenant, role="viewer",
        )
        self.sftp = FakeSFTP()
        self.sftp.seed("mysql-8.0.26.tar.gz", b"x" * 10)
        self.patcher = mock.patch.object(
            RepositoryClient, "_connect", return_value=FakeSSHClient(self.sftp),
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        # 列表走 SFTP 回退（HTTP 路径在 API 测试中禁用）
        self.http_patcher = mock.patch(
            "urllib.request.urlopen", side_effect=OSError("no http in api tests"),
        )
        self.http_patcher.start()
        self.addCleanup(self.http_patcher.stop)
        self.client = APIClient()
        token = RefreshToken.for_user(self.admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def test_list_files(self):
        resp = self.client.get("/api/repository/files/")
        self.assertEqual(resp.status_code, 200)
        items = resp.data["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "mysql-8.0.26.tar.gz")
        self.assertEqual(items[0]["variable"], "PKG_MYSQL_8_0_26_TAR_GZ")
        self.assertEqual(
            items[0]["http_url"], "http://192.168.1.1:8081/mysql-8.0.26.tar.gz",
        )

    def test_list_files_requires_auth(self):
        resp = APIClient().get("/api/repository/files/")
        self.assertEqual(resp.status_code, 401)

    def test_list_files_rejects_traversal(self):
        resp = self.client.get("/api/repository/files/", {"path": "../secret"})
        self.assertEqual(resp.status_code, 400)

    def test_upload_requires_operator(self):
        viewer_client = APIClient()
        token = RefreshToken.for_user(self.viewer)
        viewer_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        resp = viewer_client.post(
            "/api/repository/files/upload/",
            {"files": [SimpleUploadedFile("v.tar", b"data")]},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 403)

    def test_upload_creates_file_and_audit(self):
        resp = self.client.post(
            "/api/repository/files/upload/",
            {"files": [SimpleUploadedFile("hello.tar", b"hello")]},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["results"][0]["saved_name"], "hello.tar")
        self.assertEqual(resp.data["results"][0]["variable"], "PKG_HELLO_TAR")
        self.assertTrue(self.sftp.files["/data/initpackages/hello.tar"])
        from apps.accounts.models import AuditLog
        self.assertEqual(AuditLog.objects.filter(action="repository.upload").count(), 1)

    @override_settings(REPO_MAX_UPLOAD_SIZE=3)
    def test_upload_all_failed_returns_400(self):
        resp = self.client.post(
            "/api/repository/files/upload/",
            {"files": [SimpleUploadedFile("big.tar", b"x" * 10)]},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["results"], [])
        self.assertEqual(len(resp.data["errors"]), 1)

    def test_download_streams_file(self):
        resp = self.client.get(
            "/api/repository/files/download/", {"path": "mysql-8.0.26.tar.gz"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b"".join(resp.streaming_content), b"x" * 10)
        self.assertIn("attachment", resp["Content-Disposition"])

    def test_download_missing_returns_404(self):
        resp = self.client.get(
            "/api/repository/files/download/", {"path": "nope.tar"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_delete_endpoint_does_not_exist(self):
        # 用 resolve 验证删除路由不存在（避免 Django debug 404 页面在 Python 3.14 下的渲染兼容问题）
        from django.urls import resolve, Resolver404
        with self.assertRaises(Resolver404):
            resolve("/api/repository/files/mysql-8.0.26.tar.gz/")


class TestEnvInjection(TestCase):
    """execute_script 在脚本头部自动注入仓库变量块。"""

    def _run_script(self, content, language="shell"):
        from apps.executor.ssh import SSHExecutor

        fake_sftp = FakeSFTP()

        class FakeClientWithSFTP:
            def open_sftp(self):
                return fake_sftp

            def exec_command(self, command, timeout=None):
                stdout = mock.MagicMock()
                stdout.channel = mock.MagicMock()
                stdout.channel.recv_exit_status.return_value = 0
                stdout.read.return_value = b""
                stderr = mock.MagicMock()
                stderr.read.return_value = b""
                return mock.MagicMock(), stdout, stderr

        executor = SSHExecutor()
        server = mock.MagicMock()
        server.resolve_credential.return_value = mock.MagicMock()
        with mock.patch.object(
            executor, "_execute_with_retry",
            side_effect=lambda server, cred, func: func(FakeClientWithSFTP()),
        ):
            result = executor.execute_script(server, content, language)
        return result, fake_sftp

    def test_execute_script_injects_env_block(self):
        with mock.patch(
            "apps.repository.client.build_repo_env_block",
            return_value="# ==== SITOP 软件仓库变量（自动注入，可在脚本中直接使用）====\n"
            'export PKG_MYSQL_8_0_26_TAR_GZ="http://192.168.1.1:8081/mysql-8.0.26.tar.gz"',
        ):
            result, fake_sftp = self._run_script("echo hi\n")

        self.assertEqual(result.exit_code, 0)
        written = fake_sftp.uploads[-1][1]
        self.assertTrue(written.startswith("# ==== SITOP 软件仓库变量".encode()))
        self.assertIn(b"export PKG_MYSQL_8_0_26_TAR_GZ", written)
        self.assertTrue(written.endswith(b"echo hi\n"))

    def test_execute_script_without_env_block(self):
        with mock.patch("apps.repository.client.build_repo_env_block", return_value=""):
            result, fake_sftp = self._run_script("echo hi\n")

        self.assertEqual(result.exit_code, 0)
        written = fake_sftp.uploads[-1][1]
        self.assertEqual(written, b"echo hi\n")

    def test_execute_python_script_injects_at_end(self):
        """python 脚本注入块追加到末尾，避免破坏文件头部的编码声明/__future__ 导入。"""
        with mock.patch(
            "apps.repository.client.build_repo_env_block",
            return_value="import os\n"
            "os.environ.setdefault('PKG_MYSQL_8_0_26_TAR_GZ', 'http://192.168.1.1:8081/mysql-8.0.26.tar.gz')",
        ):
            result, fake_sftp = self._run_script("# -*- coding: utf-8 -*-\nprint('hi')\n", "python")

        self.assertEqual(result.exit_code, 0)
        written = fake_sftp.uploads[-1][1]
        # 头部保持编码声明
        self.assertTrue(written.startswith(b"# -*- coding: utf-8 -*-"))
        # 注入块在末尾（完整内容）
        self.assertTrue(written.endswith(
            b"os.environ.setdefault('PKG_MYSQL_8_0_26_TAR_GZ', "
            b"'http://192.168.1.1:8081/mysql-8.0.26.tar.gz')"
        ), written)
