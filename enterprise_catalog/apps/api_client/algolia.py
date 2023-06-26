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

    def __init__(self):
        self._client = None
        self.algolia_index = None

    def init_index(self):
        """
        Initializes an index within Algolia. Initializing an index will create it if it doesn't exist.
        """
        if not self.ALGOLIA_INDEX_NAME:
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
        except AlgoliaException as exc:
            logger.exception(
                'Could not initialize %s index in Algolia due to an exception.',
                self.ALGOLIA_INDEX_NAME,
            )
            raise exc

    def set_index_settings(self, index_settings):
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
            self.algolia_index.set_settings(index_settings)
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
        if not self.algolia_index:
            logger.error('Algolia index does not exist. Did you initialize it?')
            return False

        exists = self.algolia_index.exists()
        if not exists:
            logger.warning(
                'Index with name %s does not exist in Algolia.',
                self.ALGOLIA_INDEX_NAME,
            )

        return exists

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
