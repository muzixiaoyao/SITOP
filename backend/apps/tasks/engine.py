"""Four-phase job execution engine.

Phases (in order): connectivity → health → init → completion.
Each phase runs over all servers of the job's group. Servers that fail
connectivity are skipped in later phases. Progress is published to the
Channels group for real-time UI updates. Cancellation is cooperative:
the engine checks job.status before each phase and each server.
"""
import logging

from django.utils import timezone

from apps.executor.ssh import SSHExecutor
from . import parsers
from .progress import publish_job_update
from .webhooks import notify_job_finished

logger = logging.getLogger(__name__)


class JobCancelled(Exception):
    pass


class ScriptSignatureError(Exception):
    pass


def _verified_content(script) -> str:
    """Return script content after verifying its HMAC signature (M4)."""
    if not script.verify_signature():
        raise ScriptSignatureError(
            f"Script '{script.name}' signature verification failed — refusing to execute"
        )
    return script.content


def _refresh_job(job):
    job.refresh_from_db()
    if job.status == "cancelled":
        raise JobCancelled()
    return job


def _update_task(task, **fields):
    for k, v in fields.items():
        setattr(task, k, v)
    task.save(update_fields=list(fields.keys()))
    publish_job_update(
        task.job_id,
        "server.status_changed",
        {
            "server_task_id": str(task.id),
            "hostname": task.server.hostname,
            "status": task.status,
            "current_step": task.current_step,
        },
    )


def _log(task, phase, status, output="", error="", exit_code=None,
         step_order=None, script_name=""):
    from .models import TaskStepLog

    TaskStepLog.objects.create(
        server_task=task, phase=phase, status=status,
        output=(output or "")[:4000], error=(error or "")[:2000],
        exit_code=exit_code, step_order=step_order, script_name=script_name,
        ended_at=timezone.now(),
    )


def create_job_tasks(job):
    """Create per-server tasks for a job (idempotent)."""
    from .models import JobServerTask

    existing = set(job.server_tasks.values_list("server_id", flat=True))
    for server in job.group.servers.all():
        if server.id not in existing:
            JobServerTask.objects.create(job=job, server=server)


def run_job(job_id):
    """Execute the full four-phase pipeline for a job."""
    from .models import InitJob

    try:
        job = InitJob.objects.get(id=job_id)
    except InitJob.DoesNotExist:
        logger.error("Job %s not found", job_id)
        return

    # Respect cancellation that happened before the worker picked it up
    if job.status == "cancelled":
        publish_job_update(job.id, "job.cancelled")
        return

    job.status = "running"
    job.start_time = timezone.now()
    job.save(update_fields=["status", "start_time"])
    create_job_tasks(job)
    publish_job_update(job.id, "job.started")

    template = job.template
    phases = ["connectivity", "health", "init", "completion"]

    try:
        with SSHExecutor(connect_timeout=10, exec_timeout=300) as executor:
            for phase in phases:
                _refresh_job(job)
                job.current_phase = phase
                job.save(update_fields=["current_phase"])
                publish_job_update(job.id, "phase.started", {"phase": phase})

                for task in job.server_tasks.select_related("server").all():
                    _refresh_job(job)
                    if task.status in ("failed", "skipped", "success") and phase != "completion":
                        # Already terminal in an earlier phase (failed/skipped);
                        # success tasks continue through later phases.
                        if task.status != "success":
                            continue
                    try:
                        if phase == "connectivity":
                            _run_connectivity(executor, task)
                        elif phase == "health":
                            _run_health(executor, task, template)
                        elif phase == "init":
                            _run_init(executor, task, template)
                        elif phase == "completion":
                            _run_completion(executor, task, template)
                    except JobCancelled:
                        raise
                    except Exception as e:  # noqa: BLE001
                        logger.error("Phase %s failed for %s: %s", phase, task.server.hostname, e)
                        _log(task, phase, "failed", error=str(e), exit_code=-1)
                        _update_task(task, status="failed", end_time=timezone.now())

                publish_job_update(job.id, "phase.completed", {"phase": phase})
    except JobCancelled:
        job.status = "cancelled"
        job.end_time = timezone.now()
        job.summary = _build_summary(job)
        job.save()
        publish_job_update(job.id, "job.cancelled")
        notify_job_finished(job)
        return

    _finalize(job)


