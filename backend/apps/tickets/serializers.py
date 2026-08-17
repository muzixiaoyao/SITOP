from rest_framework import serializers
from .models import (
    Ticket, TicketFlow, TicketNode, SLAPolicy,
    TicketTransition, TicketComment, TicketAttachment, Notification,
)


class SLAPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = SLAPolicy
        fields = "__all__"


class TicketNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketNode
        fields = ["id", "name", "order", "role_required", "is_terminal", "sla_hours", "auto_assign_rule"]


class TicketFlowSerializer(serializers.ModelSerializer):
    nodes = TicketNodeSerializer(many=True, read_only=True)

    class Meta:
        model = TicketFlow
        fields = ["id", "name", "ticket_type", "is_active", "nodes", "created_at"]


class TicketFlowCreateSerializer(serializers.ModelSerializer):
    nodes = TicketNodeSerializer(many=True, required=False)

    class Meta:
        model = TicketFlow
        fields = ["id", "name", "ticket_type", "is_active", "nodes"]

    def create(self, validated_data):
        nodes_data = validated_data.pop("nodes", [])
        flow = TicketFlow.objects.create(**validated_data)
        for node_data in nodes_data:
            TicketNode.objects.create(flow=flow, **node_data)
        return flow


class TicketCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = TicketComment
        fields = ["id", "author", "author_name", "content", "is_system", "created_at"]
        read_only_fields = ["author", "is_system"]


class TicketTransitionSerializer(serializers.ModelSerializer):
    from_node_name = serializers.CharField(source="from_node.name", read_only=True, default="")
    to_node_name = serializers.CharField(source="to_node.name", read_only=True, default="")
    operator_name = serializers.CharField(source="operator.username", read_only=True)

    class Meta:
        model = TicketTransition
        fields = ["id", "from_node", "from_node_name", "to_node", "to_node_name",
                  "operator", "operator_name", "comment", "duration_seconds", "created_at"]


class TicketListSerializer(serializers.ModelSerializer):
    submitter_name = serializers.CharField(source="submitter.username", read_only=True)
    assignee_name = serializers.CharField(source="assignee.username", read_only=True, default="")
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id", "ticket_no", "title", "type", "type_display",
            "priority", "priority_display", "status", "status_display",
            "submitter", "submitter_name", "assignee", "assignee_name",
            "created_at", "updated_at",
        ]


class TicketDetailSerializer(serializers.ModelSerializer):
    submitter_name = serializers.CharField(source="submitter.username", read_only=True)
    assignee_name = serializers.CharField(source="assignee.username", read_only=True, default="")
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    current_node_name = serializers.CharField(source="current_node.name", read_only=True, default="")
    sla_policy_detail = SLAPolicySerializer(source="sla_policy", read_only=True)
    comments = TicketCommentSerializer(many=True, read_only=True)
    transitions = TicketTransitionSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id", "ticket_no", "title", "description", "type", "type_display",
            "priority", "priority_display", "status", "status_display",
            "current_node", "current_node_name",
            "submitter", "submitter_name", "assignee", "assignee_name",
            "related_job", "sla_policy_detail",
            "first_response_at", "assigned_at", "resolved_at", "closed_at",
            "created_at", "updated_at",
            "comments", "transitions",
        ]


class TicketCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ["title", "description", "type", "priority", "related_job"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "type", "title", "content", "ticket", "is_read", "created_at"]
