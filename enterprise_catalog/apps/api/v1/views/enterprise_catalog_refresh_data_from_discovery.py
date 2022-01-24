from celery import chain
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.views import APIView

from enterprise_catalog.apps.api.tasks import (
    index_enterprise_catalog_in_algolia_task,
    update_catalog_metadata_task,
    update_full_content_metadata_task,
)
from enterprise_catalog.apps.api.v1.views.base import BaseViewSet
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


class EnterpriseCatalogRefreshDataFromDiscovery(BaseViewSet, APIView):
    """
    View to update metadata with data from the Discovery service and also index course metadata in Algolia.
    """
    permission_required = 'catalog.has_admin_access'

    def get_permission_object(self):
        """
        Retrieves the apporpriate object to use during edx-rbac's permission checks.

        This object is passed to the rule predicate(s).
        """
        uuid = self.kwargs.get('uuid')
        enterprise_catalog = get_object_or_404(EnterpriseCatalog, uuid=uuid)
        return str(enterprise_catalog.enterprise_uuid)

    def post(self, request, uuid):
        enterprise_catalog = get_object_or_404(EnterpriseCatalog, uuid=uuid)
        catalog_query_id = enterprise_catalog.catalog_query.id

        # Use immutable signatures so task results from a parent task are not passed as arguments to a child task.
        async_update_metadata_chain = chain(
            update_catalog_metadata_task.si(catalog_query_id),
            update_full_content_metadata_task.si(),
            index_enterprise_catalog_in_algolia_task.si(),
        )
        async_task = async_update_metadata_chain.apply_async()

        return Response({'async_task_id': async_task.task_id}, status=HTTP_200_OK)