def _run_connectivity(executor, task):
    _update_task(task, status="running", start_time=timezone.now())
    result = executor.check_connectivity(task.server)
    is_ok = result.exit_code == 0 and "SITOP_CONNECTIVITY_OK" in result.output
    task.connectivity_result = {
        "exit_code": result.exit_code, "output": result.output[:500], "error": result.error[:500],
    }
    task.save(update_fields=["connectivity_result"])
    # Also update the server's own connectivity status
    task.server.connectivity_status = "success" if is_ok else "failed"
    task.server.last_check_time = timezone.now()
    task.server.save(update_fields=["connectivity_status", "last_check_time"])
    _log(task, "connectivity", "success" if is_ok else "failed",
         output=result.output, error=result.error, exit_code=result.exit_code)
    if is_ok:
        _update_task(task, status="running")
    else:
        _update_task(task, status="failed", end_time=timezone.now())


def _run_health(executor, task, template):
    if not template.health_check_script:
        task.health_result = {"status": "skipped", "message": "No health check script configured"}
        task.save(update_fields=["health_result"])
        _log(task, "health", "success", output="Skipped: no health check script")
        return
    script = template.health_check_script
    try:
        content = _verified_content(script)
    except ScriptSignatureError as e:
        _log(task, "health", "failed", error=str(e))
        _update_task(task, status="failed", end_time=timezone.now())
        return
    result = executor.execute_script(task.server, content, script.language)
    parsed = parsers.parse_health_output(result.output, result.exit_code)
    task.health_result = parsed
    task.save(update_fields=["health_result"])
    _log(task, "health", "success" if parsed["ok"] else "failed",
         output=result.output, error=result.error, exit_code=result.exit_code,
         script_name=script.name)
    if not parsed["ok"]:
        _update_task(task, status="failed", end_time=timezone.now())


def _run_init(executor, task, template):
    steps = list(template.steps.all().order_by("step_order"))
    for step in steps:
        _refresh_job(task.job)
        _update_task(task, current_step=step.step_order)
        script = step.script
        try:
            content = _verified_content(script)
        except ScriptSignatureError as e:
            _log(task, "init", "failed", error=str(e), step_order=step.step_order,
                 script_name=script.name)
            _update_task(task, status="failed", end_time=timezone.now())
            return
        result = executor.execute_script(task.server, content, script.language)
        is_ok = result.exit_code == 0
        _log(task, "init", "success" if is_ok else "failed",
             output=result.output, error=result.error, exit_code=result.exit_code,
             step_order=step.step_order, script_name=script.name)
        if not is_ok:
            if step.on_failure == "abort":
                _update_task(task, status="failed", end_time=timezone.now())
                return
            if step.on_failure == "retry":
                succeeded = False
                for _ in range(step.max_retries):
                    result = executor.execute_script(task.server, script.content, script.language)
                    retry_ok = result.exit_code == 0
                    _log(task, "init", "success" if retry_ok else "failed",
                         output=result.output, error=result.error, exit_code=result.exit_code,
                         step_order=step.step_order, script_name=f"{script.name} (retry)")
                    if retry_ok:
                        succeeded = True
                        break
                if not succeeded:
                    _update_task(task, status="failed", end_time=timezone.now())
                    return
            # on_failure == "continue": proceed to next step


def _run_completion(executor, task, template):
    if task.status in ("failed", "skipped"):
        return
    if not template.completion_check_script:
        task.completion_result = {"status": "skipped", "message": "No completion check script configured"}
        task.save(update_fields=["completion_result"])
        _log(task, "completion", "success", output="Skipped: no completion check script")
        _update_task(task, status="success", end_time=timezone.now())
        return
    script = template.completion_check_script
    try:
        content = _verified_content(script)
    except ScriptSignatureError as e:
        _log(task, "completion", "failed", error=str(e), script_name=script.name)
        _update_task(task, status="failed", end_time=timezone.now())
        return
    result = executor.execute_script(task.server, content, script.language)
    parsed = parsers.parse_completion_output(result.output, result.exit_code)
    task.completion_result = parsed
    task.save(update_fields=["completion_result"])
    _log(task, "completion", "success" if parsed["ok"] else "failed",
         output=result.output, error=result.error, exit_code=result.exit_code,
         script_name=script.name)
    _update_task(task, status="success" if parsed["ok"] else "failed",
                 end_time=timezone.now())


def _build_summary(job):
    qs = job.server_tasks
    return {
        "total": qs.count(),
        "success": qs.filter(status="success").count(),
        "failed": qs.filter(status__in=["failed", "timeout"]).count(),
        "skipped": qs.filter(status="skipped").count(),
    }


def _finalize(job):
    summary = _build_summary(job)
    job.summary = summary
    job.end_time = timezone.now()
    # Success only when no server failed and at least one succeeded
    if summary["failed"] == 0 and summary["success"] > 0:
        job.status = "success"
    else:
        job.status = "failed"
    job.save()
    publish_job_update(job.id, "job.completed", {"status": job.status, "summary": summary})
    notify_job_finished(job)
