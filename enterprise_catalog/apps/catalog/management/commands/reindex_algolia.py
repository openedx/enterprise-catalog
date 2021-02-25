import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.api.tasks import (
    index_enterprise_catalog_courses_in_algolia_task,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Reindex course data in Algolia, adding on enterprise-specific metadata'
    )

    def handle(self, *args, **options):
        """
        Runs a celery task to reindex algolia.  Blocks until celery task returns.
        """
        try:
            result = index_enterprise_catalog_courses_in_algolia_task.apply_async().get()
            message = (
                'index_enterprise_catalog_courses_in_algolia_task from command reindex_algolia finished successfully.'
            )
            logger.info(message)
        except Exception as exc:
            # celery weirdly hijacks and prefixes the path of the below Exception
            # with `celery.backends.base` when it's raised.
            # So this block still catches only a specific error, just in a roundabout way.
            if type(exc).__name__ != 'TaskRecentlyRunError':
                raise
            else:
                logger.info(
                    'index_enterprise_catalog_courses_in_algolia_task was recently run prior to this command, '
                    'and was thus skipped during the execution of this command.'
                )
