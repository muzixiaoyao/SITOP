from django.urls import path
from . import views

urlpatterns = [
    path("repository/files/", views.RepositoryFileListView.as_view(), name="repository-file-list"),
    path("repository/files/upload/", views.RepositoryFileUploadView.as_view(), name="repository-file-upload"),
    path("repository/files/delete/", views.RepositoryFileDeleteView.as_view(), name="repository-file-delete"),
    path("repository/files/download/", views.RepositoryFileDownloadView.as_view(), name="repository-file-download"),
]
