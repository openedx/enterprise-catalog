from django.utils.decorators import method_decorator
from edx_rest_framework_extensions.auth.bearer.authentication import (
    BearerAuthentication,
)
from edx_rest_framework_extensions.auth.jwt.authentication import (
    JwtAuthentication,
)
from rest_framework import permissions, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST
from rest_framework.views import APIView
from six.moves.urllib.parse import quote_plus, unquote

from enterprise_catalog.apps.api.tasks import update_catalog_metadata_task
from enterprise_catalog.apps.api.v1.decorators import (
    require_at_least_one_query_parameter,
)
from enterprise_catalog.apps.api.v1.serializers import (
    EnterpriseCatalogCreateSerializer,
    EnterpriseCatalogSerializer,
)
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


class EnterpriseCatalogViewSet(viewsets.ModelViewSet):
    """ View for CRUD operations on Enterprise Catalogs """
    queryset = EnterpriseCatalog.objects.all().order_by('created')
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    authentication_classes = [JwtAuthentication, BearerAuthentication, SessionAuthentication]
    lookup_field = 'uuid'

    def get_serializer_class(self):
        request_action = getattr(self, 'action', None)
        if request_action == 'create':
            return EnterpriseCatalogCreateSerializer

        return EnterpriseCatalogSerializer

    @method_decorator(require_at_least_one_query_parameter('course_run_ids', 'program_uuids'))
    @action(detail=True)
    def contains_content_items(self, request, uuid, course_run_ids, program_uuids):
        """
        Returns whether or not the EnterpriseCatalog contains the specified content.

        Multiple course_run_ids and/or program_uuids query parameters can be sent to this view to check for their
        existence in the specified enterprise catalog.
        """
        # Maintain plus characters in course run keys
        course_run_ids = [unquote(quote_plus(course_run_id)) for course_run_id in course_run_ids]

        enterprise_catalog = self.get_object()
        contains_content_items = enterprise_catalog.contains_content_keys(course_run_ids + program_uuids)
        return Response({'contains_content_items': contains_content_items})


class EnterpriseCatalogRefreshDataFromDiscovery(APIView):
    """
    View to update metadata in Catalog with most recent data from Discovery service
    """
    def post(self, request, uuid):
        # ensure catalog exists before starting celery task
        if not EnterpriseCatalog.objects.filter(uuid=uuid):
            # respond with 400 status if catalog doesn't exist
            return Response(status=HTTP_400_BAD_REQUEST)
        # call update function and respond
        async_task = update_catalog_metadata_task.delay(catalog_uuid=uuid)
        return Response({'async_task_id': async_task.task_id}, status=HTTP_200_OK)
