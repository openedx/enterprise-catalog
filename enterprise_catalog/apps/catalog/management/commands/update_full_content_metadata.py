import logging

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from enterprise_catalog.apps.api.tasks import update_full_content_metadata_task


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Add full course metadata to ContentMetadata records',
    )

    def handle(self, *args, **options):
        update_full_content_metadata_task.delay()
        message = (
            'Spinning off update_full_content_metadata_task from update_full_content_metadata command'
            ' to replace minimal json_metadata from /search/all/ with full json_metadata from /courses/.'
        )
        logger.info(message)
