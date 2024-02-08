from edx_rest_framework_extensions.auth.jwt.authentication import (
    JwtAuthentication,
)
from rest_framework import permissions, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import JSONRenderer
from rest_framework_xml.renderers import XMLRenderer

from enterprise_catalog.apps.api.v1.pagination import (
    PageNumberWithSizePagination,
)
from enterprise_catalog.apps.api.v1.serializers import ContentMetadataSerializer
from enterprise_catalog.apps.catalog.models import ContentMetadata


class ContentMetadataView(viewsets.ReadOnlyModelViewSet):
    """
    View for retrieving and listing base content metadata.
    """
    serializer_class = ContentMetadataSerializer
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [JSONRenderer, XMLRenderer]
    queryset = ContentMetadata.objects.all()
    pagination_class = PageNumberWithSizePagination

    def get_queryset(self, **kwargs):
        """
        Returns all content metadata objects filtered by an optional request query param ``content_keys`` (LIST).
        """
        content_filter = kwargs.get('content_keys')
        queryset = self.queryset
        if content_filter:
            return queryset.filter(content_key__in=content_filter)
        return queryset
