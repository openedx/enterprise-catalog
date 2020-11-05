"""
Interfaces to the discovery API using a volatile cache.
"""
from logging import getLogger

from django.conf import settings
from django.core.cache import cache

from .constants import DISCOVERY_CATALOG_QUERY_CACHE_KEY_TPL
from .discovery import DiscoveryApiClient


LOGGER = getLogger(__name__)


class CatalogQueryMetadata:
    """
    Metadata for a given CatalogQuery from the Discovery API.

    Data is cached for 'settings.CATALOG_QUERY_CACHE_TIMEOUT' seconds.
    """
    def __init__(self, catalog_query_id):
        """
        Initialize a Catalog Query details instance and load data from
        cache or by using the Discovery API client.

        Arguments:
            catalog_query_id (int): Identifier for the Catalog Query
        """
        self.catalog_query_id = catalog_query_id
        self.catalog_query_data = self._get_catalog_query_metadata(catalog_query_id)

    @property
    def metadata(self):
        """
        Return catalog query metadata (will be an empty dict if unavailable)
        """
        return self.catalog_query_data

    def _get_catalog_query_metadata(self, catalog_query):
        """
        Retrieve JSON data containing Catalog Query metadata for the given catalog_query_id.
        Look in cache first, make call to Discovery API Client if not found.

        Arguments:
            catalog_query (CatalogQuery): Catalog Query object

        Returns:
            customer_data (dict): Enterprise Customer details OR
                Empty dictionary if no data found in cache or from API.
        """
        cache_key = DISCOVERY_CATALOG_QUERY_CACHE_KEY_TPL.format(id=self.catalog_query_id)
        catalog_query_data = cache.get(cache_key)
        if not catalog_query_data:
            client = DiscoveryApiClient()
            query_params = {
                # Omit non-active course runs from the course-discovery results
                'exclude_expired_course_run': True,
                # Increase number of results per page for the course-discovery response
                'page_size': 100,
                # Ensure paginated results are consistently ordered by `aggregation_key` and `start`
                'ordering': 'aggregation_key,start',
            }
            catalog_query_data = client.get_metadata_by_query(catalog_query, query_params=query_params)
            if not catalog_query_data:
                catalog_query_data = []
            cache.set(cache_key, catalog_query_data, settings.DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT)
            LOGGER.info('CatalogQueryDetails: CACHING CatalogQuery metadata with id %s for %s sec'.format(
                self.catalog_query_id,
                settings.DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT,
            ))
        return catalog_query_data


class AllCourseData:
    """
    All Course data from the Discovery API /courses endpoint.

    Data is cached for 'settings.DISCOVERY_COURSE_DATA_CACHE_TIMEOUT' seconds.
    """
    def __init__(self):
        """
        Initialize an AllCourseData instance and load data from
        cache or by using the Discovery API client.
        """
        self.all_course_data = _get_all_course_data()

    @property
    def course_data(self):
        """

        """
        return self.all_course_data


def _get_all_course_data():
    """
    TODO: implement
    """
    return 0
