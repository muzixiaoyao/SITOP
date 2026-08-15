"""Software repository SFTP client.

操作 192.168.1.1:/data/initpackages（免密公钥认证）。
无 DB 模型：文件列表实时从 SFTP 读取。
"""
import json
import logging
import re
import stat
import time
from dataclasses import dataclass
from urllib.parse import quote

import paramiko
from django.conf import settings

logger = logging.getLogger(__name__)

# 上传文件名白名单：字母数字 ._- 与中文（防 shell 注入与路径穿越，同时支持中文文件名）
SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._\-\u4e00-\u9fff]+$")


class RepositoryError(Exception):
    """Base error for repository operations."""


class UploadTooLargeError(RepositoryError):
    pass


class PathNotAllowedError(RepositoryError):
    pass


@dataclass
class RepoItem:
    name: str
    rel_path: str  # 相对仓库根目录的完整路径
    is_dir: bool
    size: int
    mtime: float

    @property
    def variable(self) -> str:
        return variable_name(self.rel_path)


def variable_name(filename: str) -> str:
    """生成脚本变量名：mysql-8.0.26.tar.gz -> PKG_MYSQL_8_0_26_TAR_GZ。
    中文等非 ASCII 段映射为 Z 标记（shell 变量名不允许非 ASCII，避免变量名非法）。"""
    name = re.sub(r"[\u4e00-\u9fff]+", "Z", filename)
    name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return f"PKG_{name}"


def is_relative_safe(rel_path: str) -> bool:
    """拒绝绝对路径、'..' 段与空段。空字符串（根目录）合法。"""
    if not rel_path:
        return True
    if rel_path.startswith("/"):
        return False
    return all(part not in ("", "..") for part in rel_path.split("/"))


