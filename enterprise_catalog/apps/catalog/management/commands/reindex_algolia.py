import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.api.tasks import (
    index_enterprise_catalog_courses_in_algolia_task,
)


logger = logging.getLogger(__name__)

# keep attributes from course objects that we explicitly want in Algolia
ALGOLIA_FIELDS = [
    'availability',
    'additional_information',
    'card_image_url',
    'enterprise_catalog_uuids',
    'enterprise_customer_uuids',
    'entitlements',
    'expected_learning_items',
    'extra_description',
    'faq',
    'full_description',
    'key',  # for links to course about pages from the Learner Portal search page
    'language',
    'level_type',
    'objectID',  # required by Algolia, e.g. "course-{uuid}"
    'outcome',
    'owners',
    'programs',
    'recent_enrollment_count',
    'short_description',
    'subjects',
    'syllabus_raw',
    'title',
    'uuid',
]

# default configuration for the index
ALGOLIA_INDEX_SETTINGS = {
    'searchableAttributes': [
        'unordered(title)',
        'unordered(full_description)',
        'unordered(short_description)',
        'unordered(additional_information)',
        'owners.name',
    ],
    'attributesForFaceting': [
        'enterprise_catalog_uuids',
        'enterprise_customer_uuids',
        'availability',
        'language',
        'level_type',
        'owners.name',
        'programs.type',
        'subjects.name',
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

    def handle(self, *args, **options):
        """
        Spin off task to reindex course data in Algolia.
        """
        async_task = index_enterprise_catalog_courses_in_algolia_task.delay(
            algolia_fields=ALGOLIA_FIELDS,
            algolia_settings=ALGOLIA_INDEX_SETTINGS,
        )
        message = (
            'Spinning off task index_enterprise_catalog_courses_in_algolia_task (%s) from'
            ' the reindex_algolia command to reindex course data in Algolia.'
        )
        logger.info(message, async_task.task_id)
