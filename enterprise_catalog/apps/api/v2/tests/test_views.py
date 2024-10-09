import copy
import json
import uuid
from collections import OrderedDict
from datetime import datetime
from unittest import mock
from urllib.parse import urljoin

import ddt
import pytz
from django.conf import settings
from django.db import IntegrityError
from django.utils.http import urlencode
from django.utils.text import slugify
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings
from six.moves.urllib.parse import quote_plus

from enterprise_catalog.apps.academy.tests.factories import (
    AcademyFactory,
    TagFactory,
)
from enterprise_catalog.apps.api.v1.serializers import ContentMetadataSerializer
from enterprise_catalog.apps.api.v1.tests.mixins import APITestMixin
from enterprise_catalog.apps.api.v1.utils import is_any_course_run_active
from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    EXEC_ED_2U_COURSE_TYPE,
    EXEC_ED_2U_ENTITLEMENT_MODE,
    LEARNER_PATHWAY,
    PROGRAM,
    SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
)
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    ContentMetadata,
    EnterpriseCatalog,
    RestrictedCourseMetadata
)
from enterprise_catalog.apps.catalog.tests.factories import (
    CatalogQueryFactory,
    ContentMetadataFactory,
    EnterpriseCatalogFactory,
)
from enterprise_catalog.apps.catalog.utils import (
    enterprise_proxy_login_url,
    get_content_filter_hash,
    get_content_key,
    get_parent_content_key,
    localized_utcnow,
)
from enterprise_catalog.apps.video_catalog.tests.factories import (
    VideoFactory,
    VideoSkillFactory,
    VideoTranscriptSummaryFactory,
)


