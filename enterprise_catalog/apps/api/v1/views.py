from django.utils.decorators import method_decorator
from edx_rbac.mixins import PermissionRequiredMixin
from edx_rest_framework_extensions.auth.bearer.authentication import (
    BearerAuthentication,
)
from edx_rest_framework_extensions.auth.jwt.authentication import (
    JwtAuthentication,
)
from rest_framework import viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_404_NOT_FOUND
from rest_framework.views import APIView
from rest_framework_xml.renderers import XMLRenderer

from enterprise_catalog.apps.api.tasks import update_catalog_metadata_task
from enterprise_catalog.apps.api.v1.decorators import (
    require_at_least_one_query_parameter,
)
from enterprise_catalog.apps.api.v1.serializers import (
    EnterpriseCatalogCreateSerializer,
    EnterpriseCatalogSerializer,
)
from enterprise_catalog.apps.api.v1.utils import unquote_course_keys
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    EnterpriseCatalog,
)


# class EnterpriseCatalogViewSet(viewsets.ModelViewSet):
class EnterpriseCatalogViewSet(PermissionRequiredMixin, viewsets.ModelViewSet):
    """ View for CRUD operations on Enterprise Catalogs """
    queryset = EnterpriseCatalog.objects.all().order_by('created')
    authentication_classes = [JwtAuthentication, BearerAuthentication, SessionAuthentication]
    renderer_classes = [JSONRenderer, XMLRenderer]
    permission_required = 'enterprise.can_view_catalog'
    lookup_field = 'uuid'

    def get_serializer_class(self):
        request_action = getattr(self, 'action', None)
        if request_action == 'create':
            return EnterpriseCatalogCreateSerializer

        return EnterpriseCatalogSerializer

    @method_decorator(require_at_least_one_query_parameter('course_run_ids', 'program_uuids'))
    @action(detail=True)
    def contains_content_items(self, request, uuid, course_run_ids, program_uuids, **kwargs):
        """
        Returns whether or not the EnterpriseCatalog contains the specified content.

        Multiple course_run_ids and/or program_uuids query parameters can be sent to this view to check for their
        existence in the specified enterprise catalog.
        """
        course_run_ids = unquote_course_keys(course_run_ids)

        enterprise_catalog = self.get_object()
        contains_content_items = enterprise_catalog.contains_content_keys(course_run_ids + program_uuids)
        return Response({'contains_content_items': contains_content_items})

    @action(detail=True)
    def get_content_metadata(self, request, uuid, **kwargs):
        """
        Returns all the content linked to the specified catalog, ordered by content key.
        """
        enterprise_catalog = self.get_object()
        metadata = {
            'uuid': enterprise_catalog.uuid,
            'title': enterprise_catalog.title,
            'enterprise_customer': enterprise_catalog.enterprise_uuid,
            'count': 0,
            'previous': None, 'next': None,  # Kept for parity with edx-enterprise
            'results': [],
        }

        catalog_query = enterprise_catalog.catalog_query
        if not catalog_query:
            return Response(metadata)

        associated_metadata = catalog_query.contentmetadata_set.all()
        sorted_content_keys = sorted([metadata_chunk.content_key for metadata_chunk in associated_metadata])
        metadata['results'] = [ContentMetadata.objects.get(content_key=content_key).json_metadata for content_key
                               in sorted_content_keys]
        metadata['count'] = len(sorted_content_keys)

        return Response(metadata)


class EnterpriseCatalogRefreshDataFromDiscovery(APIView):
    """
    View to update metadata in Catalog with most recent data from Discovery service
    """
    def post(self, request, uuid):
        # ensure catalog exists before starting celery task
        if not EnterpriseCatalog.objects.filter(uuid=uuid):
            # respond with 400 status if catalog doesn't exist
            return Response(status=HTTP_404_NOT_FOUND)
        # call update function and respond
        async_task = update_catalog_metadata_task.delay(catalog_uuid=uuid)
        return Response({'async_task_id': async_task.task_id}, status=HTTP_200_OK)


class EnterpriseCustomerViewSet(viewsets.ViewSet):
    """
    Viewset for operations on enterprise customers.

    Although we don't have a specific EnterpriseCustomer model, this viewset handles operations that use an enterprise
    identifier to perform operations on their associated catalogs, etc.
    """
    authentication_classes = [JwtAuthentication, BearerAuthentication, SessionAuthentication]

    # Just a convenience so that `enterprise_uuid` becomes an argument on our detail routes
    lookup_field = 'enterprise_uuid'

    @method_decorator(require_at_least_one_query_parameter('course_run_ids', 'program_uuids'))
    @action(detail=True)
    def contains_content_items(self, request, enterprise_uuid, course_run_ids, program_uuids, **kwargs):
        """
        Returns whether or not the specified content is available for the given enterprise.
        """
        course_run_ids = unquote_course_keys(course_run_ids)

        customer_catalogs = EnterpriseCatalog.objects.filter(enterprise_uuid=enterprise_uuid)
        contains_content_items = False
        for catalog in customer_catalogs:
            contains_content_items = catalog.contains_content_keys(course_run_ids + program_uuids)
            # Break as soon as we find a catalog that contains the specified content
            if contains_content_items:
                break

        return Response({'contains_content_items': contains_content_items})
