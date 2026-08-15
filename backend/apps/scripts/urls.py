from django.urls import path
from . import views

urlpatterns = [
    path("", views.ScriptListView.as_view(), name="script-list"),
    path("<uuid:pk>/", views.ScriptDetailView.as_view(), name="script-detail"),
    path("<uuid:pk>/versions/", views.ScriptVersionListView.as_view(), name="script-versions"),
    path("<uuid:pk>/test-run/", views.ScriptTestRunView.as_view(), name="script-test-run"),
]
