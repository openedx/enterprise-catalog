import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.catalog import filters
from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    EnterpriseCatalog,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Compare the Enterprise Catalog Query results to our own Catalog Filter'
    )

    def handle(self, *args, **options):
        """
        Cook it.
        """
        logger.info('compare_catalog_queries_to_filters starting...')
        for content_metadata in ContentMetadata.objects.filter(content_type=COURSE):
            for enterprise_catalog in EnterpriseCatalog.objects.all():
                discovery_included = content_metadata in enterprise_catalog.content_metadata
                match = filters.does_query_match_content(
                    enterprise_catalog.catalog_query.content_filter,
                    content_metadata.json_metadata
                )
                logger.info(
                    'compare_catalog_queries_to_filters '
                    f'enterprise_catalog={enterprise_catalog.uuid}, '
                    f'content_metadata={content_metadata.content_key}, '
                    f'discovery_included={discovery_included}, '
                    f'filter_match={match}'
                )
        logger.info('compare_catalog_queries_to_filters complete.')