class RepositoryClient:
    """Paramiko SFTP 客户端（免密公钥认证，连接超时 10s）。"""

    def __init__(self):
        self.host = settings.REPO_SSH_HOST
        self.port = settings.REPO_SSH_PORT
        self.username = settings.REPO_SSH_USER
        self.root = settings.REPO_ROOT_PATH.rstrip("/")
        self.connect_timeout = 10

    def _connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        known_hosts = settings.REPO_KNOWN_HOSTS
        if known_hosts:
            # 生产建议配置 known_hosts 并启用严格主机密钥校验，防 MITM
            client.load_host_keys(known_hosts)
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs = {
            "hostname": self.host,
            "port": self.port,
            "username": self.username,
            "timeout": self.connect_timeout,
            "banner_timeout": self.connect_timeout,
        }
        # 显式指定私钥时禁用 agent/默认密钥扫描，保证确定性（paramiko 不解析 ~/.ssh/config）
        key_path = settings.REPO_SSH_KEY_PATH
        if key_path:
            connect_kwargs["key_filename"] = key_path
            connect_kwargs["allow_agent"] = False
            connect_kwargs["look_for_keys"] = False
        client.connect(**connect_kwargs)
        return client

    def _resolve(self, rel_path: str) -> str:
        if not is_relative_safe(rel_path):
            raise PathNotAllowedError(f"非法路径: {rel_path}")
        return f"{self.root}/{rel_path}" if rel_path else self.root

    def list_dir(self, rel_path: str = "") -> list:
        """列出目录内容：优先 HTTP（nginx JSON，~0.3s），失败回退 SFTP。"""
        try:
            return self._list_dir_http(rel_path)
        except Exception as e:
            logger.warning("HTTP 列目录失败，回退 SFTP: %s", e)
            return self._list_dir_sftp(rel_path)

    def _list_dir_sftp(self, rel_path: str = "") -> list:
        """SFTP 列目录（回退路径）。"""
        full = self._resolve(rel_path)
        client = self._connect()
        try:
            sftp = client.open_sftp()
            try:
                items = []
                for attr in sftp.listdir_attr(full):
                    name = attr.filename
                    items.append(RepoItem(
                        name=name,
                        rel_path=f"{rel_path}/{name}" if rel_path else name,
                        is_dir=stat.S_ISDIR(attr.st_mode),
                        size=attr.st_size,
                        mtime=attr.st_mtime,
                    ))
                items.sort(key=lambda i: (not i.is_dir, i.name.lower()))
                return items
            finally:
                sftp.close()
        finally:
            client.close()

    def _list_dir_http(self, rel_path: str = "") -> list:
        """HTTP 列目录：请求 nginx autoindex JSON 并解析（实测格式：RFC1123 mtime、数字 size、无 ../ 项）。"""
        import urllib.request
        from email.utils import parsedate_to_datetime

        base = settings.REPO_HTTP_URL.rstrip("/")
        url = f"{base}/{rel_path}/" if rel_path else f"{base}/"
        with urllib.request.urlopen(url, timeout=5) as resp:
            raw = json.loads(resp.read().decode("utf-8"))

        items = []
        for entry in raw:
            name = entry.get("name", "")
            if name in ("", "../"):
                continue
            is_dir = entry.get("type") == "directory"
            size = entry.get("size") or 0
            try:
                size = int(size)
            except (TypeError, ValueError):
                size = 0
            mtime_raw = entry.get("mtime", "")
            try:
                mtime = parsedate_to_datetime(mtime_raw).timestamp()
            except (TypeError, ValueError):
                mtime = 0.0
            rel = f"{rel_path}/{name}" if rel_path else name
            items.append(RepoItem(
                name=name,
                rel_path=rel,
                is_dir=is_dir,
                size=size,
                mtime=mtime,
            ))
        items.sort(key=lambda i: (not i.is_dir, i.name.lower()))
        return items

    def list_all(self) -> list:
        """递归列出根目录下所有文件（不含目录项）。"""
        result = []
        client = self._connect()
        try:
            sftp = client.open_sftp()
            try:
                self._walk(sftp, self.root, "", result)
            finally:
                sftp.close()
        finally:
            client.close()
        return result

    def _walk(self, sftp, full_dir, rel_dir, result):
        for attr in sftp.listdir_attr(full_dir):
            name = attr.filename
            rel_path = f"{rel_dir}/{name}" if rel_dir else name
            if stat.S_ISDIR(attr.st_mode):
                self._walk(sftp, f"{full_dir}/{name}", rel_path, result)
            else:
                result.append(RepoItem(name, rel_path, False, attr.st_size, attr.st_mtime))

    def resolve_upload_name(self, rel_path: str, filename: str) -> str:
        """重名自动重命名：app.tar.gz -> app.tar(1).gz（不覆盖）；与目录同名则拒绝。"""
        full_dir = self._resolve(rel_path)
        client = self._connect()
        try:
            sftp = client.open_sftp()
            try:
                entries = {
                    attr.filename: stat.S_ISDIR(attr.st_mode)
                    for attr in sftp.listdir_attr(full_dir)
                }
            finally:
                sftp.close()
        finally:
            client.close()
        if filename not in entries:
            return filename
        if entries[filename]:
            raise RepositoryError(f"与已有目录同名，无法上传: {filename}")
        base, dot, ext = filename.rpartition(".")
        if not dot:
            base, ext = filename, ""
        n = 1
        while True:
            candidate = f"{base}({n})" + (f".{ext}" if ext else "")
            if candidate not in entries:
                return candidate
            n += 1

    def upload(self, fileobj, rel_path: str, filename: str, size: int) -> tuple:
        """流式上传，重名自动重命名。返回 (saved_name, variable_name)。"""
        if not SAFE_FILENAME_RE.match(filename):
            raise RepositoryError(f"文件名包含非法字符，仅允许字母/数字/._-: {filename}")
        if size > settings.REPO_MAX_UPLOAD_SIZE:
            raise UploadTooLargeError(f"文件 {filename} 超过最大上传限制")
        saved_name = self.resolve_upload_name(rel_path, filename)
        full_dir = self._resolve(rel_path)
        target = f"{full_dir}/{saved_name}"
        client = self._connect()
        try:
            sftp = client.open_sftp()
            try:
                try:
                    attr = sftp.stat(target)
                    if stat.S_ISDIR(attr.st_mode):
                        raise RepositoryError(f"与已有目录同名，无法上传: {saved_name}")
                except FileNotFoundError:
                    pass
                with sftp.open(target, "wb") as remote:
                    while chunk := fileobj.read(4 * 1024 * 1024):
                        remote.write(chunk)
            finally:
                sftp.close()
        finally:
            client.close()
        rel_file = f"{rel_path}/{saved_name}" if rel_path else saved_name
        return saved_name, variable_name(rel_file)

    def get_fileobj(self, rel_path: str):
        """打开远程文件供流式下载。返回 (sftp, ssh_client, fileobj, size)，调用方负责关闭。"""
        full = self._resolve(rel_path)
        client = self._connect()
        sftp = None
        try:
            sftp = client.open_sftp()
            attr = sftp.stat(full)
            if stat.S_ISDIR(attr.st_mode):
                raise RepositoryError("目标为目录，无法下载")
            fileobj = sftp.open(full, "rb")
        except FileNotFoundError:
            if sftp is not None:
                sftp.close()
            client.close()
            raise RepositoryError("路径不存在")
        except Exception:
            if sftp is not None:
                sftp.close()
            client.close()
            raise
        return sftp, client, fileobj, attr.st_size

    def delete(self, rel_paths: list) -> dict:
        """批量删除文件/目录（单连接复用）。返回 {deleted: [...], errors: [{path, error}]}。
        目录递归删除；拒绝删除仓库根目录。删除成功后重置变量缓存。"""
        deleted, errors = [], []
        client = self._connect()
        try:
            sftp = client.open_sftp()
            try:
                for rel in rel_paths:
                    rel = (rel or "").strip()
                    if not rel:
                        errors.append({"path": rel, "error": "路径为空"})
                        continue
                    try:
                        full = self._resolve(rel)
                        if full.rstrip("/") == self.root.rstrip("/"):
                            raise RepositoryError("不能删除仓库根目录")
                        self._delete_path(sftp, full, rel)
                        deleted.append(rel)
                    except Exception as e:
                        errors.append({"path": rel, "error": str(e)})
            finally:
                sftp.close()
        finally:
            client.close()
        if deleted:
            _reset_repo_vars_cache()
        return {"deleted": deleted, "errors": errors}

    def _delete_path(self, sftp, full: str, rel: str):
        """删除单个文件或递归删除目录。"""
        try:
            attr = sftp.stat(full)
        except FileNotFoundError:
            raise RepositoryError("路径不存在") from None
        if stat.S_ISDIR(attr.st_mode):
            self._rmdir_recursive(sftp, full, rel)
        else:
            sftp.remove(full)

    def _rmdir_recursive(self, sftp, full: str, rel: str):
        """递归删除目录（先删子项，再删自身）。"""
        for attr in sftp.listdir_attr(full):
            child_full = f"{full}/{attr.filename}"
            child_rel = f"{rel}/{attr.filename}"
            if stat.S_ISDIR(attr.st_mode):
                self._rmdir_recursive(sftp, child_full, child_rel)
            else:
                sftp.remove(child_full)
        sftp.rmdir(full)


