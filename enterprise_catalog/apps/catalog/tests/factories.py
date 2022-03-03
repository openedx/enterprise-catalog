from uuid import uuid4

import factory

from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    LEARNER_PATHWAY,
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
FAKE_IMAGE_URL = 'https://fake.url/image.jpg'
FAKE_ADVERTISED_COURSE_RUN_UUID = uuid4()


class CatalogQueryFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `CatalogQuery` model
    """
    class Meta:
        model = CatalogQuery

    content_filter = factory.Dict({'content_type': factory.Faker('words', nb=3)})
    title = factory.Faker('word')


class EnterpriseCatalogFactory(factory.django.DjangoModelFactory):
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


class ContentMetadataFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `ContentMetadata` model
    """
    class Meta:
        model = ContentMetadata

    content_key = factory.Sequence(lambda n: f'metadata_item_{n}')
    content_type = factory.Iterator([COURSE_RUN, COURSE, PROGRAM, LEARNER_PATHWAY])
    parent_content_key = None   # Default to None

    @factory.lazy_attribute
    def json_metadata(self):
        json_metadata = {
            'key': self.content_key,
            'aggregation_key': f'{self.content_type}:{self.content_key}',
            'uuid': str(uuid4()),
        }
        if self.content_type == COURSE:
            owners = [{
                'name': 'Partner Name',
                'logo_image_url': FAKE_IMAGE_URL,
            }]
            course_runs = [{
                'key': 'course-v1:edX+DemoX',
                'uuid': str(FAKE_ADVERTISED_COURSE_RUN_UUID),
                'content_language': 'en-us',
                'status': 'published',
                'is_enrollable': True,
                'is_marketable': True,
                'availability': 'current',
            }]
            json_metadata.update({
                'content_type': COURSE,
                'marketing_url': f'https://marketing.url/{self.content_key}',
                'image_url': FAKE_IMAGE_URL,
                'owners': owners,
                'advertised_course_run_uuid': str(FAKE_ADVERTISED_COURSE_RUN_UUID),
                'course_runs': course_runs,
            })
        elif self.content_type == COURSE_RUN:
            json_metadata.update({
                'content_type': COURSE_RUN,
                'status': 'published',
                'is_enrollable': True,
                'is_marketable': True,
            })
        elif self.content_type == PROGRAM:
            json_metadata.update({
                'uuid': self.content_key,
                'content_type': PROGRAM,
                'type': 'MicroMasters',
                'hidden': True,
                'marketing_url': f'https://marketing.url/{self.content_key}',
            })
        elif self.content_type == LEARNER_PATHWAY:
            json_metadata.update({
                'content_type': LEARNER_PATHWAY,
                'name': 'Data Engineer',
                'status': 'active',
                'overview': 'Pathway for a data engineer.',
                'published': True,
                'visible_via_association': True,
            })
        return json_metadata


class UserFactory(factory.django.DjangoModelFactory):
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


class EnterpriseCatalogFeatureRoleFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `EnterpriseCatalogFeatureRole` model.
    """
    name = factory.Faker('word')

    class Meta:
        model = EnterpriseCatalogFeatureRole


class EnterpriseCatalogRoleAssignmentFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `EnterpriseCatalogRoleAssignment` model.
    """
    role = factory.SubFactory(EnterpriseCatalogFeatureRoleFactory)
    enterprise_id = factory.LazyFunction(uuid4)

    class Meta:
        model = EnterpriseCatalogRoleAssignment
