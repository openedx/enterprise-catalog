import logging

from enterprise_catalog.apps.api.v1.views.enterprise_catalog_contains_content_items import (
    EnterpriseCatalogContainsContentItems,
)


logger = logging.getLogger(__name__)


class EnterpriseCatalogContainsContentItemsV2(EnterpriseCatalogContainsContentItems):
    """
    Viewset to indicate if given content keys are contained by a catalog, with
    restricted content taken into account.
    """
    def catalog_contains_content_items(self, content_keys):
        """
        Returns a boolean indicating whether all of the provided content_keys
        are contained by the catalog record associated with the current request.
        Takes restricted content into account.
        """
        enterprise_catalog = self.get_object()
        return enterprise_catalog.contains_content_keys(content_keys, include_restricted=True)