# 仓库变量映射缓存（成功 TTL 60s，失败熔断 5s）
_repo_vars_cache: dict | None = None
_repo_vars_ts: float = 0.0
_repo_vars_failed = False
_REPO_VARS_TTL = 60
_REPO_VARS_FAIL_TTL = 5


def _reset_repo_vars_cache():
    """测试辅助：清空缓存。"""
    global _repo_vars_cache, _repo_vars_ts, _repo_vars_failed
    _repo_vars_cache = None
    _repo_vars_ts = 0.0
    _repo_vars_failed = False


def get_repo_variables() -> dict:
    """获取仓库全部文件的变量映射 {PKG_XXX: http_url}（缓存）。仓库不可达时返回空 dict（不抛异常）。"""
    global _repo_vars_cache, _repo_vars_ts, _repo_vars_failed
    now = time.monotonic()
    if _repo_vars_cache is not None:
        ttl = _REPO_VARS_FAIL_TTL if _repo_vars_failed else _REPO_VARS_TTL
        if now - _repo_vars_ts < ttl:
            return _repo_vars_cache
    try:
        client = RepositoryClient()
        result = {}
        base_url = settings.REPO_HTTP_URL.rstrip("/")
        for item in client.list_all():
            # URL 编码文件名特殊字符（空格、引号、$ 等），防止注入；括号保留保持可读
            url_path = quote(item.rel_path, safe="/()")
            result[item.variable] = f"{base_url}/{url_path}"
        _repo_vars_cache = result
        _repo_vars_failed = False
        _repo_vars_ts = now
        return result
    except Exception as e:
        logger.warning("获取仓库变量失败: %s", e)
        _repo_vars_cache = {}
        _repo_vars_failed = True
        _repo_vars_ts = now  # 失败短暂缓存，避免每次脚本执行都重试（熔断）
        return {}


def build_repo_env_block(language: str = "shell") -> str:
    """构造脚本变量注入块（shell export / python os.environ）。仓库不可达时返回空串。"""
    variables = get_repo_variables()
    if not variables:
        return ""
    lines = ["# ==== SITOP 软件仓库变量（自动注入，可在脚本中直接使用）===="]
    if language == "python":
        lines.append("import os")
        for name, url in variables.items():
            lines.append(f"os.environ.setdefault({name!r}, {url!r})")
    else:
        for name, url in variables.items():
            # shell 单引号转义：值内单引号替换为 '\''（值本身经 URL 编码不含引号，双保险）
            safe_url = url.replace("'", "'\\''")
            lines.append(f"export {name}='{safe_url}'")
    return "\n".join(lines)
