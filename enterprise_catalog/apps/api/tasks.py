from celery import shared_task

from enterprise_catalog.apps.catalog.models import (
    update_contentmetadata_from_discovery,
)


@shared_task(bind=True)
# pylint: disable=unused-argument
def update_catalog_metadata_task(self, catalog_query_id):
    update_contentmetadata_from_discovery(catalog_query_id)
