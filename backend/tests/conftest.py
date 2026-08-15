import pytest
from apps.accounts.models import Tenant, User


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="测试租户")


@pytest.fixture
def admin_user(db, tenant):
    return User.objects.create_user(
        username="admin", password="testpass123", tenant=tenant, role="admin",
    )


@pytest.fixture
def operator_user(db, tenant):
    return User.objects.create_user(
        username="operator", password="testpass123", tenant=tenant, role="operator",
    )
