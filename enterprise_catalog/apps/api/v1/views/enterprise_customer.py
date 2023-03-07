import logging
import uuid

from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from edx_rbac.utils import get_decoded_jwt
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST

from enterprise_catalog.apps.api.v1.decorators import (
    require_at_least_one_query_parameter,
)
from enterprise_catalog.apps.api.v1.serializers import ContentMetadataSerializer
from enterprise_catalog.apps.api.v1.utils import unquote_course_keys
from enterprise_catalog.apps.api.v1.views.base import BaseViewSet
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


logger = logging.getLogger(__name__)


class EnterpriseCustomerViewSet(BaseViewSet):
    """
    Viewset for operations on enterprise customers.

    Although we don't have a specific EnterpriseCustomer model, this viewset handles operations that use an enterprise
    identifier to perform operations on their associated catalogs, etc.
    """
    permission_required = 'catalog.has_learner_access'
    # Just a convenience so that `enterprise_uuid` becomes an argument on our detail routes
    lookup_field = 'enterprise_uuid'

    def get_serializer_context(self):
        return {"request": self.request}

    def check_permissions(self, request):
        """
        Helper to log information from Auth token on
        PermissionDenied errors.
        See https://openedx.atlassian.net/browse/ENT-4885
        """
        try:
            super().check_permissions(request)
        except PermissionDenied:
            decoded_jwt = get_decoded_jwt(request)
            message = (
                'PermissionDenied for user_id (from JWT) %s and EnterpriseCustomer %s in '
                'contains_content_items. JWT roles: %s',
            )
            logger.exception(
                message,
                decoded_jwt.get('user_id'),
                self.kwargs.get('enterprise_uuid'),
                decoded_jwt.get('roles'),
            )
            raise

    def get_permission_object(self):
        """
        Retrieves the apporpriate object to use during edx-rbac's permission checks.

        This object is passed to the rule predicate(s).
        """
        return self.kwargs.get('enterprise_uuid')

    @method_decorator(require_at_least_one_query_parameter('course_run_ids', 'program_uuids'))
    @action(detail=True)
    def contains_content_items(self, request, enterprise_uuid, course_run_ids, program_uuids, **kwargs):
        """
        Returns whether or not the specified content is available for the given enterprise.
        ---
        parameters:
            - name: course_run_ids
              description: Ids of the course runs to check availability of
              paramType: query
            - name: program_uuids
              description: Uuids of the programs to check availability of
              paramType: query
            - name: get_catalog_list
              description: [Old parameter] Return a list of catalogs in which the course / program is present
              paramType: query
            - name: get_catalogs_containing_specified_content_ids
              description: Return a list of catalogs in which the course / program is present
              paramType: query
        """
        get_catalogs_containing_specified_content_ids = request.GET.get(
            'get_catalogs_containing_specified_content_ids', False
        )
        get_catalog_list = request.GET.get('get_catalog_list', False)
        course_run_ids = unquote_course_keys(course_run_ids)

        try:
            uuid.UUID(enterprise_uuid)
        except ValueError as exc:
            logger.warning(
                f"Could not parse catalogs from provided enterprise uuid: {enterprise_uuid}. "
                f"Query failed with exception: {exc}"
            )
            return Response(
                f'Error: invalid enterprice customer uuid: "{enterprise_uuid}" provided.',
                status=HTTP_400_BAD_REQUEST
            )
        customer_catalogs = EnterpriseCatalog.objects.filter(enterprise_uuid=enterprise_uuid)

        any_catalog_contains_content_items = False
        catalogs_that_contain_course = []
        for catalog in customer_catalogs:
            contains_content_items = catalog.contains_content_keys(course_run_ids + program_uuids)
            if contains_content_items:
                any_catalog_contains_content_items = True
                if not (get_catalogs_containing_specified_content_ids or get_catalog_list):
                    # Break as soon as we find a catalog that contains the specified content
                    break
                catalogs_that_contain_course.append(catalog.uuid)

        response_data = {
            'contains_content_items': any_catalog_contains_content_items,
        }
        if (get_catalogs_containing_specified_content_ids or get_catalog_list):
            response_data['catalog_list'] = catalogs_that_contain_course
        return Response(response_data)

    @action(detail=True, methods=['post'])
    def filter_content_items(self, request, enterprise_uuid, **kwargs):
        """
        Filters the content items based on catalogs passed or all catalogs belonging to an enterprise.
        """
        customer_catalogs = request.data.get('catalog_uuids', [])
        content_keys = set(request.data.get('content_keys', []))
        if customer_catalogs:
            customer_catalogs = EnterpriseCatalog.objects.filter(uuid__in=customer_catalogs)
        else:
            customer_catalogs = EnterpriseCatalog.objects.filter(enterprise_uuid=enterprise_uuid)

        filtered_content_keys = set()
        for catalog in customer_catalogs:
            items_included = catalog.filter_content_keys(content_keys)
            if items_included:
                filtered_content_keys = filtered_content_keys.union(items_included)

        response_data = {
            'filtered_content_keys': list(filtered_content_keys),
        }

        return Response(response_data)

    def get_metadata_item_serializer(self, **kwargs):
        """
        Fetches the queryset of content metadata under a specific customer context for a request
        """
        # Grab the enterprise from the url params and fetch the catalogs belonging to the customer
        enterprise_uuid = self.kwargs.get('enterprise_uuid')
        enterprise_catalogs = EnterpriseCatalog.objects.filter(enterprise_uuid=enterprise_uuid)

        # Set the context IFF there exists only one customer catalog
        serializer_context = {}
        if len(enterprise_catalogs) == 1:
            serializer_context['enterprise_catalog'] = enterprise_catalogs.first()

        # Collect a queryset of all content under all of the customer's catalogs
        content_metadata_queryset = EnterpriseCatalog.objects.none()
        for catalog in enterprise_catalogs:
            content_metadata_queryset = content_metadata_queryset | catalog.content_metadata

        # Filter the queryset down to the desired content
        if content_identifier := self.kwargs.get('content_identifier'):
            try:
                uuid.UUID(content_identifier)
                content_filter = {'content_uuid': content_identifier}
            except ValueError:
                content_filter = {'content_key': content_identifier}
            content_metadata_queryset = get_object_or_404(content_metadata_queryset.filter(**content_filter)[:1])

        return ContentMetadataSerializer(content_metadata_queryset, context=serializer_context, many=False)

    @action(detail=True, methods=['get'])
    def content_metadata(self, customer_uuid, content_identifier, **kwargs):  # pylint: disable=unused-argument
        """
        Get endpoint for `/api/v1/enterprise-customer/{customer uuid}/content-metadata/{content identifier}`.
        Accepts both content uuids and content keys for the specific content metadata record requested
        """
        serializer = self.get_metadata_item_serializer()
        return Response(serializer.data)
