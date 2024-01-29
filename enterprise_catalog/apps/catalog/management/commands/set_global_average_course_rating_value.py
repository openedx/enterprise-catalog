import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.catalog.algolia_utils import (
    set_global_course_review_avg,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Fetch ContentMetadata records, read the course review values and save the average to py-cache.'
    )

    def handle(self, *args, **options):
        """
        Fetch ContentMetadata records, read the course review values and save the average to py-cache.
        """
        logger.info("compare_catalog_queries_to_filters queuing task...")
        set_global_course_review_avg()
