import logging
import uuid

from rest_framework.exceptions import NotFound

from enterprise_catalog.apps.api.v1.serializers import ContentMetadataSerializer
from enterprise_catalog.apps.api.v1.views.enterprise_customer import EnterpriseCustomerViewSet
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog

from django.utils.decorators import method_decorator
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST

from enterprise_catalog.apps.api.v1.decorators import (
    require_at_least_one_query_parameter,
)
from enterprise_catalog.apps.api.v1.utils import unquote_course_keys


logger = logging.getLogger(__name__)


class EnterpriseCustomerViewSetV2(EnterpriseCustomerViewSet):
    """
    Viewset for operations on enterprise customers.
    Although we don't have a specific EnterpriseCustomer model, this viewset handles operations that use an enterprise
    identifier to perform operations on their associated catalogs, etc.
    """
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
        requested_course_or_run_keys = unquote_course_keys(course_run_ids)

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
            contains_content_items = catalog.contains_content_keys(requested_course_or_run_keys + program_uuids, include_restricted=True)
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

    def get_metadata_item_serializer(self):
        """
        Gets the first matching serialized ContentMetadata for a requested ``content_identifier``
        associated with any of a requested ``customer_uuid``'s catalogs.
        """
        enterprise_catalogs = list(EnterpriseCatalog.objects.filter(
            enterprise_uuid=self.kwargs.get('enterprise_uuid')
        ))
        content_identifier = self.kwargs.get('content_identifier')
        serializer_context = {
            'skip_customer_fetch': bool(self.request.query_params.get('skip_customer_fetch', '').lower()),
        }

        try:
            # Search for matching metadata if the value of the requested
            # identifier is a valid UUID.
            content_uuid = uuid.UUID(content_identifier)
            for catalog in enterprise_catalogs:
                content_with_uuid = catalog.content_metadata_with_restricted.filter(content_uuid=content_uuid)
                if content_with_uuid:
                    return ContentMetadataSerializer(
                        content_with_uuid.first(),
                        context={'enterprise_catalog': catalog, **serializer_context},
                    )
        except ValueError:
            # Otherwise, search for matching metadata as a content key
            for catalog in enterprise_catalogs:
                content_with_key = catalog.get_matching_content(content_keys=[content_identifier], include_restricted=True)
                if content_with_key:
                    return ContentMetadataSerializer(
                        content_with_key.first(),
                        context={'enterprise_catalog': catalog, **serializer_context},
                    )
        # If we've made it here without finding a matching ContentMetadata record,
        # assume no matching record exists and raise a 404.
        raise NotFound(detail='No matching content in any catalog for this customer')

