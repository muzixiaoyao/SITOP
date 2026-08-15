<div align="center">

# SITOP — Server Intelligent Task Orchestration Platform

**Server Intelligent Task Orchestration Platform**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org/)
[![Django](https://img.shields.io/badge/Django-5.1-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Tests](https://img.shields.io/badge/Tests-148-green)](./backend/tests/)

<p align="center">
🇨🇳 <a href="./README.md">简体中文</a> | 🇺🇸 <a href="./README.en.md">English</a>
</p>

A **server intelligent task orchestration platform** for operations teams: manage server groups, SSH credentials, initialization scripts, and execution templates through a web UI. Execute complete initialization workflows across hundreds or thousands of servers with one click, track progress in real-time, audit operations, and export reports.

</div>

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Software Repository Integration](#software-repository-integration)
- [Production Deployment](#production-deployment)
- [API Reference](#api-reference)
- [Development Notes](#development-notes)
- [License](#license)

---

## Features

| Module | Description |
|--------|-------------|
| **Dashboard** | Task count, success rate, server statistics + 7-day trend charts and status distribution (ECharts) |
| **Server Management** | Group management, single/batch add, CSV import/export (UTF-8/GBK), inline credentials, connectivity check, batch command execution, global/per-group search (fuzzy/exact), column filtering, pagination (20/50/100/200/all), cross-page select all |
| **Credential Management** | SSH credentials (password/private key + passphrase), AES-encrypted at rest, group-level default credentials |
| **Script Library** | Three script types: health check / initialization steps / completion check, supports Shell and Python, version managed |
| **Template Orchestration** | Compose health check + multiple initialization steps (with order, timeout, failure policy: abort/continue/retry) + completion check into reusable templates |
| **Software Repository** | Package distribution for initialization: upload (SFTP, CJK filenames), list/download (nginx HTTP direct ~0.3s), online delete (admin + confirmation); auto-generates `PKG_*` variables injected into scripts |
| **Task Center** | Create batch initialization tasks from templates, four-phase execution (connectivity → health → init → completion), WebSocket real-time progress, export all logs as **interactive HTML report** |
| **Audit Logs** | Full audit trail for login, CRUD, import/export operations |
| **User Management** | Multi-tenant isolation, roles: Admin / Operator / Read-only |

---

## Architecture

```
┌────────────┐    ┌─────────────────────────────────────────┐
│  Browser    │    │  k8s Cluster (namespace: sitop)          │
│  Vue3 SPA   │───▶│  nginx (sitop-frontend)                  │
└────────────┘    │       │ /api  /ws                        │
                  │  sitop-backend (Django + Daphne)          │
                  │       │                 ┌──────────────┐ │
                  │       ├── PostgreSQL ◀──┤ Redis        │ │
                  │       │                 └──────────────┘ │
                  │  sitop-celery-worker ──▶ Redis (queue)    │
                  └───────┼──────────────────────────────────┘
                          │ SSH (Paramiko)
                          ▼
                  ┌─────────────────┐   List/Download(HTTP) ┌──────────────────┐
                  │  Target Servers  │ ◀─────────────────── │ Repo Server       │
                  └─────────────────┘   curl packages       │ nginx :8081+SFTP │
                                                          └──────────────────┘
```

> [!NOTE]
> **Control/Data Plane Separation**: Package downloads go directly from target servers to the repository HTTP endpoint (bypassing SITOP). Directory listings are fetched by the frontend directly from nginx JSON autoindex (~0.3s). SFTP is used only for uploads and fallback.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Django 5.1, DRF 3.15, Channels 4 + Daphne 4 (WebSocket), Celery 5, Paramiko 3 (SSH/SFTP), SimpleJWT 5.3, cryptography 43 (credential encryption), ReportLab 4 (PDF reports) |
| **Frontend** | Vue 3.5, TypeScript 5.6, Element Plus 2.9, Pinia 2.3, Vue Router 4.5, Axios 1.7, ECharts 5.6, Vite 6 |
| **Storage** | PostgreSQL (production, psycopg 3.2) / SQLite (development), Redis 7 (Celery queue + cache) |
| **Deployment** | Docker Compose (dev), k8s (production), Yunxiao Pipeline (CI/CD, manual trigger), Harbor registry |
| **Testing** | pytest 8 + pytest-django 4 + factory-boy 3 (**148 tests**) |

---

## Quick Start

### 1. Prepare Environment Variables

```bash
cp .env.example .env
# Edit as needed:
#   CREDENTIAL_ENCRYPTION_KEY  Credential encryption key
#   REPO_SSH_KEY_PATH          Repository server private key path
```

> [!TIP]
> Generate encryption key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

### 2. Start Dependencies & Backend

```bash
# Redis
docker compose up -d redis

# Backend (Python 3.14 venv)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser

# API server (development)
python manage.py runserver 0.0.0.0:8000

# WebSocket (ASGI, separate terminal)
daphne -p 8001 config.asgi:application

# Celery worker (separate terminal)
celery -A config worker -l info
```

### 3. Start Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (vite proxies /api → backend)
```

### 4. Run Tests

```bash
cd backend && .venv/bin/python -m pytest -q    # 148 tests
cd frontend && npm run build                    # type check + build
```

---

## Configuration

<details>
<summary>Full environment variables (click to expand)</summary>

| Variable | Description |
|----------|-------------|
| `DJANGO_SECRET_KEY` | Django secret key (must change in production) |
| `DATABASE_URL` | PostgreSQL connection string (leave empty for SQLite in dev) |
| `REDIS_URL` | Redis URL (Celery queue + cache) |
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet key for SSH credential encryption |
| `REPO_SSH_HOST` / `REPO_SSH_PORT` / `REPO_SSH_USER` | Repository server SSH connection |
| `REPO_SSH_KEY_PATH` | Private key path (**paramiko does not parse ~/.ssh/config, must specify explicitly**) |
| `REPO_KNOWN_HOSTS` | known_hosts path (leave empty to auto-accept host keys) |
| `REPO_ROOT_PATH` | Repository root directory (default: `/data/initpackages`) |
| `REPO_HTTP_URL` | Repository HTTP download URL (frontend direct + script variable injection) |
| `REPO_MAX_UPLOAD_SIZE` | Upload size limit in bytes (default: 1GB) |
| `VITE_REPO_HTTP_URL` (frontend/.env) | Repository direct URL injected at frontend build time |

</details>

---

## Software Repository Integration

Packages are available for initialization scripts to download, with automatic variable injection:

1. Upload `mysql-8.0.26.tar.gz` → auto-generates variable `PKG_MYSQL_8_0_26_TAR_GZ`
2. Variables are automatically injected during task execution (Shell `export` / Python `os.environ.setdefault`):

```bash
# Use directly in scripts
curl -fsSL -O "$PKG_MYSQL_8_0_26_TAR_GZ"
tar xzf mysql-8.0.26.tar.gz
```

> [!IMPORTANT]
> The repository server nginx must be configured with `autoindex_format json` + CORS headers for frontend direct directory listing:
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

## Production Deployment

```bash
kubectl apply -f k8s/00-middleware/     # PostgreSQL (first time)
kubectl apply -f k8s/01-sitop/           # namespace/secrets/backend/celery/frontend

# Update release (Yunxiao pipeline manual trigger → rolling update)
kubectl -n sitop rollout restart deploy/sitop-backend deploy/sitop-celery-worker deploy/sitop-frontend
```

**CI/CD**: Yunxiao Pipeline (sitop-frontend / sitop-backend), **manual trigger** after code push, images pushed to Harbor, tag pattern `dev-<timestamp>` + `latest`.

<details>
<summary>Deployment Components</summary>

| Deployment | Description |
|------------|-------------|
| `sitop-backend` | Daphne (HTTP + WebSocket) |
| `sitop-celery-worker` | Task engine worker |
| `sitop-frontend` | nginx serving SPA, `/api` and `/ws` reverse-proxied to backend |

</details>

---

## API Reference

| Path | Description |
|------|-------------|
| `POST /api/auth/login/` | Login to obtain JWT |
| `GET /api/groups/` | Group list |
| `GET /api/groups/<id>/servers/?page_size=N` | Server list (FlexiblePagination) |
| `POST /api/groups/<id>/servers/import/` | CSV import (UTF-8/GBK, auto-detect password auth) |
| `POST /api/servers/batch/connectivity\|credential\|delete\|group-move\|group-add/` | Batch operations |
| `GET/POST /api/scripts/` | Script library |
| `GET/POST /api/templates/` | Initialization templates |
| `POST /api/jobs/` | Create initialization task (WebSocket `/ws/jobs/<id>/` for progress) |
| `GET /api/repository/files/` | Repository file list |
| `POST /api/repository/files/upload/` | Repository upload |
| `POST /api/repository/files/delete/` | Repository delete (admin only) |
| `GET /api/reports/dashboard/` | Dashboard statistics |

---

## Development Notes

- **paramiko key-based auth**: Does not parse `~/.ssh/config`; must explicitly specify `key_filename`
- **DRF pagination**: Custom `FlexiblePagination` supports `?page_size=` override (default 20)
- **CSV CJK support**: Import supports UTF-8/GBK auto-detection (Excel CJK locale can save directly)
- **Delete cache reset**: Repository delete resets script variable cache to prevent injecting deleted package URLs
- **Log export**: Task logs export as self-contained interactive HTML (inline CSS/JS, double-click to open, supports status filter/node search/navigation)

---

## License

This project is licensed under the [GNU Affero General Public License v3.0](./LICENSE).

- Free to use, modify, and distribute
- **Must provide source code**: Even when providing services over a network (SaaS), source code must be made available to users
- Modified versions must also be licensed under AGPL-3.0
