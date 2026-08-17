from django.urls import path
from . import views

urlpatterns = [
    path("articles/", views.ArticleListView.as_view(), name="kb-article-list"),
    path("articles/manage/", views.ArticleManageView.as_view(), name="kb-article-manage"),
    path("articles/manage/<uuid:pk>/", views.ArticleUpdateView.as_view(), name="kb-article-update"),
    path("articles/search/", views.ArticleSearchView.as_view(), name="kb-article-search"),
    path("articles/<slug:slug>/", views.ArticleDetailView.as_view(), name="kb-article-detail"),
    path("categories/", views.CategoryListView.as_view(), name="kb-category-list"),
]
