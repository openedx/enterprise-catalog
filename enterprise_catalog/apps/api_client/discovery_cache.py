"""
Interfaces to the discovery API using a volatile cache.
"""
from logging import getLogger

from django.conf import settings
from django.core.cache import cache

from enterprise_catalog.apps.api_client.constants import (
    DISCOVERY_CATALOG_QUERY_CACHE_KEY_TPL,
)
from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient


LOGGER = getLogger(__name__)

_CACHE_MISS = object()


class CatalogQueryMetadata:
    """
    Metadata for a given CatalogQuery from the Discovery API.

    Data is cached for 'settings.CATALOG_QUERY_CACHE_TIMEOUT' seconds.
    """
    def __init__(self, catalog_query):
        """
        Initialize a Catalog Query details instance and load data from
        cache or by using the Discovery API client.

        Arguments:
            catalog_query (CatalogQuery): Catalog Query to retrieve metadata for
        """
        self.catalog_query = catalog_query
        self.catalog_query_data = self._get_catalog_query_metadata(catalog_query)

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
        cache_key = DISCOVERY_CATALOG_QUERY_CACHE_KEY_TPL.format(id=self.catalog_query.id)
        catalog_query_data = cache.get(cache_key, _CACHE_MISS)
        if catalog_query_data is not _CACHE_MISS:
            LOGGER.info('Cache HIT for CatalogQuery id=%s', self.catalog_query.id)
        else:
            client = DiscoveryApiClient()
            catalog_query_data = client.get_metadata_by_query(catalog_query)
            if not catalog_query_data:
                catalog_query_data = []

            # cache.add() will not attempt to update the cache if the key specified is already present
            # this is fine here, because we know we just encountered a cache miss on our key.
            # add() returns a boolean letting us know if it stored anything in the cache
            # Debugging: force ignore_exc off to see what exception is getting raise
            # on the cache adds.
            if hasattr(cache, '_options'):
                cache._options['ignore_exc'] = False  # pylint: disable=protected-access
            cache_add_success = False
            try:
                cache_add_success = cache.add(
                    cache_key,
                    catalog_query_data,
                    settings.DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT,
                )
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception('Cache add fail %s', exc)
            finally:
                if hasattr(cache, '_options'):
                    cache._options['ignore_exc'] = True  # pylint: disable=protected-access

            if cache_add_success:
                LOGGER.info(
                    'CatalogQueryDetails: CACHED CatalogQuery metadata with id %s for %s sec',
                    self.catalog_query.id,
                    settings.DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT,
                )
            else:
                LOGGER.info('Cache ADD FAIL for CatalogQuery id=%s', self.catalog_query.id)
        return catalog_query_data
