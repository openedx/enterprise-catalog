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
    ContentMetadata,
    EnterpriseCatalog,
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

    def test_get_content_metadata_unauthorized_invalid_permissions(self):
        """
        Verify the get_content_metadata endpoint rejects users with invalid permissions
        """
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        url = self._get_content_metadata_url(self.enterprise_catalog)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_content_metadata_unauthorized_incorrect_jwt_context(self):
        """
        Verify the get_content_metadata endpoint rejects catalog learners
        with an incorrect JWT context (i.e., enterprise uuid)
        """
        enterprise_catalog = EnterpriseCatalogFactory()
        self.remove_role_assignments()
        url = self._get_content_metadata_url(enterprise_catalog)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_content_metadata_implicit_access(self):
        """
        Verify the get_content_metadata endpoint responds with 200 OK for
        user with implicit JWT access
        """
        self.remove_role_assignments()
        url = self._get_content_metadata_url(self.enterprise_catalog)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_content_metadata_no_catalog_query(self):
        """
        Verify the get_content_metadata endpoint returns no results if the catalog has no catalog query
        """
        no_catalog_query_catalog = EnterpriseCatalogFactory(
            catalog_query=None,
            enterprise_uuid=self.enterprise_uuid,
        )
        url = self._get_content_metadata_url(no_catalog_query_catalog)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['results'], [])

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    def test_get_content_metadata_content_filters_course_run_key(self, mock_api_client):
        """
        Test that the get_content_metadata view GET view will support a filter including
        course run key(s), even when the catalog itself doesn't explictly contain course runs.
        """
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': True,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }
        course_metadata = ContentMetadataFactory(content_type=COURSE)
        course_key = course_metadata.content_key
        course_run_key = course_metadata.json_metadata['course_runs'][0]['key']
        ContentMetadataFactory(
            content_type=COURSE_RUN,
            content_key=course_run_key,
            parent_content_key=course_key
        )
        self.add_metadata_to_catalog(self.enterprise_catalog, [course_metadata])

        url = f'{self._get_content_metadata_url(self.enterprise_catalog)}?content_keys={quote_plus(course_run_key)}'
        response = self.client.get(url)
        assert response.data.get('count') == 1
        result = response.data.get('results')[0]
        assert get_content_key(result) == course_metadata.content_key

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    @ddt.data(
        False,
        True
    )
    def test_get_content_metadata_content_filters(self, learner_portal_enabled, mock_api_client):
        """
        Test that the get_content_metadata view GET view will filter provided content_keys (up to a limit)
        """
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': learner_portal_enabled,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }
        ContentMetadataFactory.reset_sequence(10)
        metadata = ContentMetadataFactory.create_batch(api_settings.PAGE_SIZE)
        filtered_content_keys = []
        url = self._get_content_metadata_url(self.enterprise_catalog)
        for filter_content_key_index in range(int(api_settings.PAGE_SIZE / 2)):
            filtered_content_keys.append(metadata[filter_content_key_index].content_key)
            url += f"&content_keys={metadata[filter_content_key_index].content_key}"

        self.add_metadata_to_catalog(self.enterprise_catalog, metadata)
        response = self.client.get(
            url,
            {'content_keys': filtered_content_keys}
        )
        assert response.data.get('count') == int(api_settings.PAGE_SIZE / 2)
        for result in response.data.get('results'):
            assert get_content_key(result) in filtered_content_keys

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    @ddt.data(
        False,
        True
    )
    def test_get_content_metadata(self, learner_portal_enabled, mock_api_client):
        """
        Verify the get_content_metadata endpoint returns all the metadata associated with a particular catalog
        """
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': learner_portal_enabled,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }
        # Create enough metadata to force pagination
        course = ContentMetadataFactory.create(content_type=COURSE)
        program = ContentMetadataFactory.create(content_type=PROGRAM)
        pathway = ContentMetadataFactory.create(content_type=LEARNER_PATHWAY)
        # important to actually link the course runs to the parent course
        course_runs = ContentMetadataFactory.create_batch(
            api_settings.PAGE_SIZE,
            content_type=COURSE_RUN,
            parent_content_key=course.content_key,
        )
        course.json_metadata['course_runs'] = [run.json_metadata for run in course_runs]
        course.save()

        metadata = course_runs + [course, program, pathway]
        self.add_metadata_to_catalog(self.enterprise_catalog, metadata)
        url = self._get_content_metadata_url(self.enterprise_catalog)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual((response_data['count']), len(metadata))
        self.assertEqual(uuid.UUID(response_data['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(response_data['title'], self.enterprise_catalog.title)
        self.assertEqual(uuid.UUID(response_data['enterprise_customer']), self.enterprise_catalog.enterprise_uuid)

        second_page_response = self.client.get(response_data['next'])
        self.assertEqual(second_page_response.status_code, status.HTTP_200_OK)
        second_response_data = second_page_response.json()
        self.assertIsNone(second_response_data['next'])

        # Check that the union of both pages' data is equal to the whole set of metadata
        expected_metadata = sorted(
            [
                self._get_expected_json_metadata(item, learner_portal_enabled)
                for item in metadata
            ],
            key=get_content_key,
        )
        actual_metadata = sorted(
            response_data['results'] + second_response_data['results'],
            key=get_content_key,
        )
        self.assertEqual(
            json.dumps(actual_metadata, sort_keys=True),
            json.dumps(expected_metadata, sort_keys=True),
        )

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
        


    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    @ddt.data(
        False,
        True
    )
    def test_get_content_metadata_traverse_pagination(self, learner_portal_enabled, mock_api_client):
        """
        Verify the get_content_metadata endpoint returns all metadata on one page if the traverse pagination query
        parameter is added.
        """
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': learner_portal_enabled,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }
        # Create enough metadata to force pagination
        course = ContentMetadataFactory.create(content_type=COURSE)
        # important to actually link the course runs to the parent course
        course_runs = ContentMetadataFactory.create_batch(
            api_settings.PAGE_SIZE,
            content_type=COURSE_RUN,
            parent_content_key=course.content_key,
        )
        course.json_metadata['course_runs'] = [run.json_metadata for run in course_runs]
        course.save()

        metadata = course_runs + [course]
        self.add_metadata_to_catalog(self.enterprise_catalog, metadata)
        url = self._get_content_metadata_url(self.enterprise_catalog) + '?traverse_pagination=1'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual((response_data['count']), api_settings.PAGE_SIZE + 1)
        self.assertEqual(uuid.UUID(response_data['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(response_data['title'], self.enterprise_catalog.title)
        self.assertEqual(uuid.UUID(response_data['enterprise_customer']), self.enterprise_catalog.enterprise_uuid)

        # Check that the page contains all the metadata
        expected_metadata = sorted(
            [
                self._get_expected_json_metadata(item, learner_portal_enabled)
                for item in metadata
            ],
            key=get_content_key,
        )
        actual_metadata = sorted(
            response_data['results'],
            key=get_content_key,
        )
        self.assertEqual(
            json.dumps(actual_metadata, sort_keys=True),
            json.dumps(expected_metadata, sort_keys=True),
        )

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    @ddt.data(
        False,
        True
    )
    def test_get_content_metadata_no_nested_enrollment_urls_exec_ed_2u(
        self,
        is_learner_portal_enabled,
        mock_api_client
    ):
        """
        Verify the get_content_metadata endpoint returns
        all the metadata associated with a particular catalog, and that
        no course run enrollment_urls are included for exec-ed-2u course types.
        """
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': is_learner_portal_enabled,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }
        # Create enough metadata to force pagination
        course = ContentMetadataFactory.create(content_type=COURSE)
        # important to actually link the course runs to the parent course
        course_runs = ContentMetadataFactory.create_batch(
            2,
            content_type=COURSE_RUN,
            parent_content_key=course.content_key,
        )
        course.json_metadata['course_runs'] = [run.json_metadata for run in course_runs]
        course.json_metadata['course_type'] = EXEC_ED_2U_COURSE_TYPE
        course.json_metadata['entitlements'] = [
            {
                'mode': EXEC_ED_2U_ENTITLEMENT_MODE,
                'sku': '123456FW',
            },
        ]
        course.save()

        metadata = course_runs + [course]
        self.add_metadata_to_catalog(self.enterprise_catalog, metadata)

        response = self.client.get(self._get_content_metadata_url(self.enterprise_catalog))

        self.maxDiff = None
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check that the union of both pages' data is equal to the whole set of metadata
        response_data = response.json()
        expected_metadata = sorted(
            [
                self._get_expected_json_metadata(item, is_learner_portal_enabled)
                for item in metadata
            ],
            key=get_content_key,
        )
        actual_metadata = sorted(response_data['results'], key=get_content_key)

        self.assertEqual(
            json.dumps(actual_metadata, sort_keys=True),
            json.dumps(expected_metadata, sort_keys=True),
        )


@ddt.ddt
class EnterpriseCustomerContentMetadataViewSetTests(APITestMixin):
    """
    Tests for the Enterprise Customer Content Metadata related endpoints.
    """

    def setUp(self):
        super().setUp()
        self.customer_details_patcher = mock.patch(
            'enterprise_catalog.apps.catalog.models.EnterpriseCustomerDetails'
        )
        self.mock_customer_details = self.customer_details_patcher.start()
        self.NOW = localized_utcnow()
        self.mock_customer_details.return_value.last_modified_date = self.NOW

        self.set_up_catalog_learner()

        self.catalog_query = CatalogQueryFactory()
        self.enterprise_catalog = EnterpriseCatalogFactory(
            enterprise_uuid=self.enterprise_uuid,
            catalog_query=self.catalog_query,
        )

        self.content_key_1 = 'test-key'
        self.content_key_2 = 'test-key-2'
        self.uuid = uuid.uuid4()
        self.uuid_2 = uuid.uuid4()
        self.first_content_metadata = ContentMetadataFactory(
            content_key=self.content_key_1,
            content_uuid=self.uuid,
            content_type=COURSE_RUN,
        )
        self.add_metadata_to_catalog(self.enterprise_catalog, [self.first_content_metadata])
        self.second_content_metadata = ContentMetadataFactory(
            content_key=self.content_key_2,
            content_uuid=self.uuid_2,
            content_type=COURSE,
        )
        self.add_metadata_to_catalog(self.enterprise_catalog, [self.second_content_metadata])

        self.url = reverse(
            'api:v1:enterprise-customer-content-metadata',
            kwargs={'enterprise_uuid': self.enterprise_uuid}
        ).replace('_', '-')

        self.addCleanup(self.customer_details_patcher.stop)

    @ddt.data(True, False)
    def test_content_metadata_get_item_with_content_key(self, skip_customer_fetch):
        """
        Test the base success case for the `content-metadata` view using a content key as an identifier
        """
        self.mock_customer_details.reset_mock()
        query_params = ''
        if skip_customer_fetch:
            query_params = '?skip_customer_fetch=1'
        response = self.client.get(urljoin(self.url, f"{self.content_key_1}/") + query_params)
        assert response.status_code == 200
        expected_data = ContentMetadataSerializer(
            self.first_content_metadata,
            context={
                'enterprise_catalog': self.enterprise_catalog,
                'skip_customer_fetch': skip_customer_fetch,
            },
        ).data
        actual_data = response.json()
        for payload_key in ['key', 'uuid']:
            assert actual_data[payload_key] == expected_data[payload_key]

        if skip_customer_fetch:
            self.assertFalse(self.mock_customer_details.called)
        else:
            self.assertTrue(self.mock_customer_details.called)

    def test_content_metadata_get_item_with_content_key_in_multiple_catalogs(self):
        """
        Test the base success case for the `content-metadata` view using a content key as an identifier
        when the customer has multiple catalogs in which to search for matching content.
        """
        other_catalog = EnterpriseCatalogFactory(
            enterprise_uuid=self.enterprise_uuid,
            catalog_query=self.catalog_query,
        )
        other_metadata = ContentMetadataFactory(
            content_type=COURSE,
        )
        self.add_metadata_to_catalog(other_catalog, [other_metadata])

        response = self.client.get(urljoin(self.url, f"{self.content_key_1}/"))

        assert response.status_code == 200
        expected_data = ContentMetadataSerializer(
            self.first_content_metadata,
            context={'enterprise_catalog': self.enterprise_catalog},
        ).data
        actual_data = response.json()
        for payload_key in ['key', 'uuid']:
            assert actual_data[payload_key] == expected_data[payload_key]

    def test_content_metadata_get_item_with_course_run_key(self):
        """
        Test the success case for the `content-metadata` view using a course run key
        as the content identifier, where the customer's catalog is only
        directly associated with the course record containing that run.
        """
        # First create a metadata record representing the course run,
        # but _don't_ associate it directly with the customer's catalog.
        # The searching/match logic will infer a corresponding course
        # and match on that course, based on the course run record's parent_content_key.
        course_run_content = ContentMetadataFactory(
            content_key='my-awesome-course-run',
            content_type=COURSE_RUN,
            parent_content_key=self.second_content_metadata.content_key,
        )
        other_catalog = EnterpriseCatalogFactory()
        self.add_metadata_to_catalog(other_catalog, [course_run_content])

        response = self.client.get(urljoin(self.url, f"{course_run_content.content_key}/"))

        expected_data = ContentMetadataSerializer(
            self.second_content_metadata,
            context={'enterprise_catalog': self.enterprise_catalog},
        ).data
        assert response.status_code == 200
        actual_data = response.json()
        for payload_key in ['key', 'uuid']:
            assert actual_data[payload_key] == expected_data[payload_key]

    def test_content_metadata_get_item_with_uuid(self):
        """
        Test the base success case for the `content-metadata` view using a UUID as an identifier
        """
        response = self.client.get(urljoin(self.url, f"{str(self.uuid)}/"))

        assert response.status_code == 200
        expected_data = ContentMetadataSerializer(self.first_content_metadata).data
        actual_data = response.json()
        for payload_key in ['key', 'uuid']:
            assert actual_data[payload_key] == expected_data[payload_key]

    def test_content_metadata_exists_outside_of_requested_catalog(self):
        """
        Test that the content metadata list endpoint will only fetch content that exists under a catalog owned by the
        requesting user's Enterprise Customer
        """
        assert len(ContentMetadata.objects.all()) == 2
        other_content_key = "not-in-your-catalog"
        other_content = ContentMetadataFactory(
            content_key=other_content_key,
            content_type=COURSE,
            content_uuid=uuid.uuid4(),
        )
        assert len(ContentMetadata.objects.all()) == 3

        response = self.client.get(urljoin(self.url, f"{str(other_content_key)}/"))

        assert response.status_code == 404
        self.add_metadata_to_catalog(self.enterprise_catalog, [other_content])

        response = self.client.get(urljoin(self.url, f"{str(other_content_key)}/"))

        assert response.json().get('key') == other_content_key
        assert response.status_code == 200

    def test_content_metadata_content_not_found(self):
        """
        Test the 404 NOT FOUND case for the `content-metadata` view.
        """
        response = self.client.get(urljoin(self.url, "somerandomkey/"))
        assert response.status_code == 404

    def test_content_metadata_create_not_implemented(self):
        """
        Test that CREATE requests are not supported by the `content-metadata` view.
        """
        response = self.client.post(urljoin(self.url, f"{self.content_key_1}/"))
        assert response.status_code == 405

    def test_content_metadata_delete_not_implemented(self):
        """
        Test that DELETE requests are not supported by the `content-metadata` view.
        """
        response = self.client.delete(urljoin(self.url, f"{self.content_key_1}/"))
        assert response.status_code == 405
