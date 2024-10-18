import json
import json
import uuid
from datetime import datetime
from unittest import mock

import ddt
import pytz
from django.conf import settings
from django.utils.text import slugify
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings
from six.moves.urllib.parse import quote_plus

from enterprise_catalog.apps.api.v1.tests.mixins import APITestMixin
from enterprise_catalog.apps.api.v1.utils import is_any_course_run_active
from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    EXEC_ED_2U_COURSE_TYPE,
    LEARNER_PATHWAY,
    PROGRAM,
)
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
)
from enterprise_catalog.apps.catalog.tests import test_utils
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
    EnterpriseCatalogFactory,
)
from enterprise_catalog.apps.catalog.utils import (
    enterprise_proxy_login_url,
    get_content_key,
    get_parent_content_key,
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
        # self.enterprise_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        # self.enterprise_catalog.catalog_query.save()

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
    def test_get_content_metadata_non_active_courses(self, learner_portal_enabled, mock_api_client):
        """
        Verify the get_content_metadata endpoint returns only active courses associated with a particular catalog
        """
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': learner_portal_enabled,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }
        # Create enough metadata to force pagination
        inactive_course = ContentMetadataFactory.create(content_type=COURSE)
        active_course = ContentMetadataFactory.create(content_type=COURSE)
        program = ContentMetadataFactory.create(content_type=PROGRAM)
        pathway = ContentMetadataFactory.create(content_type=LEARNER_PATHWAY)
        # important to actually link the course runs to the parent course
        course_runs = ContentMetadataFactory.create_batch(
            api_settings.PAGE_SIZE,
            content_type=COURSE_RUN,
            parent_content_key=active_course.content_key,
        )
        inactive_course_runs = ContentMetadataFactory.create_batch(
            api_settings.PAGE_SIZE,
            content_type=COURSE_RUN,
            parent_content_key=inactive_course.content_key,
        )
        for run in inactive_course_runs:
            # Setting both 'is_enrollable' or 'is_marketable' to False will mark the course as inactive
            run.json_metadata['is_enrollable'] = False
            run.json_metadata['is_marketable'] = False
            run.save()

        inactive_course.json_metadata['course_runs'] = [
            run.json_metadata for run in inactive_course_runs]
        inactive_course.save()
        active_course.json_metadata['course_runs'] = [
            run.json_metadata for run in course_runs]
        active_course.save()

        metadata = course_runs + [inactive_course,
                                  active_course, program, pathway]
        self.add_metadata_to_catalog(self.enterprise_catalog, metadata)
        url = self._get_content_metadata_url(self.enterprise_catalog)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        # excluded expire course (API won't return it)
        self.assertEqual((response_data['count']), len(metadata) - 1)
        self.assertEqual(
            uuid.UUID(response_data['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(response_data['title'], self.enterprise_catalog.title)
        self.assertEqual(uuid.UUID(
            response_data['enterprise_customer']), self.enterprise_catalog.enterprise_uuid)

        second_page_response = self.client.get(response_data['next'])
        self.assertEqual(second_page_response.status_code, status.HTTP_200_OK)
        second_response_data = second_page_response.json()
        self.assertIsNone(second_response_data['next'])

        # Check that the union of both pages' data is equal to the whole set of metadata
        expected_metadata = sorted(
            [
                self._get_expected_json_metadata(item, learner_portal_enabled)
                # since the course is expired, we won't get it back from get_content_metadata endpoint
                for item in metadata if item != inactive_course
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
        # Iterate through response_data results and verify active status for courses
        for item in response_data['results']:
            if item['content_type'] == 'course':
                self.assertTrue(
                    item['active'], f"Course {item['key']} should be active")

        # Do the same for the second page
        for item in second_response_data['results']:
            if item['content_type'] == 'course':
                self.assertTrue(
                    item['active'], f"Course {item['key']} should be active")

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
        # Create a course with both an unrestricted (run1) and restricted run (run2), and the restricted run is allowed
        # by the CatalogQuery.
        {
            'learner_portal_enabled': False,
            'create_catalog_query': {
                '11111111-1111-1111-1111-111111111111': {
                    'content_filter': {
                        'restricted_runs_allowed': {
                            'course:edX+course': [
                                'course-v1:edX+course+run2',
                            ],
                        },
                    },
                },
            },
            'create_content_metadata': {
                'edX+course': {
                    'create_runs': {
                        'course-v1:edX+course+run1': {'is_restricted': False},
                        'course-v1:edX+course+run2': {'is_restricted': True},
                    },
                    'json_metadata': {'foobar': 'base metadata'},
                    'associate_with_catalog_query': '11111111-1111-1111-1111-111111111111',
                },
            },
            'create_restricted_courses': {
                1: {
                    'content_key': 'edX+course',
                    'catalog_query': '11111111-1111-1111-1111-111111111111',
                    'json_metadata': {'foobar': 'override metadata'},
                },
            },
            'create_restricted_run_allowed_for_restricted_course': [
                {'course': 1, 'run': 'course-v1:edX+course+run2'},
            ],
        },
        {
            'learner_portal_enabled': True,
            'create_catalog_query': {
                '11111111-1111-1111-1111-111111111111': {
                    'content_filter': {
                        'restricted_runs_allowed': {
                            'course:edX+course': [
                                'course-v1:edX+course+run2',
                            ],
                        },
                    },
                },
            },
            'create_content_metadata': {
                'edX+course': {
                    'create_runs': {
                        'course-v1:edX+course+run1': {'is_restricted': False},
                        'course-v1:edX+course+run2': {'is_restricted': True},
                    },
                    'json_metadata': {'foobar': 'base metadata'},
                    'associate_with_catalog_query': '11111111-1111-1111-1111-111111111111',
                },
            },
            'create_restricted_courses': {
                1: {
                    'content_key': 'edX+course',
                    'catalog_query': '11111111-1111-1111-1111-111111111111',
                    'json_metadata': {'foobar': 'override metadata'},
                },
            },
            'create_restricted_run_allowed_for_restricted_course': [
                {'course': 1, 'run': 'course-v1:edX+course+run2'},
            ],
        },
    )
    @ddt.unpack
    def test_my_get_content_metadata_content_filters_round_2(

        self,
        mock_api_client,
        learner_portal_enabled,
        create_catalog_query,
        create_content_metadata=None,
        create_restricted_courses=None,
        create_restricted_run_allowed_for_restricted_course=None,
    ):
        """
        Test that the get_content_metadata view GET view will filter provided content_keys (up to a limit)
        """
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': learner_portal_enabled,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }

        main_catalog, catalog_queries, content_metadata, restricted_courses = test_utils.setup_scaffolding(
            create_catalog_query,
            create_content_metadata,
            create_restricted_courses,
            create_restricted_run_allowed_for_restricted_course,
        )

        # ContentMetadataFactory.reset_sequence(10)
        # metadata = ContentMetadataFactory.create_batch(api_settings.PAGE_SIZE)
        filtered_content_keys = [
            'edX+course',
            'course-v1:edX+course+run1',
            'course-v1:edX+course+run2',
        ]
        url = self._get_content_metadata_url(main_catalog)
        # for filter_content_key in filtered_content_keys:
        #     url += f"&content_keys={filter_content_key}"

        response = self.client.get(
            url,
            {'content_keys': filtered_content_keys}
        )
        print(f'response: {response}')
        assert response.data.get('count') == int(api_settings.PAGE_SIZE / 2)
        for result in response.data.get('results'):
            assert get_content_key(result) in filtered_content_keys
