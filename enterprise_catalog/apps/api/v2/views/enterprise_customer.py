import logging

from rest_framework.decorators import action

from enterprise_catalog.apps.api.v1.views.enterprise_customer import (
    EnterpriseCustomerViewSet,
)
from enterprise_catalog.apps.catalog.models import ContentMetadata


logger = logging.getLogger(__name__)


class EnterpriseCustomerViewSetV2(EnterpriseCustomerViewSet):
    """
    V2 views for content metadata and catalog-content inclusion for retrieving.
    """
    def get_metadata_by_uuid(self, catalog, content_uuid):
        """
        Slightly more complicated - we have to find the content metadata
        record, regardless of catalog, with this uuid, then use `get_matching_content`
        on that record's content key.
        """
        record = ContentMetadata.objects.filter(content_uuid=content_uuid).first()
        if not record:
            return
        return catalog.get_matching_content(
            content_keys=[record.content_key],
            include_restricted=True,
        ).first()

    def get_metadata_by_content_key(self, catalog, content_key):
        return catalog.get_matching_content(
            content_keys=[content_key],
            include_restricted=True,
        ).first()

    def filter_content_keys(self, catalog, content_keys):
        return catalog.filter_content_keys(content_keys, include_restricted=True)

    def contains_content_keys(self, catalog, content_keys):
        return catalog.contains_content_keys(content_keys, include_restricted=True)

    @action(detail=False, methods=['get'], url_path='secured-algolia-api-key')
    def secured_algolia_api_key(self, request, enterprise_uuid, **kwargs):
        """
        There is no V2 version of this endpoint.
        """
        raise NotImplementedError('This endpoint is not available in V2.')  # pragma: no cover
