import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.catalog.tasks import (
    compare_catalog_queries_to_filters_task,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Compare the Enterprise Catalog Query results to our own Catalog Filter'
    )

    def handle(self, *args, **options):
        """
        Compare the Enterprise Catalog Query results to our own Catalog Filter vai task
        """
        logger.info("compare_catalog_queries_to_filters queuing task...")
        compare_catalog_queries_to_filters_task.s()
