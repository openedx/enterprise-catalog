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
from enterprise_catalog.apps.core.models import User


USER_PASSWORD = 'password'


class CatalogQueryFactory(factory.DjangoModelFactory):
    """
    Test factory for the `CatalogQuery` model
    """
    class Meta:
        model = CatalogQuery

    content_filter = "{}"  # Default filter to empty object


class EnterpriseCatalogFactory(factory.DjangoModelFactory):
    """
    Test factory for the `EnterpriseCatalog` model
    """
    class Meta:
        model = EnterpriseCatalog

    uuid = factory.LazyFunction(uuid4)
    title = factory.Faker('word')
    enterprise_uuid = factory.LazyFunction(uuid4)
    catalog_query = factory.SubFactory(CatalogQueryFactory)
    enabled_course_modes = json_serialized_course_modes()
    publish_audit_enrollment_urls = False   # Default to False


class ContentMetadataFactory(factory.DjangoModelFactory):
    """
    Test factory for the `ContentMetadata` model
    """
    class Meta:
        model = ContentMetadata

    content_key = factory.Faker('course-v1:fake+content+key')
    content_type = factory.Iterator([COURSE_RUN, COURSE, PROGRAM])
    parent_content_key = None   # Default to None
    json_metadata = "{}"  # Default metadata to empty object


class CatalogContentKeyFactory(factory.DjangoModelFactory):
    """
    Test factory for the `CatalogContentKey` model
    """
    class Meta:
        model = CatalogContentKey

    catalog_query = factory.SubFactory(CatalogQueryFactory)
    content_key = factory.SubFactory(ContentMetadataFactory)


class UserFactory(factory.DjangoModelFactory):
    username = factory.Faker('user_name')
    password = factory.PostGenerationMethodCall('set_password', USER_PASSWORD)
    email = factory.Faker('email')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    is_active = True
    is_staff = False

    class Meta:
        model = User
