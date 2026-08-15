from rest_framework import serializers


class ConnectivityCheckResultSerializer(serializers.Serializer):
    server_id = serializers.UUIDField()
    hostname = serializers.CharField()
    ip = serializers.CharField()
    status = serializers.ChoiceField(choices=["success", "failed"])
    message = serializers.CharField(allow_blank=True)
    latency_ms = serializers.IntegerField(allow_null=True)


class CommandExecutionRequestSerializer(serializers.Serializer):
    command = serializers.CharField(max_length=4096)


class CommandExecutionResultSerializer(serializers.Serializer):
    server_id = serializers.UUIDField()
    hostname = serializers.CharField()
    exit_code = serializers.IntegerField()
    output = serializers.CharField()
    error = serializers.CharField()
