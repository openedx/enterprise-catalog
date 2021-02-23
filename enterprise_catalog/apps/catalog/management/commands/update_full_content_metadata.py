import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.api.tasks import update_full_content_metadata_task
from enterprise_catalog.apps.catalog.management.utils import (
    get_all_content_keys,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Add full course metadata to ContentMetadata records',
    )

    def handle(self, *args, **options):
        try:
            result = update_full_content_metadata_task.apply_async().get()
            message = (
                'update_full_content_metadata task from update_full_content_metadata command finished'
                ' successfully with result %s'
            )
            logger.info(message, result)
        except Exception as exc:
            # celery weirdly hijacks and prefixes the path of the below Exception
            # with `celery.backends.base` when it's raised.
            # So this block still catches only a specific error, just in a roundabout way.
            if type(exc).__name__ != 'TaskRecentlyRunError':
                raise
            else:
                logger.info(
                    'update_full_content_metadata_task was recently run prior to this command, '
                    'and was thus skipped during the execution of this command.'
                )
