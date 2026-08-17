from django.test import TestCase
from apps.accounts.models import Tenant, User


class TestRoleExtension(TestCase):
    def test_platform_admin_role_exists(self):
        tenant = Tenant.objects.create(name="ICT公司")
        # admin 角色即平台管理员（向后兼容，保留 admin 值）
        user = User.objects.create_user(
            username="plat_admin", password="pass", tenant=tenant, role="admin"
        )
        self.assertEqual(user.role, "admin")
        self.assertEqual(user.get_role_display(), "平台管理员")

    def test_enterprise_admin_role_exists(self):
        tenant = Tenant.objects.create(name="客户企业A")
        user = User.objects.create_user(
            username="ent_admin", password="pass", tenant=tenant, role="enterprise_admin"
        )
        self.assertEqual(user.role, "enterprise_admin")

    def test_enterprise_user_role_exists(self):
        tenant = Tenant.objects.create(name="客户企业B")
        user = User.objects.create_user(
            username="ent_user", password="pass", tenant=tenant, role="enterprise_user"
        )
        self.assertEqual(user.role, "enterprise_user")

    def test_operator_role_still_works(self):
        """向后兼容：operator 角色仍然可用"""
        tenant = Tenant.objects.create(name="测试租户")
        user = User.objects.create_user(
            username="op", password="pass", tenant=tenant, role="operator"
        )
        self.assertEqual(user.role, "operator")
