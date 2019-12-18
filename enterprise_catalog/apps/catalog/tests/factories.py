import factory
from uuid import uuid4

from enterprise_catalog.apps.catalog.models import CatalogQuery, EnterpriseCatalog


class CatalogQueryFactory(factory.Factory):
    class Meta:
        model = CatalogQuery

    title = factory.Faker('bs')
    content_filter = "{}"  # Default filter to empty object


class EnterpriseCatalogFactory(factory.Factory):
    class Meta:
        model = EnterpriseCatalog

    uuid = factory.LazyFunction(uuid4)
    enterprise_uuid = factory.LazyFunction(uuid4)
    catalog_query = factory.SubFactory(CatalogQueryFactory)
