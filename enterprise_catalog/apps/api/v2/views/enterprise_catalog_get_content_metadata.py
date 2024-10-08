from enterprise_catalog.apps.api.v1.views.enterprise_catalog_get_content_metadata import EnterpriseCatalogGetContentMetadata


class EnterpriseCatalogGetContentMetadataV2(EnterpriseCatalogGetContentMetadata):
    """
    View for retrieving all the content metadata associated with a catalog.
    """
    def get_queryset(self, **kwargs):
        """
        Returns all of the json of content metadata associated with the catalog.
        """
        # Avoids ordering the content metadata by any field on that model to avoid using a temporary table / filesort
        queryset = self.enterprise_catalog.content_metadata_with_restricted
        content_filter = kwargs.get('content_keys_filter')
        if content_filter:
            queryset = self.enterprise_catalog.get_matching_content(content_keys=content_filter, include_restricted=True)

        return queryset.order_by('catalog_queries')
