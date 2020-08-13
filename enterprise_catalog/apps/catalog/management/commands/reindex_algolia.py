import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.api.tasks import (
    index_enterprise_catalog_courses_in_algolia_task,
)
from enterprise_catalog.apps.api_client.algolia import AlgoliaSearchClient
from enterprise_catalog.apps.catalog.models import (
    content_metadata_with_type_course,
)
from enterprise_catalog.apps.catalog.utils import batch


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
    'attributeForDistinct': 'key',
    'distinct': True,
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
        'partners.name',
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


def should_index_course(course_metadata):
    """
    Replicates the B2C index check of whether a certain course should be indexed for search.

    A course should only be indexed for algolia search if it has a non-indexed advertiseable course run, at least
    one owner, and a marketing url slug.
    The course-discovery check that the course's partner is edX is included by default as the discovery API filters
    to the request's site's partner.
    The discovery check that the course has an availability level was decided to be a duplicate check that the
    website team plans on removing.
    Original code:
    https://github.com/edx/course-discovery/blob/c6ac5329225e2f32cdf1d1da855d7c9d905b2576/course_discovery/apps/course_metadata/algolia_models.py#L218-L227

    Args:
        course (ContentMetadata): The ContentMetadata representing a course object.

    Returns:
        bool: Whether or not the course should be indexed by algolia.
    """
    course_json_metadata = course_metadata.json_metadata
    advertised_course_run_uuid = course_json_metadata.get('advertised_course_run_uuid')
    course_runs = course_json_metadata.get('course_runs')
    try:
        advertised_course_run = [run for run in course_runs if run.get('uuid') == advertised_course_run_uuid][0]
    except IndexError:
        # If there is no advertised course run we can immediately return False
        return False

    owners = course_json_metadata.get('owners', [])
    return (len(owners) > 0
            and bool(course_json_metadata.get('url_slug'))
            and not advertised_course_run.get('hidden'))


class Command(BaseCommand):
    help = (
        'Reindex course data in Algolia, adding on enterprise-specific metadata'
    )

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
        all_course_content_metadata = content_metadata_with_type_course()
        # Only use the course content metadata that should be indexed for Algolia using the B2C logic
        indexable_content_keys = [course_content_metadata.content_key for course_content_metadata
                                  in all_course_content_metadata if should_index_course(course_content_metadata)]

        # batch the content keys and spin off a new task for each batch
        for content_keys_batch in batch(indexable_content_keys, batch_size=BATCH_SIZE):
            async_task = index_enterprise_catalog_courses_in_algolia_task.delay(
                algolia_fields=ALGOLIA_FIELDS,
                content_keys=content_keys_batch,
            )
            message = (
                'Spinning off task index_enterprise_catalog_courses_in_algolia_task (%s) from'
                ' the reindex_algolia command to reindex %d courses in Algolia.'
            )
            logger.info(message, async_task.task_id, len(content_keys_batch))
