from django.urls import path
from . import views

urlpatterns = [
    path("jobs/<uuid:pk>/report/", views.JobReportView.as_view(), name="job-report"),
    path("jobs/<uuid:pk>/summary/", views.JobSummaryView.as_view(), name="job-summary"),
    path("stats/dashboard/", views.DashboardStatsView.as_view(), name="dashboard-stats"),
]
