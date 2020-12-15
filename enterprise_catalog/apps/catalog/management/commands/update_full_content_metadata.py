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
        all_content_keys = get_all_content_keys()
        result = update_full_content_metadata_task.run(all_content_keys)
        message = (
            'update_full_content_metadata task from update_full_content_metadata command finished'
            ' successfully with result %s'
        )
        logger.info(message, result)
