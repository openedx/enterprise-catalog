from celery import task
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
from six.moves.urllib.parse import quote_plus, unquote
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.views import APIView

from enterprise_catalog.apps.api.v1.decorators import (
    require_at_least_one_query_parameter,
)
from enterprise_catalog.apps.api.v1.serializers import (
    EnterpriseCatalogCreateSerializer,
    EnterpriseCatalogSerializer,
)
from enterprise_catalog.apps.catalog.models import (
    EnterpriseCatalog,
    update_contentmetadata_from_discovery,
)


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

    def get(self, request):
        resp = str(dir(self))
        return Response(resp, status=HTTP_200_OK)

    @task(bind=True)
    def post(self, request):
        uuid = request.data.get("uuid")
        # call update function
        update_contentmetadata_from_discovery(uuid)
        return Response(uuid, status=HTTP_200_OK)
