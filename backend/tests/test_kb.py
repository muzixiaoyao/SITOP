import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.accounts.models import Tenant, User
from apps.kb.models import Article, ArticleCategory


class TestKnowledgeBase(TestCase):
    def setUp(self):
        self.cat = ArticleCategory.objects.create(name="FAQ")
        self.tenant = Tenant.objects.create(name="ICT")
        self.user = User.objects.create_user(username="kb_user", password="pass", tenant=self.tenant, role="admin")
        self.client = APIClient()
        token = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def test_create_article(self):
        article = Article.objects.create(
            title="如何重置密码", slug="reset-password",
            content="## 步骤\n1. 登录管理后台\n2. 找到用户管理",
            category=self.cat, is_published=True, author=self.user,
        )
        assert article.title == "如何重置密码"
        assert article.slug == "reset-password"

    def test_article_list_api(self):
        Article.objects.create(title="文章1", slug="art-1", content="内容", category=self.cat, is_published=True, author=self.user)
        Article.objects.create(title="草稿", slug="draft", content="未发布", category=self.cat, is_published=False, author=self.user)
        resp = self.client.get("/api/kb/articles/")
        assert resp.status_code == 200
        assert len(resp.data["results"]) == 1

    def test_article_search(self):
        Article.objects.create(title="SSH连接失败", slug="ssh-fail", content="检查防火墙配置", category=self.cat, is_published=True, author=self.user)
        Article.objects.create(title="密码重置", slug="pwd-reset", content="忘记密码的处理流程", category=self.cat, is_published=True, author=self.user)
        resp = self.client.get("/api/kb/articles/search/?q=SSH")
        assert resp.status_code == 200
        assert len(resp.data) >= 1
        assert resp.data[0]["title"] == "SSH连接失败"
