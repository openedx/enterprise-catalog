from uuid import uuid4

import factory

from enterprise_catalog.apps.catalog.models import (
    CatalogContentKey,
    CatalogQuery,
    ContentMetadata,
    EnterpriseCatalog,
)


class CatalogQueryFactory(factory.Factory):
    """
    Test factory for the `CatalogQuery` model
    """
    class Meta:
        model = CatalogQuery

    title = factory.Faker('bs')
    content_filter = "{}"  # Default filter to empty object


class EnterpriseCatalogFactory(factory.Factory):
    """
    Test factory for the `EnterpriseCatalog` model
    """
    class Meta:
        model = EnterpriseCatalog

    uuid = factory.LazyFunction(uuid4)
    enterprise_uuid = factory.LazyFunction(uuid4)
    catalog_query = factory.SubFactory(CatalogQueryFactory)


class ContentMetadataFactory(factory.Factory):
    """
    Test factory for the `ContentMetadata` model
    """
    class Meta:
        model = ContentMetadata

    content_key = factory.Faker('word')
    content_type = factory.Iterator(['course_run', 'course', 'program'])
    parent_content_key = factory.Faker('word')
    json_metadata = "{}"  # Default metadata to empty object


class CatalogContentKeyFactory(factory.Factory):
    """
    Test factory for the `CatalogContentKey` model
    """
    class Meta:
        model = CatalogContentKey

    catalog_query = factory.SubFactory(CatalogQueryFactory)
    content_key = factory.SubFactory(ContentMetadataFactory)
