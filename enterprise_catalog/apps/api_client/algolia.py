"""
Algolia api client code.
"""

import logging
from datetime import timedelta

from algoliasearch.exceptions import AlgoliaException
from algoliasearch.search_client import SearchClient
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from enterprise_catalog.apps.catalog.utils import localized_utcnow


logger = logging.getLogger(__name__)


class AlgoliaSearchClient:
    """
    Object builds an API client to make calls to an Algolia index.
    """

    def __init__(self):
        self._client = None
        self.algolia_index = None
        self.replica_index = None

    @property
    def algolia_application_id(self):
        return settings.ALGOLIA.get('APPLICATION_ID')

    @property
    def algolia_api_key(self):
        return settings.ALGOLIA.get('API_KEY')

    @property
    def algolia_search_api_key(self):
        return settings.ALGOLIA.get('SEARCH_API_KEY')

    @property
    def algolia_index_name(self):
        return settings.ALGOLIA.get('INDEX_NAME')

    @property
    def algolia_replica_index_name(self):
        return settings.ALGOLIA.get('REPLICA_INDEX_NAME')

    def init_index(self):
        """
        Initializes an index within Algolia. Initializing an index will create it if it doesn't exist.
        """
        if not self.algolia_index_name or not self.algolia_replica_index_name:
            logger.error('Could not initialize Algolia index due to missing index name.')
            return

        if not self.algolia_application_id or not self.algolia_api_key:
            logger.error(
                'Could not initialize Algolia\'s %s index due to missing Algolia settings: %s',
                self.algolia_index_name,
                ['APPLICATION_ID', 'API_KEY'],
            )
            return

        # Create SearchClient
        self._client = SearchClient.create(self.algolia_application_id, self.algolia_api_key)

        # Initialize Algolia indices
        if self.algolia_index_name:
            try:
                self.algolia_index = self._client.init_index(self.algolia_index_name)
            except AlgoliaException as exc:
                logger.exception(
                    'Could not initialize %s index in Algolia due to an exception.',
                    self.algolia_index_name,
                )
                raise exc
        if self.algolia_replica_index_name:
            try:
                self.replica_index = self._client.init_index(self.algolia_replica_index_name)
            except AlgoliaException as exc:
                logger.exception(
                    'Could not initialize %s index in Algolia due to an exception.',
                    self.algolia_replica_index_name,
                )
                raise exc

    def set_index_settings(self, index_settings, primary_index=True):
        """
        Set default settings to use for the Algolia index.

        Note: This will override manual updates to the index configuration on the
        Algolia dashboard but ensures consistent settings (configuration as code).

        Arguments:
            settings (dict): A dictionary of Algolia settings.
        """
        if not self.algolia_index:
            logger.error('Algolia index does not exist. Did you initialize it?')
            return

        try:
            if primary_index:
                self.algolia_index.set_settings(index_settings)
            else:
                self.replica_index.set_settings(index_settings)
        except AlgoliaException as exc:
            logger.exception(
                'Unable to set settings for Algolia\'s %s index due to an exception.',
                self.algolia_index_name,
            )
            raise exc

    def index_exists(self):
        """
        Returns whether the index exists in Algolia.
        """
        if not self.algolia_index or not self.replica_index:
            logger.error('Algolia index does not exist. Did you initialize it?')
            return False

        primary_exists = self.algolia_index.exists()
        replica_exists = self.replica_index.exists()
        if not primary_exists:
            logger.warning(
                'Index with name %s does not exist in Algolia.',
                self.algolia_index_name,
            )
        if not replica_exists:
            logger.warning(
                'Index with name %s does not exist in Algolia.',
                self.algolia_replica_index_name,
            )

        return primary_exists and replica_exists

    def replace_all_objects(self, algolia_objects):  # pragma: no cover
        """
        Clears all objects from the index and replaces them with a new set of objects. The records are
        replaced in the index without any downtime due to an atomic reindex.

        See https://www.algolia.com/doc/api-reference/api-methods/replace-all-objects/ for more detials.

        Arguments:
            algolia_objects (list): List of objects to include in the Algolia index
        """
        if not self.index_exists():
            # index must exist to continue, nothing left to do
            return

        try:
            self.algolia_index.replace_all_objects(algolia_objects, {
                'safe': True,  # wait for asynchronous indexing operations to complete
            })
            logger.info('The %s Algolia index was successfully indexed.', self.algolia_index_name)
        except AlgoliaException as exc:
            logger.exception(
                'Could not index objects in the %s Algolia index due to an exception.',
                self.algolia_index_name,
            )
            raise exc

    def get_all_objects_associated_with_aggregation_key(self, aggregation_key):
        """
        Returns an array of Algolia object IDs associated with the given aggregation key.
        """
        objects = []
        if not self.index_exists():
            # index must exist to continue, nothing left to do
            return objects
        try:
            index_browse_iterator = self.algolia_index.browse_objects({
                "attributesToRetrieve": ["objectID"],
                "filters": f"aggregation_key:'{aggregation_key}'",
            })
            for hit in index_browse_iterator:
                objects.append(hit['objectID'])
        except AlgoliaException as exc:
            logger.exception(
                'Could not retrieve objects associated with aggregation key %s due to an exception.',
                aggregation_key,
            )
            raise exc
        return objects

    def remove_objects(self, object_ids):
        """
        Removes objects from the Algolia index.
        """
        if not self.index_exists():
            # index must exist to continue, nothing left to do
            return

        try:
            self.algolia_index.delete_objects(object_ids)
            logger.info(
                'The following objects were successfully removed from the %s Algolia index: %s',
                self.algolia_index_name,
                object_ids,
            )
        except AlgoliaException as exc:
            logger.exception(
                'Could not remove objects from the %s Algolia index due to an exception.',
                self.algolia_index_name,
            )
            raise exc

    def generate_secured_api_key(self, user_id, enterprise_catalog_query_uuids):
        """
        Generates a secured api key for the Algolia search API.
        The secured api key will be used to restrict the search results to only those
        that are associated with the given enterprise catalog query uuids.
        The secured api key will also be restricted to the given user id.
        Arguments:
            user_id (str): The user id to restrict the api key to.
            enterprise_catalog_query_uuids (list): The enterprise catalog query uuids to restrict the api key to.
        Returns:
            dict: A dictionary containing the secured api key and the expiration time.
            The expiration time is in ISO format.
        """
        if not self.algolia_search_api_key:
            logger.error(
                'Could not generate secured Algolia API key due to missing Algolia settings: %s',
                'SEARCH_API_KEY',
            )
            raise ImproperlyConfigured(
                'Cannot generate secured Algolia API key without the ALGOLIA.SEARCH_API_KEY in settings.'
            )

        expiration_time = getattr(settings, 'SECURED_ALGOLIA_API_KEY_EXPIRATION', 3600)  # Default to 1 hour
        valid_until_dt = localized_utcnow() + timedelta(seconds=expiration_time)
        valid_until_unix = int(valid_until_dt.timestamp())
        catalog_query_filter = ' OR '.join(
            [f'enterprise_catalog_query_uuids:{query_uuid}' for query_uuid in enterprise_catalog_query_uuids]
        )

        # Base secured API key restrictions
        restrictions = {
            'filters': catalog_query_filter,
            'validUntil': valid_until_unix,
            'userToken': user_id,
        }

        # Determine indices to restrict
        indices = []
        if self.algolia_index_name:
            indices.append(self.algolia_index_name)
        if self.algolia_replica_index_name:
            indices.append(self.algolia_replica_index_name)
        if indices:
            restrictions |= {'restrictIndices': indices}

        # Generate secured api key
        logger.info('[AlgoliaSearchClient.generate_secured_api_key] restrictions: %s', restrictions)
        try:
            secured_api_key = SearchClient.generate_secured_api_key(
                self.algolia_search_api_key,
                restrictions,
            )
        except AlgoliaException as exc:
            logger.exception('Could not generate secured Algolia API key due to an AlgoliaException.')
            raise exc

        # Return secured api key and expiration time
        iso_format = "%Y-%m-%dT%H:%M:%SZ"
        valid_until_iso = valid_until_dt.strftime(iso_format)
        return {
            'secured_api_key': secured_api_key,
            'valid_until': valid_until_iso,
        }
