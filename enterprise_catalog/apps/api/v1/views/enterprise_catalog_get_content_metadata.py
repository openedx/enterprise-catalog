from asyncio.log import logger
from collections import OrderedDict

from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from edx_rest_framework_extensions.paginators import DefaultPagination
from rest_framework.decorators import action
from rest_framework.generics import GenericAPIView
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework_xml.renderers import XMLRenderer

from enterprise_catalog.apps.api.v1.serializers import (
    ContentMetadataListResponseSerializer,
    ContentMetadataSerializer,
)
from enterprise_catalog.apps.api.v1.utils import is_any_course_run_active
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
    pagination_class = DefaultPagination
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
        Retrieves the appropriate object to use during edx-rbac's permission checks.

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
            queryset = self.enterprise_catalog.get_matching_content(content_keys=content_filter)

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
        return response

    @extend_schema(
        description=(
            "GET calls to the `enterprise-catalogs/{catalog_id}` endpoint return a list of all of the active courses "
            "in a specified course catalog. You can then make a GET call to the "
            "`/enterprise-catalogs/{catalog_id}/courses/{course_key}` endpoint to return details about a single course."
        ),
        parameters=[
            OpenApiParameter(
                name="content_keys",
                type=str,
                location=OpenApiParameter.QUERY,
                description=(
                    "A list of content keys to filter the results. "
                    "If not provided, all content metadata is returned."
                ),
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="A page number within the paginated result.",
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                description=f"Number of results to return per page. Defaults to {DefaultPagination.page_size}. "
                f"Maximum value is {DefaultPagination.max_page_size}.",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=ContentMetadataListResponseSerializer,
                description="Paginated list of dynamic content metadata for the catalog.",
                examples=[
                    OpenApiExample(
                        "Detailed Catalog Metadata Response",
                        description=(
                            "Illustrates a typical, dynamic data structure for a course, "
                            "including common nested fields like course_runs, owners, and subjects. "
                            "Note: The actual fields returned can vary."
                        ),
                        value={
                            "count": 20,
                            "next": "https://api.example.org/enterprise/v2/enterprise-catalogs/{catalog_id}?page=2",
                            "previous": None,
                            "results": [
                                {
                                    "aggregation_key": "course:edX+DemoX",
                                    "content_type": "course",
                                    "full_description": "<p><strong>This is a sample course description.</strong></p>",
                                    "key": "edX+DemoX",
                                    "short_description": "<p>This is a sample short description.</p>",
                                    "card_image_url": None,
                                    "image_url": "https://prod-discovery.edx-cdn.org/...",
                                    "uuid": "11111111-1111-1111-1111-111111111111",
                                    "title": "edX Demonstration Course",
                                    "seat_types": ["audit", "verified"],
                                    "course_runs": [
                                        {
                                            "key": "course-v1:edX+DemoX+2025_T1",
                                            "uuid": "22222222-2222-2222-2222-222222222222",
                                            "status": "published",
                                            "is_enrollable": True,
                                            "is_marketable": True,
                                            "availability": "Current",
                                            "min_effort": 1,
                                            "max_effort": 3,
                                            "weeks_to_complete": 4,
                                            "parent_content_key": "edX+DemoX",
                                            "enrollment_url": "https://enterprise.example.org/acme/course/edX+DemoX?..."
                                        }
                                    ],
                                    "owners": [
                                        {
                                            "uuid": "33333333-3333-3333-3333-333333333333",
                                            "key": "AdelaideX",
                                            "name": "University of Adelaide"
                                        }
                                    ],
                                    "subjects": [
                                        {
                                            "name": "Business & Management",
                                            "slug": "business-management"
                                        }
                                    ],
                                    "normalized_metadata": {
                                        "start_date": "2025-01-01T00:00:00Z",
                                        "end_date": "2025-06-01T00:00:00Z",
                                        "enroll_by_date": "2025-05-25T23:59:59Z",
                                        "content_price": 99.0
                                    },
                                    "parent_content_key": None,
                                    "content_last_modified": "2025-01-01T00:00:00Z",
                                    "enrollment_url": "https://enterprise.example.org/acme/course/edX+DemoX",
                                    "xapi_activity_id": "https://lms.example.org/xapi/activities/course/edX+DemoX",
                                    "active": True
                                }
                            ],
                        },
                    )
                ]
            )
        },
    )
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

    def is_active(self, item):
        """
        Determines if a content item is active.
        Args:
            item (ContentMetadata): The content metadata item to check.
        Returns:
            bool: True if the item is active, False otherwise.
                For courses, checks if any course run is active.
                For other content types, always returns True.
        """
        if item.content_type == 'course':
            active = is_any_course_run_active(
                item.json_metadata.get('course_runs', []))
            if not active:
                logger.debug(f'[get_content_metadata]: Content item {item.content_key} is not active.')
            return active
        return True

    @action(detail=True)
    def get_content_metadata(self, request, traverse_pagination, content_keys_filter):
        """
        Returns all the content metadata associated with the enterprise catalog.

        The parameter `traverse_pagination`, if provided, will collect the results onto a single page.

        The parameter `content_keys_filter`, if provided, will result in only content metadata associated with the
        provided content keys being returned.
        """
        queryset = self.filter_queryset(self.get_queryset(content_keys_filter=content_keys_filter))
        logger.debug(f'[get_content_metadata]: Original queryset length: {len(queryset)}, {self.enterprise_catalog}')

        # Always filter out inactive courses,
        # to ensure only active content is always returned via API
        
        queryset = [item for item in queryset if self.is_active(item)]
        filtered_queryset_length = len(queryset)
        logger.debug(f'[get_content_metadata]: Filtered queryset length: {filtered_queryset_length}, '
                         f'{self.enterprise_catalog}')
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
