import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.api.tasks import update_full_content_metadata_task
from enterprise_catalog.apps.catalog.constants import TASK_TIMEOUT
from enterprise_catalog.apps.catalog.management.utils import (
    get_all_content_keys,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Add full course metadata to ContentMetadata records',
    )

    def handle(self, *args, **options):
        all_content_keys = get_all_content_keys()
        async_task = update_full_content_metadata_task.delay(all_content_keys)
        message = (
            'Spinning off update_full_content_metadata_task (%s) from update_full_content_metadata command'
            ' to replace minimal json_metadata from /search/all/ with full json_metadata from /courses/.'
        )
        logger.info(message, async_task.task_id)

        # See https://docs.celeryproject.org/en/stable/reference/celery.result.html#celery.result.AsyncResult.get
        # for documentation
        async_result = async_task.get(
            timeout=TASK_TIMEOUT,
            propagate=True,
        )
        if async_task.successful():
            message = (
                'update_full_content_metadata task (%s) from update_full_content_metadata command finished'
                ' successfully with result %s'
            )
            logger.info(message, async_task.task_id, async_result)
