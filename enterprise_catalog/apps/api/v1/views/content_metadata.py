"""
Enterprise Catalog
"""
import uuid

from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from rest_framework import viewsets
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST
from rest_framework_xml.renderers import XMLRenderer

from enterprise_catalog.apps.api.v1.pagination import (
    PageNumberWithSizePagination,
)
from enterprise_catalog.apps.api.v1.serializers import ContentMetadataSerializer
from enterprise_catalog.apps.api.v1.views.base import BaseViewSet
from enterprise_catalog.apps.catalog.models import ContentMetadata
from enterprise_catalog.apps.catalog.rules import enterprises_with_admin_access


class ContentMetadataCRUDViewSet(BaseViewSet, viewsets.ModelViewSet):
    """ Viewset for CRUD operations on Content Metadata """
    serializer_class = ContentMetadataSerializer
    renderer_classes = [JSONRenderer, XMLRenderer]
    permission_required = 'catalog.has_learner_access'
    http_method_names = ['get', 'list']
    pagination_class = PageNumberWithSizePagination

    @cached_property
    def request_action(self):
        return getattr(self, 'action', None)

    def get_queryset(self, **kwargs):
        """
        Returns the queryset corresponding to all content metadata the request has access to.
        """
        if content_identifier := self.kwargs.get('pk'):
            try:
                uuid.UUID(content_identifier)
                content_filter = {'content_uuid': content_identifier}
            except ValueError:
                content_filter = {'content_key': content_identifier}
            queryset = ContentMetadata.objects.filter(**content_filter).order_by('created')
        else:
            queryset = ContentMetadata.objects.all().order_by('created')
        return queryset

    def retrieve(self, request, pk=None):
        """
        Get endpoint for `/api/v1/content-metadata/{content identifier}`. Accepts both content uuids and content keys
        """
        queryset = self.get_queryset()
        content = get_object_or_404(queryset)
        serializer = ContentMetadataSerializer(content)
        return Response(serializer.data)

    def list(self, request, **kwargs):
        """
        List endpoint for `/api/v1/content-metadata/`. Results are paginated and specific pages of content
        can be requested with the `page_size` query param.
        """
        queryset = self.get_queryset()
        serializer = ContentMetadataSerializer(queryset, many=True)
        return Response(serializer.data)
