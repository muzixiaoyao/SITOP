import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("sitop")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# M4: periodic connectivity patrol (every 30 minutes)
app.conf.beat_schedule = {
    "patrol-all-groups": {
        "task": "servers.patrol_all_groups",
        "schedule": crontab(minute="*/30"),
    },
}
