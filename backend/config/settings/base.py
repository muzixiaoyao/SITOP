import environ
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-change-me")
DEBUG = env("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    "channels",
    # Local
    "apps.accounts",
    "apps.servers",
    "apps.executor",
    "apps.scripts",
    "apps.tasks",
    "apps.reports",
    "apps.repository",
    "apps.tickets",
    "apps.kb",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.accounts.middleware.TenantMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
DATABASE_URL = env("DATABASE_URL", default="")
if DATABASE_URL:
    DATABASES = {
        "default": env.db("DATABASE_URL"),
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "data" / "db.sqlite3",
        }
    }

# Auth
AUTH_USER_MODEL = "accounts.User"

# DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "300/min",
        "connectivity": "5/min",
        "job_create": "10/min",
    },
    "DEFAULT_PAGINATION_CLASS": "config.pagination.FlexiblePagination",
    "PAGE_SIZE": 20,
    # Disable ?format= content negotiation — we use it for report export (csv/pdf)
    "URL_FORMAT_OVERRIDE": None,
}

# JWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# Encryption key for SSH credentials
CREDENTIAL_ENCRYPTION_KEY = env("CREDENTIAL_ENCRYPTION_KEY", default="")

# Celery — Redis broker in production; dev uses eager mode (see development.py)
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/2")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]

# Django Channels — Redis layer in production; dev uses in-memory (see development.py)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [env("REDIS_URL", default="redis://localhost:6379/0")]},
    }
}

# Script signing key (M4)
SCRIPT_SIGNING_KEY = env("SCRIPT_SIGNING_KEY", default="dev-signing-key")

# Static files
STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Software repository (软件仓库)
REPO_SSH_HOST = env("REPO_SSH_HOST", default="192.168.1.1")
REPO_SSH_PORT = env.int("REPO_SSH_PORT", default=22)
REPO_SSH_USER = env("REPO_SSH_USER", default="root")
REPO_SSH_KEY_PATH = env("REPO_SSH_KEY_PATH", default="")
# known_hosts 文件路径（设置后启用主机密钥校验 RejectPolicy；留空则 AutoAddPolicy，仅建议开发环境）
REPO_KNOWN_HOSTS = env("REPO_KNOWN_HOSTS", default="")
REPO_ROOT_PATH = env("REPO_ROOT_PATH", default="/data/initpackages")
REPO_HTTP_URL = env("REPO_HTTP_URL", default="http://192.168.1.1:8081/")
REPO_MAX_UPLOAD_SIZE = env.int("REPO_MAX_UPLOAD_SIZE", default=1073741824)  # 1GB
