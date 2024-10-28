import logging

from enterprise_catalog.apps.api.v1.views.enterprise_customer import (
    EnterpriseCustomerViewSet,
)


logger = logging.getLogger(__name__)


class EnterpriseCustomerViewSetV2(EnterpriseCustomerViewSet):
    """
    V2 views for content metadata and catalog-content inclusion for retrieving.
    """
    def get_metadata_by_uuid(self, catalog, content_uuid):
        return catalog.content_metadata_with_restricted.filter(content_uuid=content_uuid).first()

    def get_metadata_by_content_key(self, catalog, content_key):
        return catalog.get_matching_content(content_keys=[content_key], include_restricted=True).first()

    def filter_content_keys(self, catalog, content_keys):
        return catalog.filter_content_keys(content_keys, include_restricted=True)

    def contains_content_keys(self, catalog, content_keys):
        return catalog.contains_content_keys(content_keys, include_restricted=True)