@ddt.ddt
class EnterpriseCatalogGetContentMetadataTests(APITestMixin):
    """
    Tests on the get_content_metadata endpoint
    """

    def setUp(self):
        super().setUp()
        # Set up catalog.has_learner_access permissions
        self.set_up_catalog_learner()
        self.enterprise_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        self.enterprise_catalog.catalog_query.save()

        # Delete any existing ContentMetadata records.
        ContentMetadata.objects.all().delete()

    def _get_content_metadata_url(self, enterprise_catalog):
        """
        Helper to get the get_content_metadata endpoint url for a given catalog
        """
        return reverse('api:v2:get-content-metadata-v2', kwargs={'uuid': enterprise_catalog.uuid})

    def _get_expected_json_metadata(self, content_metadata, is_learner_portal_enabled):  # pylint: disable=too-many-statements
        """
        Helper to get the expected json_metadata from the passed in content_metadata instance
        """
        content_type = content_metadata.content_type
        json_metadata = content_metadata.json_metadata.copy()
        enrollment_url = '{}/enterprise/{}/{}/{}/enroll/?catalog={}&utm_medium=enterprise&utm_source={}'
        json_metadata['parent_content_key'] = content_metadata.parent_content_key

        json_metadata['content_last_modified'] = content_metadata.modified.isoformat()[:-6] + 'Z'
        if content_metadata.is_exec_ed_2u_course and is_learner_portal_enabled:
            enrollment_url = '{}/{}/executive-education-2u/course/{}?{}utm_medium=enterprise&utm_source={}'
        elif content_metadata.is_exec_ed_2u_course:
            if sku := json_metadata.get('entitlements', [{}])[0].get('sku'):
                exec_ed_enrollment_url = (
                    f"{settings.ECOMMERCE_BASE_URL}/executive-education-2u/checkout"
                    f"?sku={sku}"
                    f"&utm_medium=enterprise&utm_source={slugify(self.enterprise_catalog.enterprise_name)}"
                )
                enrollment_url = enterprise_proxy_login_url(self.enterprise_slug, next_url=exec_ed_enrollment_url)
        elif is_learner_portal_enabled and content_type in (COURSE, COURSE_RUN):
            enrollment_url = '{}/{}/course/{}?{}utm_medium=enterprise&utm_source={}'
        marketing_url = '{}?utm_medium=enterprise&utm_source={}'
        xapi_activity_id = '{}/xapi/activities/{}/{}'

        if json_metadata.get('uuid'):
            json_metadata['uuid'] = str(json_metadata.get('uuid'))

        if json_metadata.get('marketing_url'):
            json_metadata['marketing_url'] = marketing_url.format(
                json_metadata['marketing_url'],
                slugify(self.enterprise_catalog.enterprise_name),
            )

        if content_type in (COURSE, COURSE_RUN):
            json_metadata['xapi_activity_id'] = xapi_activity_id.format(
                settings.LMS_BASE_URL,
                content_type,
                json_metadata.get('key'),
            )

        if content_type == COURSE:
            course_key = json_metadata.get('key')
            course_runs = json_metadata.get('course_runs') or []
            if is_learner_portal_enabled:
                course_enrollment_url = enrollment_url.format(
                    settings.ENTERPRISE_LEARNER_PORTAL_BASE_URL,
                    self.enterprise_slug,
                    course_key,
                    '',
                    slugify(self.enterprise_catalog.enterprise_name),
                )
                json_metadata['enrollment_url'] = course_enrollment_url
                if json_metadata.get('course_type') != EXEC_ED_2U_COURSE_TYPE:
                    for course_run in course_runs:
                        course_run_key = quote_plus(course_run.get('key'))
                        course_run_key_param = f'course_run_key={course_run_key}&'
                        course_run_enrollment_url = enrollment_url.format(
                            settings.ENTERPRISE_LEARNER_PORTAL_BASE_URL,
                            self.enterprise_slug,
                            course_key,
                            course_run_key_param,
                            slugify(self.enterprise_catalog.enterprise_name),
                        )
                        course_run.update({'enrollment_url': course_run_enrollment_url})
                        course_run['parent_content_key'] = course_key
            else:
                course_enrollment_url = enrollment_url.format(
                    settings.LMS_BASE_URL,
                    self.enterprise_catalog.enterprise_uuid,
                    COURSE,
                    course_key,
                    self.enterprise_catalog.uuid,
                    slugify(self.enterprise_catalog.enterprise_name),
                )
                json_metadata['enrollment_url'] = course_enrollment_url
                if json_metadata.get('course_type') != EXEC_ED_2U_COURSE_TYPE:
                    for course_run in course_runs:
                        course_run_enrollment_url = enrollment_url.format(
                            settings.LMS_BASE_URL,
                            self.enterprise_catalog.enterprise_uuid,
                            COURSE,
                            course_run.get('key'),
                            self.enterprise_catalog.uuid,
                            slugify(self.enterprise_catalog.enterprise_name),
                        )
                        course_run.update({'enrollment_url': course_run_enrollment_url})
                        course_run['parent_content_key'] = course_key

            json_metadata['course_runs'] = course_runs
            json_metadata['active'] = is_any_course_run_active(course_runs)

        if content_type == COURSE_RUN:
            course_key = content_metadata.parent_content_key or get_parent_content_key(json_metadata)
            if is_learner_portal_enabled:
                course_run_key = quote_plus(json_metadata.get('key'))
                course_run_key_param = f'course_run_key={course_run_key}&'
                course_run_enrollment_url = enrollment_url.format(
                    settings.ENTERPRISE_LEARNER_PORTAL_BASE_URL,
                    self.enterprise_slug,
                    course_key,
                    course_run_key_param,
                    slugify(self.enterprise_catalog.enterprise_name),
                )
                json_metadata['enrollment_url'] = course_run_enrollment_url
            else:
                course_run_enrollment_url = enrollment_url.format(
                    settings.LMS_BASE_URL,
                    self.enterprise_catalog.enterprise_uuid,
                    COURSE,
                    json_metadata.get('key'),
                    self.enterprise_catalog.uuid,
                    slugify(self.enterprise_catalog.enterprise_name),
                )
                json_metadata['enrollment_url'] = course_run_enrollment_url

        if content_type == PROGRAM:
            json_metadata['enrollment_url'] = None

        return json_metadata


    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    @ddt.data(
        False,
        True
    )
    def test_get_content_metadata_restricted(self, learner_portal_enabled, mock_api_client):
        """
        Verify the get_content_metadata endpoint returns all the metadata associated with a particular catalog
        """
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': learner_portal_enabled,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }

        catalog = EnterpriseCatalogFactory()
        catalog_query = catalog.catalog_query
        course_mixed = ContentMetadataFactory(content_key='mixed_course', content_type='course')
        course_mixed.catalog_queries.set(CatalogQuery.objects.all())
        course_mixed_run1 = ContentMetadataFactory(content_key='course_mixed_run1', content_type='courserun')
        course_mixed_run2 = ContentMetadataFactory(content_key='course_mixed_run2', content_type='courserun',
                                                   is_restricted_run=True)
        course_mixed_run2.catalog_queries.set(CatalogQuery.objects.all())
        # TODO: create restricted course for mixed course
        course_unicorn = ContentMetadataFactory(content_key='unicorn_course', content_type='course')
        course_unicorn.catalog_queries.set(CatalogQuery.objects.all())
        course_unicorn_run1 = ContentMetadataFactory(content_key='course_unicorn_run1', content_type='courserun',
                                                     is_restricted_run=True)
        course_unicorn_run1.catalog_queries.set(CatalogQuery.objects.all())
        restricted_course_unicorn, _ = RestrictedCourseMetadata.objects.get_or_create(
            content_key=course_unicorn.content_key,
            content_type=course_unicorn.content_type,
        )
        restricted_course_unicorn.catalog_query = CatalogQuery.objects.first()
        restricted_course_unicorn.unrestricted_parent = course_unicorn
        restricted_course_unicorn.save()
        assert catalog.content_metadata[1].json_metadata
        assert not catalog.content_metadata_with_restricted[2].json_metadata
        assert catalog.get_matching_content(['mixed_course'], include_restricted=False)[0].json_metadata
        assert catalog.get_matching_content(['mixed_course'], include_restricted=True)[0].json_metadata
        assert catalog.get_matching_content(['unicorn_course'], include_restricted=False)[0].json_metadata
        assert not catalog.get_matching_content(['unicorn_course'], include_restricted=True)[0].json_metadata
        assert len(catalog.get_matching_content(['course_unicorn_run1'], include_restricted=False)) == 0
        assert len(catalog.get_matching_content(['course_unicorn_run1'], include_restricted=True)) == 1

