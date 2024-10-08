from asyncio.log import logger

from enterprise_catalog.apps.api.v1.views.enterprise_catalog_get_content_metadata import (
    EnterpriseCatalogGetContentMetadata,
)
from enterprise_catalog.apps.api.v2.utils import is_any_course_run_active


class EnterpriseCatalogGetContentMetadataV2(EnterpriseCatalogGetContentMetadata):
    """
    View for retrieving all the content metadata associated with a catalog.
    """
    def get_queryset(self, **kwargs):
        """
        Returns all the json of content metadata associated with the catalog.
        """
        # Avoids ordering the content metadata by any field on that model to avoid using a temporary table / filesort
        queryset = self.enterprise_catalog.content_metadata_with_restricted
        content_filter = kwargs.get('content_keys_filter')
        if content_filter:
            queryset = self.enterprise_catalog.get_matching_content(
                content_keys=content_filter,
                include_restricted=True
            )

        return queryset.order_by('catalog_queries')

    def is_active(self, item):
        """
        Determines if a content item is active.
        Args:
            item (ContentMetadata): The content metadata item to check.
        Returns:
            bool: True if the item is active, False otherwise.
                For courses, checks if any course run is active.
                For other content types, always returns True.
        """
        if item.content_type == 'course':
            active = is_any_course_run_active(
                item.json_metadata.get('course_runs', []))
            if not active:
                logger.debug(f'[get_content_metadata]: Content item {item.content_key} is not active.')
            return active
        return True
