import logging

from celery import shared_task
from celery_utils.logged_task import LoggedTask

from enterprise_catalog.apps.catalog import filters
from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    EnterpriseCatalog,
)


logger = logging.getLogger(__name__)


@shared_task(base=LoggedTask)
def compare_catalog_queries_to_filters_task():
    logger.info('compare_catalog_queries_to_filters starting...')
    # NOTE: No need to exclude restricted runs because they are already filtered out via content_type.
    for content_metadata in ContentMetadata.objects.filter(content_type=COURSE):
        for enterprise_catalog in EnterpriseCatalog.objects.all():
            try:
                discovery_included = content_metadata in enterprise_catalog.content_metadata
                match = filters.does_query_match_content(
                    enterprise_catalog.catalog_query.content_filter,
                    content_metadata.json_metadata
                )
                does_discovery_agree_with_filter = discovery_included == match
                logger.info(
                    'compare_catalog_queries_to_filters '
                    f'enterprise_catalog={enterprise_catalog.uuid}, '
                    f'content_key={content_metadata.content_key}, '
                    f'discovery_included={discovery_included}, '
                    f'filter_match={match}, '
                    f'does_discovery_agree_with_filter={does_discovery_agree_with_filter}'
                )
            except filters.QueryFilterException:
                logger.exception(
                    'compare_catalog_queries_to_filters '
                    'filter exception '
                    f'enterprise_catalog={enterprise_catalog.uuid}, '
                    f'content_metadata={content_metadata.content_key}'
                )
    logger.info('compare_catalog_queries_to_filters complete.')
