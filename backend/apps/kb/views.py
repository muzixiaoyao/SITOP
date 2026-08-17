from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q, Count, F
from apps.accounts.permissions import IsAdmin
from .models import Article, ArticleCategory
from .serializers import ArticleListSerializer, ArticleDetailSerializer, ArticleCategorySerializer


class ArticleListView(generics.ListAPIView):
    serializer_class = ArticleListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Article.objects.filter(is_published=True).select_related("category", "author")


class ArticleDetailView(generics.RetrieveAPIView):
    serializer_class = ArticleDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        return Article.objects.filter(is_published=True)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        Article.objects.filter(pk=instance.pk).update(view_count=F("view_count") + 1)
        return super().retrieve(request, *args, **kwargs)


class ArticleSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        if not q:
            return Response([])
        articles = Article.objects.filter(
            is_published=True,
        ).filter(
            Q(title__icontains=q) | Q(content__icontains=q) | Q(tags__icontains=q)
        ).select_related("category")[:20]
        return Response(ArticleListSerializer(articles, many=True).data)


class ArticleManageView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ArticleDetailSerializer
        return ArticleListSerializer

    def get_queryset(self):
        return Article.objects.all().select_related("category", "author")

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class ArticleUpdateView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = ArticleDetailSerializer
    queryset = Article.objects.all()


class CategoryListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ArticleCategorySerializer

    def get_queryset(self):
        return ArticleCategory.objects.annotate(
            article_count=Count("articles", filter=Q(articles__is_published=True))
        )

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsAdmin()]
        return super().get_permissions()
