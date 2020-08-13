# -*- coding: utf-8 -*-
"""
Algolia api client code.
"""

import logging

from algoliasearch.search_client import SearchClient
from django.conf import settings


logger = logging.getLogger(__name__)


class AlgoliaSearchClient:
    """
    Object builds an API client to make calls to an Algolia index.
    """

    ALGOLIA_APPLICATION_ID = settings.ALGOLIA.get('APPLICATION_ID')
    ALGOLIA_API_KEY = settings.ALGOLIA.get('API_KEY')
    # Temporarily prefer the new algolia index if it exists
    ALGOLIA_INDEX_NAME = settings.ALGOLIA.get('INDEX_NAME_NEW') or settings.ALGOLIA.get('INDEX_NAME')

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
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                'Could not initialize %s index in Algolia: %s',
                self.ALGOLIA_INDEX_NAME,
                exc,
            )
            self.algolia_index = None

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
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                'Unable to set settings for Algolia\'s %s index: %s',
                self.ALGOLIA_INDEX_NAME,
                exc,
            )

    def partially_update_index(self, algolia_objects):
        """
        Performs a partial update of the Algolia index with the specified data.

        If an object with the same `objectID` already exists in Algolia, it will be
        updated. If Algolia is unaware of an object, a new one will be created.

        Arguments:
            algolia_objects (list): A list of payload objects to index into Algolia
        """
        if not self.algolia_index:
            logger.error('Algolia index does not exist. Did you initialize it?')
            return

        try:
            # Add algolia_objects to the Algolia index
            response = self.algolia_index.partial_update_objects(algolia_objects, {
                'createIfNotExists': True,
            })
            object_ids = []
            for response in response.raw_responses:
                object_ids += response.get('objectIDs', [])
                logger.info(
                    'Successfully indexed %d courses in Algolia\'s %s index.',
                    len(object_ids),
                    self.ALGOLIA_INDEX_NAME,
                )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                'Could not index %d course(s) in Algolia\'s %s index: %s',
                len(algolia_objects),
                self.ALGOLIA_INDEX_NAME,
                exc,
            )
