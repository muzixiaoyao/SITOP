<div align="center">

# SITOP — 服务器智能任务编排平台

**Server Intelligent Task Orchestration Platform**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org/)
[![Django](https://img.shields.io/badge/Django-5.1-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Tests](https://img.shields.io/badge/Tests-148-green)](./backend/tests/)

<p align="center">
🇨🇳 <a href="./README.md">简体中文</a> | 🇺🇸 <a href="./README.en.md">English</a>
</p>

面向运维场景的 **服务器智能任务编排平台**：通过 Web 界面管理服务器分组、SSH 凭据、初始化脚本与执行模板，一键对成百上千台服务器执行完整的初始化流程，并实时跟踪进度、审计操作、导出报告。

</div>

---

## 目录

- [功能特性](#功能特性)
- [架构](#架构)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [配置参考](#配置参考)
- [软件仓库集成](#软件仓库集成)
- [生产部署](#生产部署)
- [API 参考](#api-参考)
- [开发备忘](#开发备忘)
- [许可](#许可)

---

## 功能特性

| 模块 | 说明 |
|------|------|
| **仪表盘** | 任务数、成功率、服务器数统计 + 近 7 天任务趋势图、状态分布图（ECharts） |
| **服务器管理** | 分组管理、单台/批量添加、CSV 导入导出（UTF-8/GBK）、内联凭据、连通性检测、批量执行命令、全局/分组内搜索（模糊/精确）、按列过滤、分页（20/50/100/200/全部）、跨页全选 |
| **凭据管理** | SSH 凭据（密码/私钥+口令），入库 AES 加密存储，支持分组默认凭据 |
| **脚本库** | 三类脚本：健康检查 / 初始化步骤 / 完成度检查，支持 Shell 与 Python，版本管理 |
| **模板编排** | 将健康检查 + 多个初始化步骤（含顺序、超时、失败策略 abort/continue/retry）+ 完成度检查编排为可复用模板 |
| **软件仓库** | 初始化软件包分发：上传（SFTP，支持中文文件名）、列表/下载（nginx HTTP 直连 ~0.3s）、在线删除（管理员+二次确认）；每个包自动生成 `PKG_*` 变量，执行脚本时自动注入 |
| **任务中心** | 基于模板创建批量初始化任务，四阶段执行（连通性→健康→初始化→完成度），WebSocket 实时进度，一键导出全部日志为**交互式 HTML 报告** |
| **审计日志** | 登录、增删改、导入导出等操作全量审计 |
| **用户管理** | 多租户隔离，角色：管理员 / 操作员 / 只读 |

---

## 架构

```
┌────────────┐    ┌─────────────────────────────────────────┐
│  浏览器     │    │  k8s 集群 (namespace: sitop)              │
│  Vue3 SPA  │───▶│  nginx(sitop-frontend)                    │
└────────────┘    │       │ /api  /ws                        │
                  │  sitop-backend (Django+Daphne)            │
                  │       │                 ┌──────────────┐ │
                  │       ├── PostgreSQL ◀──┤ Redis        │ │
                  │       │                 └──────────────┘ │
                  │  sitop-celery-worker ──▶ Redis (队列)      │
                  └───────┼──────────────────────────────────┘
                          │ SSH (Paramiko)
                          ▼
                  ┌─────────────────┐   列表/下载(HTTP)  ┌──────────────────┐
                  │  目标服务器 ×N    │ ◀──────────────── │ 软件仓库服务器      │
                  └─────────────────┘   脚本 curl 拉包    │ nginx :8081 + SFTP│
                                                          └──────────────────┘
```

> [!NOTE]
> **控制面/数据面分离**：软件包下载由目标服务器直连仓库 HTTP（不经过 SITOP），仓库列表由前端直连 nginx JSON autoindex（~0.3s），SFTP 仅用于上传与回退。

---

## 技术栈

| 层 | 技术 |
|----|------|
| **后端** | Django 5.1、DRF 3.15、Channels 4 + Daphne 4（WebSocket）、Celery 5、Paramiko 3（SSH/SFTP）、SimpleJWT 5.3、cryptography 43（凭据加密）、ReportLab 4（PDF 报告） |
| **前端** | Vue 3.5、TypeScript 5.6、Element Plus 2.9、Pinia 2.3、Vue Router 4.5、Axios 1.7、ECharts 5.6、Vite 6 |
| **存储** | PostgreSQL（生产，psycopg 3.2）/ SQLite（开发）、Redis 7（Celery 队列 + 缓存） |
| **部署** | Docker Compose（开发）、k8s（生产）、云效流水线（CI/CD，手动触发）、Harbor 镜像仓库 |
| **测试** | pytest 8 + pytest-django 4 + factory-boy 3（**148 个测试**） |

---

## 快速开始

### 1. 准备环境变量

```bash
cp .env.example .env
# 按需修改：
#   CREDENTIAL_ENCRYPTION_KEY  凭据加密密钥
#   REPO_SSH_KEY_PATH          仓库服务器免密私钥路径
```

> [!TIP]
> 生成加密密钥：`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

### 2. 启动依赖与后端

```bash
# Redis
docker compose up -d redis

# 后端（Python 3.14 venv）
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser

# API 服务（开发）
python manage.py runserver 0.0.0.0:8000

# WebSocket（ASGI，另开终端）
daphne -p 8001 config.asgi:application

# Celery worker（另开终端）
celery -A config worker -l info
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173（vite 代理 /api → 后端）
```

### 4. 运行测试

```bash
cd backend && .venv/bin/python -m pytest -q    # 148 tests
cd frontend && npm run build                    # 类型检查 + 构建
```

---

## 配置参考

<details>
<summary>完整环境变量列表（点击展开）</summary>

| 变量 | 说明 |
|------|------|
| `DJANGO_SECRET_KEY` | Django 密钥（生产必须替换） |
| `DATABASE_URL` | PostgreSQL 连接串（开发可留空用 SQLite） |
| `REDIS_URL` | Redis 地址（Celery 队列 + 缓存） |
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet 密钥，SSH 凭据加密存储 |
| `REPO_SSH_HOST` / `REPO_SSH_PORT` / `REPO_SSH_USER` | 软件仓库服务器 SSH 连接 |
| `REPO_SSH_KEY_PATH` | 免密私钥路径（**paramiko 不解析 ~/.ssh/config，必须显式指定**） |
| `REPO_KNOWN_HOSTS` | known_hosts 路径（留空则自动接受主机密钥） |
| `REPO_ROOT_PATH` | 仓库根目录（默认 `/data/initpackages`） |
| `REPO_HTTP_URL` | 仓库 HTTP 下载地址（前端直连 + 脚本变量注入） |
| `REPO_MAX_UPLOAD_SIZE` | 上传大小上限（字节，默认 1GB） |
| `VITE_REPO_HTTP_URL`（frontend/.env） | 前端构建时注入的仓库直连地址 |

</details>

---

## 软件仓库集成

软件包供初始化脚本下载使用，变量自动注入：

1. 上传 `mysql-8.0.26.tar.gz` → 自动生成变量 `PKG_MYSQL_8_0_26_TAR_GZ`
2. 执行任务时脚本自动注入（Shell `export` / Python `os.environ.setdefault`）：

```bash
# 脚本中直接使用
curl -fsSL -O "$PKG_MYSQL_8_0_26_TAR_GZ"
tar xzf mysql-8.0.26.tar.gz
```

> [!IMPORTANT]
> 仓库服务器 nginx 需配置 `autoindex_format json` + CORS 头，供前端直连列目录：
>
> ```nginx
> location / {
>     autoindex on;
>     autoindex_format json;
>     autoindex_exact_size on;
>     autoindex_localtime on;
>     add_header Access-Control-Allow-Origin "*";
> }
> ```

---

## 生产部署

```bash
kubectl apply -f k8s/00-middleware/     # PostgreSQL（首次）
kubectl apply -f k8s/01-sitop/           # namespace/secrets/backend/celery/frontend

# 更新发布（云效流水线手动触发构建镜像 → 滚动更新）
kubectl -n sitop rollout restart deploy/sitop-backend deploy/sitop-celery-worker deploy/sitop-frontend
```

**CI/CD**：云效流水线（sitop-frontend / sitop-backend），代码推送后**手动触发**构建，镜像推送 Harbor，tag 规则 `dev-<时间戳>` + `latest`。

<details>
<summary>Deployment 组成</summary>

| Deployment | 说明 |
|------------|------|
| `sitop-backend` | Daphne（HTTP + WebSocket） |
| `sitop-celery-worker` | 任务引擎 worker |
| `sitop-frontend` | nginx 托管 SPA，`/api`、`/ws` 反代到 backend |

</details>

---

## API 参考

| 路径 | 说明 |
|------|------|
| `POST /api/auth/login/` | 登录获取 JWT |
| `GET /api/groups/` | 分组列表 |
| `GET /api/groups/<id>/servers/?page_size=N` | 服务器列表（FlexiblePagination） |
| `POST /api/groups/<id>/servers/import/` | CSV 导入（UTF-8/GBK，自动推断密码认证） |
| `POST /api/servers/batch/connectivity\|credential\|delete\|group-move\|group-add/` | 批量操作 |
| `GET/POST /api/scripts/` | 脚本库 |
| `GET/POST /api/templates/` | 初始化模板 |
| `POST /api/jobs/` | 创建初始化任务（WebSocket `/ws/jobs/<id>/` 推送进度） |
| `GET /api/repository/files/` | 仓库列表 |
| `POST /api/repository/files/upload/` | 仓库上传 |
| `POST /api/repository/files/delete/` | 仓库删除（仅管理员） |
| `GET /api/reports/dashboard/` | 仪表盘统计 |

---

## 开发备忘

- **paramiko 免密**：不解析 `~/.ssh/config`，必须 `key_filename` 显式指定私钥
- **DRF 分页**：自定义 `FlexiblePagination` 支持 `?page_size=` 覆盖默认 20 条
- **CSV 中文**：导入支持 UTF-8/GBK 自适应解码（Excel 中文环境直接保存可用）
- **删除后缓存**：仓库删除会主动重置脚本变量缓存，避免注入已删除包地址
- **日志导出**：任务日志导出为自包含交互式 HTML（内联 CSS/JS，双击即开，支持状态筛选/节点搜索/导航跳转）

---

## 许可

本项目基于 [GNU Affero General Public License v3.0](./LICENSE) 授权。

- 允许自由使用、修改和分发
- **必须公开源代码**：即使通过网络提供服务（SaaS），也必须向用户提供源代码
- 修改后的版本必须以相同的 AGPL-3.0 授权
