from collections import OrderedDict

from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from rest_framework.decorators import action
from rest_framework.generics import GenericAPIView
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework_xml.renderers import XMLRenderer

from enterprise_catalog.apps.api.v1.pagination import (
    PageNumberWithSizePagination,
)
from enterprise_catalog.apps.api.v1.serializers import ContentMetadataSerializer
from enterprise_catalog.apps.api.v1.views.base import BaseViewSet
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


class EnterpriseCatalogGetContentMetadata(BaseViewSet, GenericAPIView):
    """
    View for retrieving all the content metadata associated with a catalog.
    """
    permission_required = 'catalog.has_learner_access'
    serializer_class = ContentMetadataSerializer
    renderer_classes = [JSONRenderer, XMLRenderer]
    lookup_field = 'uuid'
    pagination_class = PageNumberWithSizePagination
    MAX_GET_CONTENT_KEYS = 100

    @cached_property
    def enterprise_catalog(self):
        """
        Helper for retrieving the specified enterprise catalog, or 404ing if it doesn't exist.
        """
        uuid = self.kwargs.get('uuid')
        return get_object_or_404(EnterpriseCatalog, uuid=uuid)

    def get_permission_object(self):
        """
        Retrieves the apporpriate object to use during edx-rbac's permission checks.

        This object is passed to the rule predicate(s).
        """
        return str(self.enterprise_catalog.enterprise_uuid)

    def get_queryset(self, **kwargs):
        """
        Returns all of the json of content metadata associated with the catalog.
        """
        # Avoids ordering the content metadata by any field on that model to avoid using a temporary table / filesort
        queryset = self.enterprise_catalog.content_metadata
        content_filter = kwargs.get('content_keys_filter')
        if content_filter:
            queryset = queryset.filter(content_key__in=content_filter)

        return queryset.order_by('catalog_queries')

    def get_response_with_enterprise_fields(self, response):
        """
        Add on the enterprise fields to the top level of the DRF response

        Args:
            response (HttpResponse): The existing DRF response to add on to

        Returns:
            HttpResponse: The new response with additional fields added on
        """
        response.data['uuid'] = self.enterprise_catalog.uuid
        response.data['title'] = self.enterprise_catalog.title
        response.data['enterprise_customer'] = self.enterprise_catalog.enterprise_uuid
        response.data.move_to_end('results')  # Place the results at the end of the response again
        return response

    @action(detail=True)
    def get(self, request, **kwargs):
        """
        GET view entry point to the `get_content_metadata` API

        Query params:
            (Optional) content_keys (list): list of content keys for which to fetch content metadata for. If no content
            keys are provided then all content under the catalog will be fetched.
        """
        content_keys_filter = request.query_params.getlist('content_keys')
        if content_keys_filter == "[]":
            content_keys_filter = []
        else:
            if len(content_keys_filter) > self.MAX_GET_CONTENT_KEYS:
                return Response(
                    f'get_content_metadata GET requests supports up to {self.MAX_GET_CONTENT_KEYS}. If more content'
                    f'keys required, please use a POST body.',
                    status=HTTP_400_BAD_REQUEST
                )

        traverse_pagination = request.query_params.get('traverse_pagination', False)

        return self.get_content_metadata(request, traverse_pagination, content_keys_filter)

    @action(detail=True)
    def get_content_metadata(self, request, traverse_pagination, content_keys_filter):
        """
        Returns all the content metadata associated with the enterprise catalog.

        The parameter `traverse_pagination`, if provided, will collect the results onto a single page.

        The parameter `content_keys_filter`, if provided, will result in only content metadata associated with the
        provided content keys being returned.
        """
        queryset = self.filter_queryset(self.get_queryset(content_keys_filter=content_keys_filter))
        context = self.get_serializer_context()
        context['enterprise_catalog'] = self.enterprise_catalog
        page = self.paginate_queryset(queryset)

        # Traverse pagination query parameter signals that we should collect the results onto a single page
        if page is not None and not traverse_pagination:
            serializer = ContentMetadataSerializer(page, context=context, many=True)
            paginated_response = self.get_paginated_response(serializer.data)
            return self.get_response_with_enterprise_fields(paginated_response)

        serializer = ContentMetadataSerializer(queryset, context=context, many=True)
        ordered_data = OrderedDict({
            'previous': None,
            'next': None,
            'count': len(queryset),
            'results': serializer.data,
        })
        response = Response(ordered_data)
        return self.get_response_with_enterprise_fields(response)
