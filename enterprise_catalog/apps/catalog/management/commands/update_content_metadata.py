import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.api.tasks import update_catalog_metadata_task
from enterprise_catalog.apps.catalog.models import CatalogQuery


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Update Content Metadata, along with the associations of Catalog Queries and Content Metadata, for all'
        ' Enterprise Catalogs'
    )

    def handle(self, *args, **options):
        for catalog_query in CatalogQuery.objects.all():
            update_catalog_metadata_task.delay(catalog_query_id=catalog_query.id)
            message = (
                'Spinning off update_catalog_metadata_task from update_content_metadata command'
                ' to update content_metadata for catalog query %s'
            )
            logger.info(message, catalog_query)
