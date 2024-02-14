import uuid

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


# https://stackoverflow.com/questions/53847404/how-to-check-uuid-validity-in-python
def is_valid_uuid(val):
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False


# https://stackoverflow.com/questions/4578590/python-equivalent-of-filter-getting-two-output-lists-i-e-partition-of-a-list
def partition(pred, iterable):
    trues = []
    falses = []
    for item in iterable:
        if pred(item):
            trues.append(item)
        else:
            falses.append(item)
    return trues, falses


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
        Returns all content metadata objects filtered by an optional request query param (LIST) ``content_identifiers``
        """
        content_filters = self.request.query_params.getlist('content_identifiers')
        queryset = self.queryset
        if content_filters:
            content_uuids, content_keys = partition(is_valid_uuid, content_filters)
            if content_keys:
                queryset = queryset.filter(content_key__in=content_filters)
            if content_uuids:
                queryset = queryset.filter(content_uuid__in=content_filters)
        return queryset
