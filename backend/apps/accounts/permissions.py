from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "admin"


class IsOperatorOrAbove(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ("admin", "operator")


class IsViewerOrAbove(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated


class WriteRequiresOperator(BasePermission):
    """GET/HEAD/OPTIONS allowed for everyone; writes require operator+."""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in ("admin", "operator")


class IsEnterpriseAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "enterprise_admin"


class IsICTStaff(BasePermission):
    """ICT 内部员工（admin / operator / viewer）"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in (
            "admin", "operator", "viewer"
        )


class IsEnterpriseUser(BasePermission):
    """企业用户（enterprise_admin / enterprise_user）"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in (
            "enterprise_admin", "enterprise_user"
        )


class WriteRequiresOperatorOrAbove(BasePermission):
    """GET/HEAD/OPTIONS allowed for all authenticated; writes require ICT staff or enterprise_admin."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in ("admin", "operator", "enterprise_admin")
