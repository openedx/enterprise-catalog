from edx_rest_framework_extensions.auth.jwt.authentication import (
    JwtAuthentication,
)
from rest_framework import permissions, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import JSONRenderer
from rest_framework_xml.renderers import XMLRenderer

from enterprise_catalog.apps.api.v1.serializers import JobSerializer
from enterprise_catalog.apps.jobs.models import Job


class EnterpriseJobReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    A viewset for retrieving all the jobs for a given enterprise.
    """

    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [JSONRenderer, XMLRenderer]
    serializer_class = JobSerializer
    lookup_field = "enterprise_uuid"

    def get_queryset(self):
        """
        Returns a list of all the jobs associated with the given enterprise UUID.
        """
        enterprise_uuid = self.kwargs.get("enterprise_uuid")
        return Job.objects.filter(enterprises__enterprise_uuid=enterprise_uuid)
