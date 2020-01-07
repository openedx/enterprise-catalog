from uuid import uuid4

import factory

from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    PROGRAM,
    json_serialized_course_modes,
)
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

    content_filter = "{}"  # Default filter to empty object


class EnterpriseCatalogFactory(factory.Factory):
    """
    Test factory for the `EnterpriseCatalog` model
    """
    class Meta:
        model = EnterpriseCatalog

    uuid = factory.LazyFunction(uuid4)
    title = factory.Faker('fake-title')
    enterprise_uuid = factory.LazyFunction(uuid4)
    catalog_query = factory.SubFactory(CatalogQueryFactory)
    enabled_course_modes = json_serialized_course_modes
    publish_audit_enrollment_urls = False   # Default to False


class ContentMetadataFactory(factory.Factory):
    """
    Test factory for the `ContentMetadata` model
    """
    class Meta:
        model = ContentMetadata

    content_key = factory.Faker('course-v1:fake+content+key')
    content_type = factory.Iterator([COURSE_RUN, COURSE, PROGRAM])
    parent_content_key = None   # Default to None
    json_metadata = "{}"  # Default metadata to empty object


class CatalogContentKeyFactory(factory.Factory):
    """
    Test factory for the `CatalogContentKey` model
    """
    class Meta:
        model = CatalogContentKey

    catalog_query = factory.SubFactory(CatalogQueryFactory)
    content_key = factory.SubFactory(ContentMetadataFactory)
