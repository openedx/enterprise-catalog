import logging
import uuid

from algoliasearch.exceptions import AlgoliaException
from django.core.exceptions import ImproperlyConfigured
from django.utils.decorators import method_decorator
from drf_spectacular.utils import OpenApiExample, extend_schema
from edx_rbac.utils import get_decoded_jwt
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from enterprise_catalog.apps.api.v1.decorators import (
    require_at_least_one_query_parameter,
)
from enterprise_catalog.apps.api.v1.serializers import (
    ContentMetadataSerializer,
    SecuredAlgoliaAPIKeyErrorResponseSerializer,
    SecuredAlgoliaAPIKeyResponseSerializer,
)
from enterprise_catalog.apps.api.v1.utils import unquote_course_keys
from enterprise_catalog.apps.api.v1.views.base import BaseViewSet
from enterprise_catalog.apps.api_client.algolia import AlgoliaSearchClient
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
        Retrieves the appropriate object to use during edx-rbac's permission checks.

        This object is passed to the rule predicate(s).
        """
        return self.kwargs.get('enterprise_uuid')

    def filter_content_keys(self, catalog, content_keys):
        return catalog.filter_content_keys(content_keys)

    def contains_content_keys(self, catalog, content_keys):
        return catalog.contains_content_keys(content_keys)

    def get_metadata_by_uuid(self, catalog, content_uuid):
        return catalog.content_metadata.filter(content_uuid=content_uuid).first()

    def get_metadata_by_content_key(self, catalog, content_key):
        return catalog.get_matching_content(content_keys=[content_key]).first()

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
                status=status.HTTP_400_BAD_REQUEST
            )
        customer_catalogs = EnterpriseCatalog.objects.filter(enterprise_uuid=enterprise_uuid)

        any_catalog_contains_content_items = False
        catalogs_that_contain_course = []
        content_keys = requested_course_or_run_keys + program_uuids
        for catalog in customer_catalogs:
            if self.contains_content_keys(catalog, content_keys):
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
            if items_included := self.filter_content_keys(catalog, content_keys):
                filtered_content_keys = filtered_content_keys.union(items_included)

        response_data = {
            'filtered_content_keys': list(filtered_content_keys),
        }

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
                if content_with_uuid := self.get_metadata_by_uuid(catalog, content_uuid):
                    return ContentMetadataSerializer(
                        content_with_uuid,
                        context={'enterprise_catalog': catalog, **serializer_context},
                    )
        except ValueError:
            # Otherwise, search for matching metadata as a content key
            for catalog in enterprise_catalogs:
                if content_with_key := self.get_metadata_by_content_key(catalog, content_identifier):
                    return ContentMetadataSerializer(
                        content_with_key,
                        context={'enterprise_catalog': catalog, **serializer_context},
                    )
        # If we've made it here without finding a matching ContentMetadata record,
        # assume no matching record exists and raise a 404.
        raise NotFound(detail='No matching content in any catalog for this customer')

    @action(detail=True, methods=['get'])
    def content_metadata(self, customer_uuid, content_identifier, **kwargs):  # pylint: disable=unused-argument
        """
        Get endpoint for `/api/v1/enterprise-customer/{customer uuid}/content-metadata/{content identifier}`.
        Accepts both content uuids and content keys for the specific content metadata record requested.

        Accepts an optional `skip_customer_fetch` query parameter.
        If present and truthy, including this param will cause
        the serialized content metadata to not fetch related enterprise customer
        details from the edx-enterprise REST API.  Thus the presence of this
        query param means that the serialized 'content_last_modified' time
        will not take into account the *customer* modified time.  Additionally,
        it means that no 'enrollment_url' fields will be present in the serialied
        response.
        """
        serializer = self.get_metadata_item_serializer()
        return Response(serializer.data)

    @extend_schema(
        summary='Get secured Algolia API key for enterprise customer',
        description='Returns a secured Algolia API key for the given enterprise UUID. '
                    'The key can be used within frontends to access Algolia search API, '
                    'restricted with the enterprise\'s available catalog query UUIDs.',
        responses={
            200: SecuredAlgoliaAPIKeyResponseSerializer,
            400: SecuredAlgoliaAPIKeyErrorResponseSerializer,
        },
        tags=['Enterprise Customer'],
        examples=[
            OpenApiExample(
                'Secured Algolia API Key Response',
                value={
                    'algolia': {
                        'secured_api_key': '...',
                        'valid_until': '2025-02-28T12:00:00Z',
                    },
                    'catalog_uuids_to_catalog_query_uuids': {
                        'catalog_uuid_1': 'catalog_query_uuid_1',
                        'catalog_uuid_2': 'catalog_query_uuid_2',
                    },
                },
            ),
        ]
    )
    @action(detail=True, methods=['get'], url_path='secured-algolia-api-key')
    def secured_algolia_api_key(self, request, enterprise_uuid, **kwargs):
        """
        Returns a secured Algolia API key for the given enterprise UUID.
        The key can be used within frontends to access Algolia search API,
        restricted with the enterprise's available catalog query UUIDs.
        """
        # Fetch all EnterpriseCatalogs associated with the given enterprise_uuid
        enterprise_catalogs = EnterpriseCatalog.objects.filter(
            enterprise_uuid=enterprise_uuid
        ).select_related('catalog_query')
        algolia_api_key_error_message = 'Error generating secured Algolia API key.'

        # Return an error response if no EnterpriseCatalogs are found
        if not enterprise_catalogs:
            logger.error(
                f'No enterprise catalogs found for the given enterprise UUID: {enterprise_uuid}.'
            )
            error_response = {
                'user_message': algolia_api_key_error_message,
                'developer_message': 'No enterprise catalogs found for the specified enterprise customer.',
            }
            return Response(
                SecuredAlgoliaAPIKeyErrorResponseSerializer(error_response).data,
                status=status.HTTP_404_NOT_FOUND,
            )

        catalog_query_uuids = [
            enterprise_catalog.catalog_query.uuid for enterprise_catalog in enterprise_catalogs
            if enterprise_catalog.catalog_query
        ]
        # Return an error response if no CatalogQueries are found
        if not catalog_query_uuids:
            logger.error(
                f'No catalog queries found for the given enterprise UUID: {enterprise_uuid}.'
            )
            error_response = {
                'user_message': algolia_api_key_error_message,
                'developer_message': 'No catalog queries found for the specified enterprise customer.'
            }
            return Response(
                SecuredAlgoliaAPIKeyErrorResponseSerializer(error_response).data,
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # Create a mapping of catalog UUIDs to their corresponding catalog query UUIDs
        catalog_uuids_to_catalog_query_uuids = {
            str(catalog.uuid): str(catalog.catalog_query.uuid) if catalog.catalog_query else None
            for catalog in enterprise_catalogs
        }

        # Generate a secured Algolia API key using the AlgoliaSearchClient
        algolia_client = AlgoliaSearchClient()
        try:
            result = algolia_client.generate_secured_api_key(
                user_id=request.user.id,
                enterprise_catalog_query_uuids=catalog_query_uuids,
            )
        except ImproperlyConfigured as exc:
            logger.exception(
                f'Could not attempt generation of secured Algolia API key for '
                f'enterprise UUID {enterprise_uuid} due to improper configuration.'
            )
            error_response = {
                'user_message': algolia_api_key_error_message,
                'developer_message': exc,
            }
            return Response(
                SecuredAlgoliaAPIKeyErrorResponseSerializer(error_response).data,
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except AlgoliaException as exc:
            logger.exception(
                f'Secured Algolia API key generation failed for enterprise UUID {enterprise_uuid}'
            )
            error_response = {
                'user_message': algolia_api_key_error_message,
                'developer_message': exc
            }
            return Response(
                SecuredAlgoliaAPIKeyErrorResponseSerializer(error_response).data,
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # Serialize the response data
        response_data = {
            'algolia': {
                'secured_api_key': result.get('secured_api_key'),
                'valid_until': result.get('valid_until'),
            },
            'catalog_uuids_to_catalog_query_uuids': catalog_uuids_to_catalog_query_uuids,
        }
        return Response(SecuredAlgoliaAPIKeyResponseSerializer(response_data).data)
