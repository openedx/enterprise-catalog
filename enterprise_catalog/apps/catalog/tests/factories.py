import datetime
from uuid import uuid4

import factory
from factory.fuzzy import FuzzyText
from faker import Faker

from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    LEARNER_PATHWAY,
    PROGRAM,
    TIMESTAMP_FORMAT,
    json_serialized_course_modes,
)
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    ContentMetadata,
    EnterpriseCatalog,
    EnterpriseCatalogFeatureRole,
    EnterpriseCatalogRoleAssignment,
    RestrictedCourseMetadata,
    RestrictedRunAllowedForRestrictedCourse,
)
from enterprise_catalog.apps.core.models import User


USER_PASSWORD = 'password'
FAKE_ADVERTISED_COURSE_RUN_UUID = uuid4()
FAKE_CONTENT_AUTHOR_NAME = 'Partner Name'
FAKE_CONTENT_AUTHOR_UUID = uuid4()
FAKE_CONTENT_TITLE_PREFIX = 'Fake Content Title'

fake = Faker()


class CatalogQueryFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `CatalogQuery` model
    """
    class Meta:
        model = CatalogQuery

    content_filter = factory.Dict({'content_type': factory.Faker('words', nb=6)})
    title = FuzzyText(length=100)


class EnterpriseCatalogFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `EnterpriseCatalog` model
    """
    class Meta:
        model = EnterpriseCatalog

    uuid = factory.LazyFunction(uuid4)
    title = FuzzyText(length=255)
    enterprise_uuid = factory.LazyFunction(uuid4)
    enterprise_name = factory.Faker('company')
    catalog_query = factory.SubFactory(CatalogQueryFactory)
    enabled_course_modes = json_serialized_course_modes()
    publish_audit_enrollment_urls = False   # Default to False


class ContentMetadataFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `ContentMetadata` model
    """
    class Meta:
        model = ContentMetadata
        # Exclude certain factory fields from being used as model fields during mode.save().  If these were not
        # specified here, the test SQL server would throw an error that the field does not exist on the table.
        exclude = ('card_image_url_prefix', 'card_image_url', 'title')

    # factory fields
    card_image_url_prefix = factory.Faker('image_url')
    card_image_url = factory.LazyAttribute(lambda p: f'{p.card_image_url_prefix}.jpg')
    title = factory.Faker('lexify', text=f'{FAKE_CONTENT_TITLE_PREFIX} ??????????')

    # model fields
    content_key = factory.Faker('bothify', text='??????????+####')
    content_uuid = factory.LazyFunction(uuid4)
    content_type = factory.Iterator([COURSE_RUN, COURSE, PROGRAM, LEARNER_PATHWAY])
    parent_content_key = None

    @factory.lazy_attribute
    def _json_metadata(self):
        json_metadata = {
            'key': self.content_key,
            'aggregation_key': f'{self.content_type}:{self.content_key}',
            'uuid': str(self.content_uuid),
            'title': self.title,
            'normalized_metadata': {
                'enroll_by_date': '2026-01-26T23:59:59Z',
            },
        }
        if self.content_type == COURSE:
            owners = [{
                'uuid': str(FAKE_CONTENT_AUTHOR_UUID),
                'name': FAKE_CONTENT_AUTHOR_NAME,
                'logo_image_url': fake.image_url() + '.jpg',
            }]
            course_runs = [{
                'key': 'course-v1:edX+DemoX',
                'uuid': str(FAKE_ADVERTISED_COURSE_RUN_UUID),
                'content_language': 'en-us',
                'status': 'published',
                'is_enrollable': True,
                'is_marketable': True,
                'availability': 'current',
                'seats': [
                    {
                        'type': 'audit',
                        'price': '0.00',
                        'currency': 'USD',
                        'upgrade_deadline': None,
                        'upgrade_deadline_override': None,
                        'credit_provider': None,
                        'credit_hours': None,
                        'sku': '175338C',
                        'bulk_sku': None
                    },
                    {
                        'type': 'verified',
                        'price': '50.00',
                        'currency': 'USD',
                        'upgrade_deadline': '2026-01-26T23:59:59Z',
                        'upgrade_deadline_override': None,
                        'credit_provider': None,
                        'credit_hours': None,
                        'sku': 'F46BB55',
                        'bulk_sku': 'C72C608'
                    }
                ],
                'start': '2024-02-12T11:00:00Z',
                'end': '2026-02-05T11:00:00Z',
                'fixed_price_price_usd': None,
                'first_enrollable_paid_seat_price': 50,
            }]
            json_metadata.update({
                'content_type': COURSE,
                'marketing_url': f'https://marketing.url/{self.content_key}',
                'image_url': self.card_image_url,
                'owners': owners,
                'advertised_course_run_uuid': str(FAKE_ADVERTISED_COURSE_RUN_UUID),
                'course_runs': course_runs,
                'course': self.content_key,
                'entitlements': [],
            })
        elif self.content_type == COURSE_RUN:
            json_metadata.update({
                'content_type': COURSE_RUN,
                'content_language': 'en-us',
                'status': 'published',
                'is_enrollable': True,
                'is_marketable': True,
                'availability': 'current',
                'image_url': self.card_image_url,
            })
        elif self.content_type == PROGRAM:
            # programs in the wild do not have a key
            json_metadata.pop('key')
            authoring_organizations = [{
                'uuid': str(FAKE_CONTENT_AUTHOR_UUID),
                'name': FAKE_CONTENT_AUTHOR_NAME,
                'logo_image_url': fake.image_url() + '.jpg',
            }]
            json_metadata.update({
                'uuid': self.content_key,
                'content_type': PROGRAM,
                'type': 'MicroMasters',
                'marketing_url': f'https://marketing.url/{self.content_key}',
                'authoring_organizations': authoring_organizations,
                'card_image_url': self.card_image_url,
                'status': 'active',
            })
        elif self.content_type == LEARNER_PATHWAY:
            json_metadata.update({
                'content_type': LEARNER_PATHWAY,
                'name': 'Data Engineer',
                'status': 'active',
                'overview': 'Pathway for a data engineer.',
                'published': True,
                'visible_via_association': True,
                'created': datetime.datetime.utcnow().strftime(TIMESTAMP_FORMAT),
                'card_image': {
                    'card': {
                        'url': self.card_image_url,
                        'width': 378,
                        'height': 225,
                    },
                },
            })
        return json_metadata


class RestrictedCourseMetadataFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `RestrictedCourseMetadata` model.
    """
    class Meta:
        model = RestrictedCourseMetadata

    content_key = factory.Faker('bothify', text='??????????+####')
    content_uuid = factory.LazyFunction(uuid4)
    content_type = COURSE
    parent_content_key = None
    _json_metadata = {}  # Callers are encouraged to set this.


class RestrictedRunAllowedForRestrictedCourseFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `RestrictedRunAllowedForRestrictedCourse` model.
    """
    class Meta:
        model = RestrictedRunAllowedForRestrictedCourse

    course = factory.SubFactory(RestrictedCourseMetadataFactory)
    run = factory.SubFactory(ContentMetadataFactory)


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
    name = FuzzyText(length=32)

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
