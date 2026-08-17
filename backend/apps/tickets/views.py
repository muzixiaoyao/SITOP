from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from apps.accounts.permissions import WriteRequiresOperatorOrAbove, IsAdmin
from .models import Ticket, TicketFlow, SLAPolicy, TicketComment, Notification
from .engine import TicketEngine
from .serializers import (
    TicketListSerializer, TicketDetailSerializer, TicketCreateSerializer,
    TicketFlowSerializer, TicketFlowCreateSerializer,
    SLAPolicySerializer, TicketCommentSerializer, TicketTransitionSerializer,
    NotificationSerializer,
)


def get_tenant(request):
    return getattr(request, "tenant", None) or getattr(request.user, "tenant", None)


class TicketListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TicketCreateSerializer
        return TicketListSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Ticket.objects.filter(tenant=get_tenant(self.request))
        if user.role == "enterprise_user":
            qs = qs.filter(submitter=user)
        for param in ("type", "status", "priority"):
            val = self.request.query_params.get(param)
            if val:
                qs = qs.filter(**{param: val})
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(ticket_no__icontains=search))
        return qs.select_related("submitter", "assignee", "current_node")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        engine = TicketEngine()
        ticket = engine.create_ticket(data=serializer.validated_data, submitter=self.request.user)
        output = TicketDetailSerializer(ticket, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)


class TicketDetailView(generics.RetrieveAPIView):
    serializer_class = TicketDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Ticket.objects.filter(tenant=get_tenant(self.request))
        if user.role == "enterprise_user":
            qs = qs.filter(submitter=user)
        return qs.select_related("submitter", "assignee", "current_node", "sla_policy")


class TicketAssignView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk, tenant=get_tenant(request))
        from apps.accounts.models import User
        assignee = User.objects.get(id=request.data.get("assignee_id"))
        engine = TicketEngine()
        engine.assign(ticket, assignee, request.user)
        return Response({"status": "assigned"})


class TicketTransitionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk, tenant=get_tenant(request))
        from .models import TicketNode
        target_node = TicketNode.objects.get(id=request.data.get("node_id"))
        comment = request.data.get("comment", "")
        engine = TicketEngine()
        engine.transition(ticket, target_node, request.user, comment)
        return Response({"status": ticket.status})


class TicketResolveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk, tenant=get_tenant(request))
        resolution = request.data.get("resolution", "")
        engine = TicketEngine()
        engine.resolve(ticket, request.user, resolution)
        return Response({"status": "resolved"})


class TicketCloseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk, tenant=get_tenant(request))
        engine = TicketEngine()
        engine.close(ticket, request.user)
        return Response({"status": "closed"})


class TicketCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk, tenant=get_tenant(request))
        reason = request.data.get("reason", "")
        engine = TicketEngine()
        engine.cancel(ticket, request.user, reason)
        return Response({"status": "cancelled"})


class TicketCommentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk, tenant=get_tenant(request))
        serializer = TicketCommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(ticket=ticket, author=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TicketTransitionListView(generics.ListAPIView):
    serializer_class = TicketTransitionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ticket = Ticket.objects.get(pk=self.kwargs["pk"], tenant=get_tenant(self.request))
        return ticket.transitions.select_related("from_node", "to_node", "operator")


class TicketFlowListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TicketFlowCreateSerializer
        return TicketFlowSerializer

    def get_queryset(self):
        return TicketFlow.objects.filter(
            Q(tenant=get_tenant(self.request)) | Q(tenant__isnull=True)
        ).prefetch_related("nodes")


class SLAPolicyListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = SLAPolicySerializer
    queryset = SLAPolicy.objects.all()


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)[:20]


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notif = Notification.objects.get(pk=pk, user=request.user)
        notif.is_read = True
        notif.save(update_fields=["is_read"])
        return Response({"status": "read"})


class NotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"status": "all_read"})


class NotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"count": count})
