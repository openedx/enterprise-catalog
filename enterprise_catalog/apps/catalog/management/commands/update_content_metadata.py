import logging

from celery import chord
from django.core.management.base import BaseCommand

from enterprise_catalog.apps.api.tasks import (
    update_catalog_metadata_task,
    update_full_content_metadata_task,
)
from enterprise_catalog.apps.catalog.constants import COURSE, TASK_TIMEOUT
from enterprise_catalog.apps.catalog.management.utils import (
    get_all_content_keys,
)
from enterprise_catalog.apps.catalog.models import CatalogQuery


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Updates Content Metadata, along with the associations of Catalog Queries and Content Metadata. '
        'Example usage with --catalog_uuids: '
        './manage.py update_content_metadata --catalog_uuids {catalog_uuid_a} {catalog_uuid_b} ...'
    )

    def _run_update_catalog_metadata_task(self, catalog_query):
        message = (
            'Spinning off update_catalog_metadata_task from update_content_metadata command'
            ' to update content_metadata for catalog query %s.'
        )
        logger.info(message, catalog_query)
        return update_catalog_metadata_task.s(catalog_query_id=catalog_query.id)

    def _run_update_full_content_metadata_task(self, *args, **kwargs):
        """
        Runs the `update_full_content_metadata` for all content keys.

        Note that the keys get filtered down to course content keys inside the task.
        """
        message = (
            'Spinning off update_full_content_metadata_task from update_content_metadata command'
            ' to replace minimal json_metadata from /search/all/ with full json_metadata from /courses/.'
        )
        logger.info(message)

        all_content_keys = get_all_content_keys()
        # task.si() is used as a shortcut for an immutable signature to avoid calling this with the results from the
        # previously run `update_catalog_metadata_task`.
        # https://docs.celeryproject.org/en/master/userguide/canvas.html#immutability
        return update_full_content_metadata_task.si(all_content_keys)

    def add_arguments(self, parser):
        # Argument to specify catalogs to update
        parser.add_argument(
            '--catalog_uuids',
            nargs='+',
        )

    def handle(self, *args, **options):
        if options['catalog_uuids'] is not None:
            # find all CatalogQuery records associated with EnterpriseCatalog UUIDs specified in the arguments
            catalog_queries = CatalogQuery.objects.filter(
                enterprise_catalogs__isnull=False
            ).filter(
                enterprise_catalogs__uuid__in=options['catalog_uuids']
            ).distinct()
        else:
            # find all CatalogQuery records used by at least one EnterpriseCatalog to avoid
            # calling /search/all/ for a CatalogQuery that is not currently used by any catalogs.
            catalog_queries = CatalogQuery.objects.filter(enterprise_catalogs__isnull=False).distinct()

        if not catalog_queries:
            logger.error('No matching CatalogQuery objects found. Exiting.')
            return

        # create a group of celery tasks that run in parallel to create/update ContentMetadata records
        # and associate those with the appropriate CatalogQuery(s). once all those tasks succeed, run a
        # callback to update the json_metadata of ContentMetadata records with content type "course"
        # with the full course metadata from /courses/.
        update_chord_task = chord(
            [
                self._run_update_catalog_metadata_task(catalog_query)
                for catalog_query in catalog_queries
            ]
        )(self._run_update_full_content_metadata_task())

        # See https://docs.celeryproject.org/en/stable/reference/celery.result.html#celery.result.AsyncResult.get
        # for documentation
        update_chord_result = update_chord_task.get(
            timeout=TASK_TIMEOUT,
            propagate=True,
        )
        if update_chord_task.successful():
            message = (
                'ContentMetadata records were successfully associated with their respective'
                ' CatalogQuery(s) and ContentMetadata records with content type of "%s" were'
                ' updated to include full course metadata. Task finished with result %s.'
            )
            logger.info(message, COURSE, update_chord_result)
