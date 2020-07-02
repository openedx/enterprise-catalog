import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.api.tasks import (
    index_enterprise_catalog_courses_in_algolia_task,
)
from enterprise_catalog.apps.api_client.algolia import AlgoliaSearchClient
from enterprise_catalog.apps.catalog.models import (
    content_metadata_with_type_course,
)


logger = logging.getLogger(__name__)

BATCH_SIZE = 250

# keep attributes from course objects that we explicitly want in Algolia
ALGOLIA_FIELDS = [
    'additional_information',
    'availability',
    'card_image_url',  # for display on course cards
    'enterprise_catalog_uuids',
    'enterprise_customer_uuids',
    'full_description',
    'key',  # for links to Course about pages from the Learner Portal search page
    'language',
    'level_type',
    'objectID',  # required by Algolia, e.g. "course-{uuid}"
    'partners',
    'programs',
    'recent_enrollment_count',
    'short_description',
    'subjects',
    'title',
]

# default configuration for the index
ALGOLIA_INDEX_SETTINGS = {
    'searchableAttributes': [
        'unordered(title)',
        'unordered(full_description)',
        'unordered(short_description)',
        'unordered(additional_information)',
        'partners',
    ],
    'attributesForFaceting': [
        'availability',
        'enterprise_catalog_uuids',
        'enterprise_customer_uuids',
        'language',
        'level_type',
        'partners',
        'programs',
        'subjects',
    ],
    'unretrievableAttributes': [
        'enterprise_catalog_uuids',
        'enterprise_customer_uuids',
    ],
    'customRanking': [
        'desc(recent_enrollment_count)',
    ],
}


class Command(BaseCommand):
    help = (
        'Reindex course data in Algolia, adding on enterprise-specific metadata'
    )

    def batch(self, iterable, batch_size=1):
        """
        Break up an iterable into equal-sized batches.

        Arguments:
            iterable (e.g. list): an iterable to batch
            batch_size (int): the size of each batch. Defaults to 1.
        Returns:
            generator: iterates through each batch of an iterable
        """
        iterable_len = len(iterable)
        for index in range(0, iterable_len, batch_size):
            yield iterable[index:min(index + batch_size, iterable_len)]

    def handle(self, *args, **options):
        """
        Initializes and configures the settings for an Algolia index, and then spins off
        a task for each batch of content_keys to reindex course data in Algolia.
        """
        # initialize the Algolia index
        algolia_client = AlgoliaSearchClient()
        algolia_client.init_index()

        # configure the Algolia index
        algolia_client.set_index_settings(ALGOLIA_INDEX_SETTINGS)

        # retrieve content_keys for all ContentMetadata records with a content type of "course"
        course_content_metadata = content_metadata_with_type_course()
        content_metadata_keys = []
        if course_content_metadata:
            content_metadata_keys = [
                metadata['content_key']
                for metadata in course_content_metadata.values('content_key')
            ]

        # batch the content keys and spin off a new task for each batch
        for content_keys_batch in self.batch(content_metadata_keys, batch_size=BATCH_SIZE):
            async_task = index_enterprise_catalog_courses_in_algolia_task.delay(
                algolia_fields=ALGOLIA_FIELDS,
                content_keys=content_keys_batch,
            )
            message = (
                'Spinning off task index_enterprise_catalog_courses_in_algolia_task (%s) from'
                ' the reindex_algolia command to reindex %d courses in Algolia.'
            )
            logger.info(message, async_task.task_id, len(content_keys_batch))
