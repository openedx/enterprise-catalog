from uuid import uuid4

import factory

from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    PROGRAM,
    json_serialized_course_modes,
)
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    ContentMetadata,
    EnterpriseCatalog,
    EnterpriseCatalogFeatureRole,
    EnterpriseCatalogRoleAssignment,
)
from enterprise_catalog.apps.core.models import User


USER_PASSWORD = 'password'


class CatalogQueryFactory(factory.DjangoModelFactory):
    """
    Test factory for the `CatalogQuery` model
    """
    class Meta:
        model = CatalogQuery

    content_filter = factory.Dict({'content_type': factory.Faker('word')})


class EnterpriseCatalogFactory(factory.DjangoModelFactory):
    """
    Test factory for the `EnterpriseCatalog` model
    """
    class Meta:
        model = EnterpriseCatalog

    uuid = factory.LazyFunction(uuid4)
    title = factory.Faker('word')
    enterprise_uuid = factory.LazyFunction(uuid4)
    enterprise_name = factory.Faker('word')
    catalog_query = factory.SubFactory(CatalogQueryFactory)
    enabled_course_modes = json_serialized_course_modes()
    publish_audit_enrollment_urls = False   # Default to False


class ContentMetadataFactory(factory.DjangoModelFactory):
    """
    Test factory for the `ContentMetadata` model
    """
    class Meta:
        model = ContentMetadata

    content_key = factory.Sequence(lambda n: 'metadata_item_{}'.format(n))  # pylint: disable=unnecessary-lambda
    content_type = factory.Iterator([COURSE_RUN, COURSE, PROGRAM])
    parent_content_key = None   # Default to None

    @factory.lazy_attribute
    def json_metadata(self):
        return {
            'key': self.content_key,
            'marketing_url': 'http://marketing.yay/{}'.format(self.content_key),
        }


class UserFactory(factory.DjangoModelFactory):
    username = factory.Faker('user_name')
    password = factory.PostGenerationMethodCall('set_password', USER_PASSWORD)
    email = factory.Faker('email')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    is_active = True
    is_staff = False
    is_superuser = False

    class Meta:
        model = User


class EnterpriseCatalogFeatureRoleFactory(factory.DjangoModelFactory):
    """
    Test factory for the `EnterpriseCatalogFeatureRole` model.
    """
    name = factory.Faker('word')

    class Meta:
        model = EnterpriseCatalogFeatureRole


class EnterpriseCatalogRoleAssignmentFactory(factory.DjangoModelFactory):
    """
    Test factory for the `EnterpriseCatalogRoleAssignment` model.
    """
    role = factory.SubFactory(EnterpriseCatalogFeatureRoleFactory)
    enterprise_id = factory.LazyFunction(uuid4)

    class Meta:
        model = EnterpriseCatalogRoleAssignment
