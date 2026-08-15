from django.contrib import admin
from .models import InitTemplate, TemplateStep, InitJob, JobServerTask, TaskStepLog


class TemplateStepInline(admin.TabularInline):
    model = TemplateStep
    extra = 0


@admin.register(InitTemplate)
class InitTemplateAdmin(admin.ModelAdmin):
    inlines = [TemplateStepInline]


@admin.register(InitJob)
class InitJobAdmin(admin.ModelAdmin):
    list_display = ["id", "template", "group", "status", "current_phase", "created_at"]


@admin.register(JobServerTask)
class JobServerTaskAdmin(admin.ModelAdmin):
    list_display = ["id", "job", "server", "status", "current_step"]


@admin.register(TaskStepLog)
class TaskStepLogAdmin(admin.ModelAdmin):
    list_display = ["id", "server_task", "phase", "step_order", "status", "started_at"]
