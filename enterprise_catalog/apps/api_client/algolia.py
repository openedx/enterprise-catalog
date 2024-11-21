"""
Algolia api client code.
"""

import logging

from algoliasearch.exceptions import AlgoliaException
from algoliasearch.search_client import SearchClient
from django.conf import settings


logger = logging.getLogger(__name__)


class AlgoliaSearchClient:
    """
    Object builds an API client to make calls to an Algolia index.
    """

    ALGOLIA_APPLICATION_ID = settings.ALGOLIA.get('APPLICATION_ID')
    ALGOLIA_API_KEY = settings.ALGOLIA.get('API_KEY')
    ALGOLIA_INDEX_NAME = settings.ALGOLIA.get('INDEX_NAME')
    ALGOLIA_REPLICA_INDEX_NAME = settings.ALGOLIA.get('REPLICA_INDEX_NAME')

    def __init__(self):
        self._client = None
        self.algolia_index = None
        self.replica_index = None

    def init_index(self):
        """
        Initializes an index within Algolia. Initializing an index will create it if it doesn't exist.
        """
        if not self.ALGOLIA_INDEX_NAME or not self.ALGOLIA_REPLICA_INDEX_NAME:
            logger.error('Could not initialize Algolia index due to missing index name.')
            return

        if not self.ALGOLIA_APPLICATION_ID or not self.ALGOLIA_API_KEY:
            logger.error(
                'Could not initialize Algolia\'s %s index due to missing Algolia settings: %s',
                self.ALGOLIA_INDEX_NAME,
                ['APPLICATION_ID', 'API_KEY'],
            )
            return

        self._client = SearchClient.create(self.ALGOLIA_APPLICATION_ID, self.ALGOLIA_API_KEY)
        try:
            self.algolia_index = self._client.init_index(self.ALGOLIA_INDEX_NAME)
            self.replica_index = self._client.init_index(self.ALGOLIA_REPLICA_INDEX_NAME)
        except AlgoliaException as exc:
            logger.exception(
                'Could not initialize %s index in Algolia due to an exception.',
                self.ALGOLIA_INDEX_NAME,
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
                self.ALGOLIA_INDEX_NAME,
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
                self.ALGOLIA_INDEX_NAME,
            )
        if not replica_exists:
            logger.warning(
                'Index with name %s does not exist in Algolia.',
                self.ALGOLIA_REPLICA_INDEX_NAME,
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
            logger.info('The %s Algolia index was successfully indexed.', self.ALGOLIA_INDEX_NAME)
        except AlgoliaException as exc:
            logger.exception(
                'Could not index objects in the %s Algolia index due to an exception.',
                self.ALGOLIA_INDEX_NAME,
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
                self.ALGOLIA_INDEX_NAME,
                object_ids,
            )
        except AlgoliaException as exc:
            logger.exception(
                'Could not remove objects from the %s Algolia index due to an exception.',
                self.ALGOLIA_INDEX_NAME,
            )
            raise exc
