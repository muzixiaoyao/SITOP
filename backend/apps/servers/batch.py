"""Batch import/export for servers (CSV format, JumpServer-inspired)."""
import csv
import io
import logging

from django.db import transaction

logger = logging.getLogger(__name__)


class CSVDecodeError(ValueError):
    """CSV 文件编码无法识别。"""


def _decode_csv(csv_content: bytes) -> str:
    """自适应解码 CSV：UTF-8（含 BOM）优先，失败回退 GB18030（GBK 超集，兼容中文 Excel）。"""
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return csv_content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CSVDecodeError("无法识别 CSV 文件编码，请使用 UTF-8 或 GBK 编码保存文件")


def export_servers_csv(servers) -> bytes:
    """Export servers to CSV with UTF-8 BOM for Excel compatibility."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    # Header
    writer.writerow([
        "hostname", "ip", "ssh_port", "protocol", "platform",
        "connect_timeout", "exec_timeout", "labels", "tags", "groups", "comment",
        "auth_type", "auth_username", "auth_password",
    ])

    # Data rows
    for server in servers:
        group_names = ",".join(server.groups.values_list("name", flat=True))
        writer.writerow([
            server.hostname,
            server.ip,
            server.ssh_port,
            server.protocol,
            server.platform,
            server.connect_timeout,
            server.exec_timeout,
            ",".join(server.labels) if server.labels else "",
            ",".join(server.tags) if server.tags else "",
            group_names,
            server.comment,
            server.auth_type,
            server.auth_username,
            "",  # auth_password 加密内容不回导出
        ])

    # UTF-8 BOM for Excel
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def import_servers_csv(csv_content: bytes, group, tenant, user):
    """
    Import servers from CSV content.
    Returns: (created_count, errors)
    """
    from .models import Server, ServerGroup
    from apps.accounts.crypto import encrypt_value

    created = 0
    errors = []

    # 解码（编码自适应：UTF-8 → GBK/GB18030，兼容 Excel 中文环境保存的 CSV）
    content = _decode_csv(csv_content)
    reader = csv.DictReader(io.StringIO(content))

    required_fields = ["hostname", "ip"]

    # 预检：已存在的 IP 集合（导入全程维护）
    existing_ips = set(Server.objects.values_list("ip", flat=True))

    with transaction.atomic():
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
            try:
                # 每行独立 savepoint：IntegrityError 等异常只回滚当前行，不破坏整批事务
                with transaction.atomic():
                    # Validate required fields
                    for field in required_fields:
                        if not row.get(field, "").strip():
                            raise ValueError(f"缺少必填字段: {field}")

                    ip = row["ip"].strip()
                    if ip in existing_ips:
                        raise ValueError(f"IP 地址 {ip} 已存在，不允许重复添加")

                    # Parse lists
                    labels = [l.strip() for l in row.get("labels", "").split(",") if l.strip()]
                    tags = [t.strip() for t in row.get("tags", "").split(",") if t.strip()]

                    # Create server (without group FK)
                    server_data = {
                        "hostname": row["hostname"].strip(),
                        "ip": ip,
                        "ssh_port": int(row.get("ssh_port", 22) or 22),
                        "protocol": row.get("protocol", "ssh") or "ssh",
                        "platform": row.get("platform", "linux") or "linux",
                        "connect_timeout": int(row.get("connect_timeout", 15) or 15),
                        "exec_timeout": int(row.get("exec_timeout", 600) or 600),
                        "labels": labels,
                        "tags": tags,
                        "comment": row.get("comment", ""),
                    }
                    # 内联认证：CSV 批量导入仅支持密码（私钥需走凭据管理）
                    # 自动推断：auth_type 留空但提供 auth_username+auth_password 时按密码认证处理
                    auth_type = (row.get("auth_type") or "").strip()
                    auth_user = (row.get("auth_username") or "").strip()
                    auth_pw = (row.get("auth_password") or "").strip()
                    if auth_type in ("password",) or (not auth_type and auth_user and auth_pw):
                        if not auth_pw or not auth_user:
                            raise ValueError("密码认证必须同时填写 auth_username 和 auth_password")
                        server_data["auth_type"] = "password"
                        server_data["auth_username"] = auth_user
                        server_data["auth_password_encrypted"] = encrypt_value(auth_pw)
                    elif auth_type == "key":
                        # 批量导入不支持私钥：添加后可通过批量操作更新凭据
                        raise ValueError("批量导入不支持私钥认证，请添加后通过批量操作更新凭据")
                    elif auth_type == "credential":
                        pass  # 不设置内联认证（留空），后续可批量更新凭据
                    elif auth_type:
                        raise ValueError(f"不支持的 auth_type: {auth_type}")

                    server = Server.objects.create(**server_data)
                    existing_ips.add(ip)

                    # Assign to groups
                    if group:
                        server.groups.add(group)

                    # Also parse group names from CSV if present
                    group_names_raw = row.get("groups", "").strip()
                    if group_names_raw and tenant:
                        for gname in group_names_raw.split(","):
                            gname = gname.strip()
                            if gname:
                                g, _ = ServerGroup.objects.get_or_create(
                                    tenant=tenant, name=gname,
                                    defaults={"created_by": user},
                                )
                                server.groups.add(g)

                    # If still no groups, assign to default
                    if server.groups.count() == 0 and tenant:
                        from .models import get_or_create_default_group
                        server.groups.add(get_or_create_default_group(tenant))

                    created += 1

            except Exception as e:
                errors.append({"row": row_num, "error": str(e), "data": row})
                logger.warning("Import error at row %d: %s", row_num, e)

    return created, errors
