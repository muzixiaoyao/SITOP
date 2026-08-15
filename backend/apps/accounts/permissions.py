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
