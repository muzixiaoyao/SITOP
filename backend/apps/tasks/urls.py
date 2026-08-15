from django.urls import path
from . import views

urlpatterns = [
    path("templates/", views.TemplateListView.as_view(), name="template-list"),
    path("templates/<uuid:pk>/", views.TemplateDetailView.as_view(), name="template-detail"),
    path("jobs/", views.JobListView.as_view(), name="job-list"),
    path("jobs/<uuid:pk>/", views.JobDetailView.as_view(), name="job-detail"),
    path("jobs/<uuid:pk>/cancel/", views.JobCancelView.as_view(), name="job-cancel"),
    path("jobs/<uuid:pk>/completion-matrix/", views.CompletionMatrixView.as_view(), name="completion-matrix"),
]
