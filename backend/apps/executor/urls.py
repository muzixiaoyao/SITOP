from django.urls import path
from . import views

urlpatterns = [
    path("groups/<uuid:group_pk>/check-connectivity/", views.ConnectivityCheckView.as_view(), name="connectivity-check"),
    path("groups/<uuid:group_pk>/execute-command/", views.CommandExecutionView.as_view(), name="execute-command"),
]
