from django.utils.decorators import method_decorator
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework_xml.renderers import XMLRenderer

from enterprise_catalog.apps.api.v1.decorators import (
    require_at_least_one_query_parameter,
)
from enterprise_catalog.apps.api.v1.serializers import (
    EnterpriseCatalogSerializer,
)
from enterprise_catalog.apps.api.v1.utils import unquote_course_keys
from enterprise_catalog.apps.api.v1.views.base import BaseViewSet
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


class EnterpriseCatalogDiff(BaseViewSet, viewsets.ModelViewSet):
    """
    View to determine if an enterprise catalog contains certain content
    """
    queryset = EnterpriseCatalog.objects.all().order_by('created')
    renderer_classes = [JSONRenderer, XMLRenderer]
    serializer_class = EnterpriseCatalogSerializer
    http_method_names = ['get', 'post']
    permission_required = 'catalog.has_learner_access'
    lookup_field = 'uuid'
    MAX_GET_CONTENT_KEYS = 100

    def get_permission_object(self):
        """
        Retrieves the appropriate object to use during edx-rbac's permission checks.

        This object is passed to the rule predicate(s).
        """
        if self.kwargs.get('uuid'):
            enterprise_catalog = self.get_object()
            return str(enterprise_catalog.enterprise_uuid)
        return None

    @action(detail=True)
    def post(self, request, **kwargs):
        content_keys = []
        if request.data:
            content_keys = request.data.get('content_keys')
        return self.catalog_diff(content_keys)

    @method_decorator(require_at_least_one_query_parameter('content_keys'))
    @action(detail=True)
    def get(self, request, content_keys, **kwargs):
        if content_keys == "[]":
            content_keys = []
        else:
            if len(content_keys) > self.MAX_GET_CONTENT_KEYS:
                return Response(
                    f'catalog_diff GET requests supports up to {self.MAX_GET_CONTENT_KEYS}. If more content keys '
                    f'required, please use a POST body.',
                    status=HTTP_400_BAD_REQUEST
                )

        return self.catalog_diff(content_keys)

    def catalog_diff(self, content_keys):
        """
        Generate three buckets representing a diff between a list of content keys and what content exists under a
        catalog

        Params:
            content_keys: (list) A list of content key strings representing content under a catalog

        Response buckets:
            'items_not_found': A list of all content keys that were provided in the content_keys param that were not
            found under the catalog.
            'items_not_included': A list of sets of content keys that were found under the catalog but not provided in
            the content_keys param.
            'items_found': A list of dicts containing 'content_key's and 'date_updated' of content keys provided in the
            content_keys param that were found under the catalog.
        """
        content_keys = unquote_course_keys(content_keys)
        enterprise_catalog = self.get_object()
        items_not_found, items_not_included, items_found = enterprise_catalog.get_catalog_content_diff(content_keys)
        return Response({
            'items_not_found': items_not_found,
            'items_not_included': items_not_included,
            'items_found': items_found
        })
