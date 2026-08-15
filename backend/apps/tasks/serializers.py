from rest_framework import serializers
from .models import InitTemplate, TemplateStep, InitJob, JobServerTask, TaskStepLog


class TemplateStepSerializer(serializers.ModelSerializer):
    script_name = serializers.CharField(source="script.name", read_only=True)

    class Meta:
        model = TemplateStep
        fields = ["id", "step_order", "script", "script_name", "parameters", "timeout_seconds", "on_failure", "max_retries"]
        read_only_fields = ["id"]


class InitTemplateSerializer(serializers.ModelSerializer):
    steps = TemplateStepSerializer(many=True, read_only=True)
    health_check_script_name = serializers.CharField(source="health_check_script.name", read_only=True, default=None)
    completion_check_script_name = serializers.CharField(source="completion_check_script.name", read_only=True, default=None)

    class Meta:
        model = InitTemplate
        fields = [
            "id", "name", "description", "health_check_script", "health_check_script_name",
            "completion_check_script", "completion_check_script_name",
            "steps", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class InitTemplateCreateSerializer(serializers.ModelSerializer):
    steps = TemplateStepSerializer(many=True, required=False)

    class Meta:
        model = InitTemplate
        fields = [
            "id", "name", "description", "health_check_script",
            "completion_check_script", "steps",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        steps_data = validated_data.pop("steps", [])
        template = InitTemplate.objects.create(**validated_data)
        for step_data in steps_data:
            TemplateStep.objects.create(template=template, **step_data)
        return template

    def update(self, instance, validated_data):
        steps_data = validated_data.pop("steps", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if steps_data is not None:
            instance.steps.all().delete()
            for step_data in steps_data:
                TemplateStep.objects.create(template=instance, **step_data)
        return instance


class TaskStepLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskStepLog
        fields = ["id", "phase", "step_order", "script_name", "output", "error", "exit_code", "status", "started_at", "ended_at"]


class JobServerTaskSerializer(serializers.ModelSerializer):
    hostname = serializers.CharField(source="server.hostname", read_only=True)
    ip = serializers.CharField(source="server.ip", read_only=True)
    step_logs = TaskStepLogSerializer(many=True, read_only=True)

    class Meta:
        model = JobServerTask
        fields = [
            "id", "server", "hostname", "ip", "status", "current_step",
            "connectivity_result", "health_result", "completion_result",
            "start_time", "end_time", "attempt", "step_logs",
        ]
        read_only_fields = ["id"]


class InitJobSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True, default=None)
    group_name = serializers.CharField(source="group.name", read_only=True)
    server_tasks = JobServerTaskSerializer(many=True, read_only=True)
    total_servers = serializers.IntegerField(source="server_tasks.count", read_only=True)
    completed_servers = serializers.SerializerMethodField()

    class Meta:
        model = InitJob
        fields = [
            "id", "template", "template_name", "group", "group_name",
            "status", "current_phase", "summary", "total_servers", "completed_servers",
            "start_time", "end_time", "created_at", "server_tasks",
        ]
        read_only_fields = ["id", "status", "current_phase", "summary", "start_time", "end_time", "created_at"]

    def get_completed_servers(self, obj):
        return obj.server_tasks.filter(status__in=["success", "failed", "skipped"]).count()


class InitJobListSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True, default=None)
    group_name = serializers.CharField(source="group.name", read_only=True)
    total_servers = serializers.IntegerField(source="server_tasks.count", read_only=True)
    completed_servers = serializers.SerializerMethodField()

    class Meta:
        model = InitJob
        fields = [
            "id", "template_name", "group_name", "status", "current_phase",
            "total_servers", "completed_servers", "start_time", "end_time", "created_at",
        ]

    def get_completed_servers(self, obj):
        return obj.server_tasks.filter(status__in=["success", "failed", "skipped"]).count()
