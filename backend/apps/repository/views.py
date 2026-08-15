"""Software repository API: 列目录 / 上传 / 删除 / 代理下载。"""
import logging
import posixpath

from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..accounts.audit import audit
from ..accounts.permissions import IsAdmin, IsOperatorOrAbove
from .client import (
    RepositoryClient, RepositoryError, PathNotAllowedError, UploadTooLargeError,
    is_relative_safe,
)

logger = logging.getLogger(__name__)


def _normalize_path(query_param: str) -> str:
    """去掉首尾斜杠的规范化相对路径。"""
    return (query_param or "").strip("/")


class RepositoryFileListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rel_path = _normalize_path(request.query_params.get("path", ""))
        if not is_relative_safe(rel_path):
            return Response({"detail": "非法路径"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            items = RepositoryClient().list_dir(rel_path)
        except PathNotAllowedError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error("仓库列目录失败 %s: %s", rel_path, e)
            return Response(
                {"detail": f"软件仓库服务器连接失败: {e}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        audit(request, "repository.browse", "repository", rel_path, {"count": len(items)})
        base_url = settings.REPO_HTTP_URL.rstrip("/")
        return Response({
            "path": rel_path,
            "parent": posixpath.dirname(rel_path) if rel_path else "",
            "root_path": settings.REPO_ROOT_PATH.rstrip("/"),
            "items": [
                {
                    "name": item.name,
                    "rel_path": item.rel_path,
                    "is_dir": item.is_dir,
                    "size": item.size,
                    "mtime": item.mtime,
                    "variable": item.variable if not item.is_dir else "",
                    "http_url": f"{base_url}/{item.rel_path}" if not item.is_dir else "",
                }
                for item in items
            ],
        })


class RepositoryFileDeleteView(APIView):
    """删除仓库文件/目录（仅管理员；目录递归删除；二次确认由前端承担）。"""
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        paths = request.data.get("paths", [])
        if not isinstance(paths, list) or not paths:
            return Response({"detail": "paths 不能为空"}, status=status.HTTP_400_BAD_REQUEST)
        if len(paths) > 500:
            return Response({"detail": "单次最多删除 500 个路径"}, status=status.HTTP_400_BAD_REQUEST)
        client = RepositoryClient()
        result = client.delete([str(p) for p in paths])
        audit(request, "repository.delete", "repository", "", {
            "deleted": result["deleted"], "errors": result["errors"],
        })
        return Response(result, status=status.HTTP_200_OK)


class RepositoryFileUploadView(APIView):
    permission_classes = [IsAuthenticated, IsOperatorOrAbove]

    def post(self, request):
        rel_path = _normalize_path(request.query_params.get("path", ""))
        if not is_relative_safe(rel_path):
            return Response({"detail": "非法路径"}, status=status.HTTP_400_BAD_REQUEST)
        files = request.FILES.getlist("files")
        if not files:
            return Response({"detail": "未提供文件"}, status=status.HTTP_400_BAD_REQUEST)

        results, errors = [], []
        client = RepositoryClient()
        for f in files:
            if f.size > settings.REPO_MAX_UPLOAD_SIZE:
                errors.append({"name": f.name, "error": "超过最大上传限制"})
                continue
            try:
                saved_name, variable = client.upload(f, rel_path, f.name, f.size)
                results.append({
                    "original_name": f.name,
                    "saved_name": saved_name,
                    "variable": variable,
                    "size": f.size,
                })
            except UploadTooLargeError as e:
                errors.append({"name": f.name, "error": str(e)})
            except Exception as e:
                logger.error("仓库上传失败 %s/%s: %s", rel_path, f.name, e)
                errors.append({"name": f.name, "error": f"上传失败: {e}"})

        if results:
            audit(request, "repository.upload", "repository", rel_path, {"files": results})
        # 全部失败返回 400，部分成功返回 201
        if not results:
            return Response({"results": [], "errors": errors}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"results": results, "errors": errors}, status=status.HTTP_201_CREATED)


class RepositoryFileDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rel_path = _normalize_path(request.query_params.get("path", ""))
        if not is_relative_safe(rel_path):
            return Response({"detail": "非法路径"}, status=status.HTTP_400_BAD_REQUEST)
        client = RepositoryClient()
        try:
            sftp, ssh_client, fileobj, size = client.get_fileobj(rel_path)
        except PathNotAllowedError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except RepositoryError as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error("仓库下载失败 %s: %s", rel_path, e)
            return Response(
                {"detail": "软件仓库服务器连接失败"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        def generate():
            try:
                while chunk := fileobj.read(64 * 1024):
                    yield chunk
            finally:
                try:
                    fileobj.close()
                except Exception:
                    pass
                try:
                    sftp.close()
                except Exception:
                    pass
                ssh_client.close()

        filename = posixpath.basename(rel_path)
        response = StreamingHttpResponse(generate(), content_type="application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = str(size)
        return response
