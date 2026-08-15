from rest_framework import serializers
from .models import Script, ScriptVersion


class ScriptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Script
        fields = [
            "id", "name", "description", "script_type", "language",
            "content", "version", "parameter_schema", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "version", "created_at", "updated_at"]


class ScriptVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScriptVersion
        fields = ["id", "version", "content", "created_at"]
