from django.urls import path
from . import views

urlpatterns = [
    path("", views.TicketListView.as_view(), name="ticket-list"),
    path("<uuid:pk>/", views.TicketDetailView.as_view(), name="ticket-detail"),
    path("<uuid:pk>/assign/", views.TicketAssignView.as_view(), name="ticket-assign"),
    path("<uuid:pk>/transition/", views.TicketTransitionView.as_view(), name="ticket-transition"),
    path("<uuid:pk>/resolve/", views.TicketResolveView.as_view(), name="ticket-resolve"),
    path("<uuid:pk>/close/", views.TicketCloseView.as_view(), name="ticket-close"),
    path("<uuid:pk>/cancel/", views.TicketCancelView.as_view(), name="ticket-cancel"),
    path("<uuid:pk>/comments/", views.TicketCommentView.as_view(), name="ticket-comment"),
    path("<uuid:pk>/transitions/", views.TicketTransitionListView.as_view(), name="ticket-transitions"),
    path("flows/", views.TicketFlowListView.as_view(), name="ticket-flow-list"),
    path("sla-policies/", views.SLAPolicyListView.as_view(), name="sla-policy-list"),
    path("export/", views.TicketExportView.as_view(), name="ticket-export"),
    path("import/", views.TicketImportView.as_view(), name="ticket-import"),
    path("import/confirm/", views.TicketImportConfirmView.as_view(), name="ticket-import-confirm"),
]
