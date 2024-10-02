from enterprise_catalog.apps.api.v1.views.enterprise_customer import EnterpriseCustomerViewSet


class EnterpriseCustomerViewSetV2(EnterpriseCustomerViewSet):
    """
    Viewset for operations on enterprise customers.

    Although we don't have a specific EnterpriseCustomer model, this viewset handles operations that use an enterprise
    identifier to perform operations on their associated catalogs, etc.
    """
