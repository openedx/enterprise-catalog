import logging
import uuid

from rest_framework.exceptions import NotFound

from enterprise_catalog.apps.api.v1.serializers import ContentMetadataSerializer
from enterprise_catalog.apps.api.v1.views.enterprise_customer import EnterpriseCustomerViewSet
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


logger = logging.getLogger(__name__)


class EnterpriseCustomerViewSetV2(EnterpriseCustomerViewSet):
    """
    Viewset for operations on enterprise customers.

    Although we don't have a specific EnterpriseCustomer model, this viewset handles operations that use an enterprise
    identifier to perform operations on their associated catalogs, etc.
    """
    def get_metadata_item_serializer(self):
        """
        Gets the first matching serialized ContentMetadata for a requested ``content_identifier``
        associated with any of a requested ``customer_uuid``'s catalogs.
        """
        enterprise_catalogs = list(EnterpriseCatalog.objects.filter(
            enterprise_uuid=self.kwargs.get('enterprise_uuid')
        ))
        content_identifier = self.kwargs.get('content_identifier')
        serializer_context = {
            'skip_customer_fetch': bool(self.request.query_params.get('skip_customer_fetch', '').lower()),
        }

        try:
            # Search for matching metadata if the value of the requested
            # identifier is a valid UUID.
            content_uuid = uuid.UUID(content_identifier)
            for catalog in enterprise_catalogs:
                content_with_uuid = catalog.content_metadata_with_restricted.filter(content_uuid=content_uuid)
                if content_with_uuid:
                    return ContentMetadataSerializer(
                        content_with_uuid.first(),
                        context={'enterprise_catalog': catalog, **serializer_context},
                    )
        except ValueError:
            # Otherwise, search for matching metadata as a content key
            for catalog in enterprise_catalogs:
                content_with_key = catalog.get_matching_content(content_keys=[content_identifier], include_restricted=True)
                if content_with_key:
                    return ContentMetadataSerializer(
                        content_with_key.first(),
                        context={'enterprise_catalog': catalog, **serializer_context},
                    )
        # If we've made it here without finding a matching ContentMetadata record,
        # assume no matching record exists and raise a 404.
        raise NotFound(detail='No matching content in any catalog for this customer')
