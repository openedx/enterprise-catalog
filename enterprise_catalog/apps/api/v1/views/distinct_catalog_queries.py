from collections import defaultdict

from edx_rest_framework_extensions.auth.jwt.authentication import (
    JwtAuthentication,
)
from rest_framework import permissions
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.views import APIView

from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


class DistinctCatalogQueriesView(APIView):
    """
    View that, given a list of EnterpriseCustomerCatalog UUIDs, returns the
    number of distinct EnterpriseCatalogQueries used by the given set of catalogs.

    Also returns a mapping of each EnterpriseCatalogQuery to the UUIDs of
    EnterpriseCustomerCatalogs which use it to help ECS remediate any issues.
    """
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        """
        Given a list of EnterpriseCustomerCatalog UUIDs, return the number of distinct
        EnterpriseCatalogQueries used by the given set of catalogs.

        Also return data mapping each EnterpriseCatalogQuery to a list of the given
        EnterpriseCustomerCatalog UUIDs which use it. This data can be used by ECS to
        determine which catalogs map to incorrect queries.

        Request Data:
            - enterprise_catalog_uuids (list[str(UUID4)]): List of EnterpriseCustomerCatalog
            UUIDs to be used in a search for the number of distinct EnterpriseCatalogQuery
            objects used by the identified catalogs.

        Response Data:
            - count (int): number of distinct catalog queries used by given catalogs
            - catalog_uuids_by_catalog_query_id (dict{ int : list[str(UUID4)] }): dictionary
            with CatalogQuery ID as the key and the list of UUIDs for EnterpriseCustomerCatalogs
            that use the given ID as the value.
        """
        enterprise_catalog_uuids = request.data.get('enterprise_catalog_uuids', [])
        enterprise_catalogs = EnterpriseCatalog.objects.filter(uuid__in=enterprise_catalog_uuids)

        catalog_query_map = defaultdict(list)
        for catalog in enterprise_catalogs:
            catalog_query_map[catalog.catalog_query_id].append(str(catalog.uuid))

        response_data = {
            'num_distinct_query_ids': len(catalog_query_map.keys()),
            'catalog_uuids_by_catalog_query_id': catalog_query_map,
        }
        return Response(response_data, status=HTTP_200_OK)
