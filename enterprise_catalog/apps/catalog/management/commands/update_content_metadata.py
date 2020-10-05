import logging
from uuid import UUID

from celery import chord
from django.core.management.base import BaseCommand

from enterprise_catalog.apps.api.tasks import (
    update_catalog_metadata_task,
    update_full_content_metadata_task,
)
from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    EnterpriseCatalog,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Updates Content Metadata, along with the associations of Catalog Queries and Content Metadata. '
        'Example usage with --catalog_uuids: '
        './manage.py update_content_metadata --catalog_uuids {catalog_uuid_a} {catalog_uuid_b} ...'
    )

    def add_arguments(self, parser):
        """
        Add required arguments to the parser.
        """
        parser.add_argument(
            '--catalog_uuids',
            dest='catalog_uuids',
            required=False,
            nargs='+',
            type=UUID,
            metavar='ENTERPRISE_CATALOG_UUID',
            help='If provided, only updates content metadata for the specified catalog',
        )
        super(Command, self).add_arguments(parser)

    def _run_update_catalog_metadata_task(self, catalog_query):
        message = (
            'Spinning off update_catalog_metadata_task from update_content_metadata command'
            ' to update content_metadata for catalog query %s.'
        )
        logger.info(message, catalog_query)
        return update_catalog_metadata_task.s(catalog_query_id=catalog_query.id)

    def _run_update_full_content_metadata_task(self, *args, **kwargs):
        message = (
            'Spinning off update_full_content_metadata_task from update_content_metadata command'
            ' to replace minimal json_metadata from /search/all/ with full json_metadata from /courses/.'
        )
        logger.info(message)
        return update_full_content_metadata_task.s()

    def handle(self, *args, **options):
        # find all CatalogQuery records used by at least one EnterpriseCatalog to avoid
        # calling /search/all/ for a CatalogQuery that is not currently used by any catalogs.
        catalog_queries = CatalogQuery.objects.filter(enterprise_catalogs__isnull=False).distinct()

        catalog_uuids = options.get('catalog_uuids')
        if catalog_uuids:
            enterprise_catalogs = EnterpriseCatalog.objects.filter(uuid__in=catalog_uuids)
            catalog_queries = catalog_queries.filter(enterprise_catalogs__in=enterprise_catalogs).distinct()
            message = (
                'Updating {} unique CatalogQuery(s) for EnterpriseCatalog(s) with uuid(s): {}'
            ).format(catalog_queries.count(), catalog_uuids)
            logger.info(message)

        # create a group of celery tasks that run in parallel to create/update ContentMetadata records
        # and associate those with the appropriate CatalogQuery(s). once all those tasks succeed, run a
        # callback to update the json_metadata of ContentMetadata records with content type "course"
        # with the full course metadata from /courses/.
        result = chord(
            [
                self._run_update_catalog_metadata_task(catalog_query)
                for catalog_query in catalog_queries
            ]
        )(self._run_update_full_content_metadata_task())

        if result.ready() and result.successful():
            message = (
                'ContentMetadata records were successfully associated with their respective'
                ' CatalogQuery(s) and ContentMetadata records with content type of "%s" were'
                ' updated to include full course metadata.'
            )
            logger.info(message, COURSE)
        else:
            message = (
                'Could not successfully complete all async tasks spun off from the command. Check'
                ' the stack trace above for more details.'
            )
            logger.error(message)
