from rest_framework import serializers
from .models import Article, ArticleCategory


class ArticleCategorySerializer(serializers.ModelSerializer):
    article_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ArticleCategory
        fields = ["id", "name", "order", "article_count"]


class ArticleListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    author_name = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = Article
        fields = ["id", "title", "slug", "category", "category_name", "tags",
                  "is_published", "view_count", "author_name", "created_at", "updated_at"]


class ArticleDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    author_name = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = Article
        fields = "__all__"
