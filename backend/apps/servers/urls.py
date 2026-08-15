from django.urls import path
from . import views

urlpatterns = [
    # Group endpoints
    path("groups/", views.ServerGroupListView.as_view(), name="group-list"),
    path("groups/<uuid:pk>/", views.ServerGroupDetailView.as_view(), name="group-detail"),
    path("groups/<uuid:pk>/patrol/", views.GroupPatrolView.as_view(), name="group-patrol"),
    # Server endpoints under a group
    path("groups/<uuid:group_pk>/servers/", views.ServerListView.as_view(), name="server-list"),
    path("groups/<uuid:group_pk>/servers/batch/", views.ServerBatchCreateView.as_view(), name="server-batch-create"),
    path("groups/<uuid:group_pk>/servers/import/", views.ServerImportView.as_view(), name="server-import"),
    path("groups/<uuid:group_pk>/servers/export/", views.ServerExportView.as_view(), name="server-export"),
    # Individual server
    path("servers/<uuid:pk>/", views.ServerDetailView.as_view(), name="server-detail"),
    # All servers (cross-group)
    path("servers/", views.ServerAllView.as_view(), name="server-all"),
    # Batch operations
    path("servers/batch/connectivity/", views.ServerBatchConnectivityView.as_view(), name="server-batch-connectivity"),
    path("servers/batch/credential/", views.ServerBatchCredentialUpdateView.as_view(), name="server-batch-credential"),
    path("servers/batch/delete/", views.ServerBatchDeleteView.as_view(), name="server-batch-delete"),
    path("servers/batch/group-move/", views.ServerBatchGroupMoveView.as_view(), name="server-batch-group-move"),
    path("servers/batch/group-add/", views.ServerBatchGroupAddView.as_view(), name="server-batch-group-add"),
]
