from edx_rbac.mixins import PermissionRequiredMixin
from edx_rest_framework_extensions.auth.jwt.authentication import (
    JwtAuthentication,
)
from rest_framework import permissions, viewsets
from rest_framework.authentication import SessionAuthentication


class BaseViewSet(PermissionRequiredMixin, viewsets.ViewSet):
    """
    Base class for all enterprise catalog view sets.
    """
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]
