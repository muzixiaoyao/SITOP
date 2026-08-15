from celery import shared_task

from . import engine


@shared_task(name="tasks.run_job")
def run_job_task(job_id):
    """Celery entry point for job execution."""
    engine.run_job(job_id)
