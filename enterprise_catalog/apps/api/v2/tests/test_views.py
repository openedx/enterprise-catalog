from datetime import datetime
from unittest import mock

import ddt
import pytz
from rest_framework import status
from rest_framework.reverse import reverse

from enterprise_catalog.apps.api.v1.tests.mixins import APITestMixin
from enterprise_catalog.apps.catalog.constants import (
    COURSE_RUN_RESTRICTION_TYPE_KEY,
    RESTRICTION_FOR_B2B,
)
from enterprise_catalog.apps.catalog.models import ContentMetadata
from enterprise_catalog.apps.catalog.tests import test_utils
from enterprise_catalog.apps.catalog.tests.factories import (
    EnterpriseCatalogFactory,
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
    @ddt.data(
        # Create a course with both an unrestricted (run1) and restricted run (run2), and the restricted run is allowed
        # by the CatalogQuery.
        {
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
                    'json_metadata': {
                        'key': 'edX+course',
                        'course_runs': [
                            {
                                'key': 'course-v1:edX+course+run1',
                                'status': 'published',
                                'is_enrollable': True,
                                'is_marketable': True,
                            },
                        ],
                    },
                    'associate_with_catalog_query': '11111111-1111-1111-1111-111111111111',
                },
            },
            'create_restricted_courses': {
                1: {
                    'content_key': 'edX+course',
                    'catalog_query': '11111111-1111-1111-1111-111111111111',
                    'json_metadata': {
                        'key': 'edX+course',
                        'course_runs': [
                            {
                                'key': 'course-v1:edX+course+run1',
                                'status': 'published',
                                'is_enrollable': True,
                                'is_marketable': True,
                            },
                            {
                                'key': 'course-v1:edX+course+run2',
                                'status': 'published',
                                'is_enrollable': True,
                                'is_marketable': True,
                            },
                        ],
                    },
                },
            },
            'create_restricted_run_allowed_for_restricted_course': [
                {'course': 1, 'run': 'course-v1:edX+course+run2'},
            ],
        },
    )
    @ddt.unpack
    def test_get_content_metadata_content_filters(

        self,
        mock_api_client,
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
            'enable_learner_portal': True,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }

        main_catalog, catalog_queries, content_metadata, restricted_courses = test_utils.setup_scaffolding(
            create_catalog_query,
            create_content_metadata,
            create_restricted_courses,
            create_restricted_run_allowed_for_restricted_course,
        )
        main_catalog.enterprise_uuid = self.enterprise_uuid
        main_catalog.save()

        filtered_content_keys = ['course-v1:edX+course+run1', 'course-v1:edX+course+run2', ]
        url = self._get_content_metadata_url(main_catalog)
        for filter_content_key in filtered_content_keys:
            url += f"&content_keys={filter_content_key}"

        response = self.client.get(
            url,
            {'content_keys': filtered_content_keys}
        )

        self.assertEqual(response.data.get('count'), 1)
        results = response.data.get('results')[0]
        self.assertEqual(results.get('key'), 'edX+course')
        course_runs = results.get('course_runs')

        for course_run in course_runs:
            self.assertIn(course_run.get('key'), filtered_content_keys)

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    @ddt.data(
        # Create a course with both an unrestricted (run1) and restricted run (run2), and the restricted run is NOT
        # allowed by the CatalogQuery.
        {
            'create_catalog_query': {
                '11111111-1111-1111-1111-111111111111': {
                    'content_filter': {
                        'restricted_runs_allowed': {},
                    },
                },
            },
            'create_content_metadata': {
                'edX+course': {
                    'create_runs': {
                        'course-v1:edX+course+run1': {'is_restricted': False},
                        'course-v1:edX+course+run2': {'is_restricted': True},
                    },
                    'json_metadata': {
                        'key': 'edX+course',
                        'course_runs': [
                            {
                                'key': 'course-v1:edX+course+run1',
                                'status': 'published',
                                'is_enrollable': True,
                                'is_marketable': True,
                                COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                            },
                        ],
                    },
                    'associate_with_catalog_query': '11111111-1111-1111-1111-111111111111',
                },
            },
            'create_restricted_courses': {
                1: {
                    'content_key': 'edX+course',
                    'catalog_query': '11111111-1111-1111-1111-111111111111',
                    'json_metadata': {
                        'key': 'edX+course',
                        'course_runs': [
                            {
                                'key': 'course-v1:edX+course+run1',
                                'status': 'published',
                                'is_enrollable': True,
                                'is_marketable': True,
                                COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                            },
                            {
                                'key': 'course-v1:edX+course+run2',
                                'status': 'published',
                                'is_enrollable': True,
                                'is_marketable': True,
                                COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                            },
                        ],
                    },
                },
            },
            'create_restricted_run_allowed_for_restricted_course': [
                {'course': 1, 'run': 'course-v1:edX+course+run2'},
            ],
        },
    )
    @ddt.unpack
    def test_get_content_metadata(
        self,
        mock_api_client,
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
            'enable_learner_portal': True,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }

        main_catalog, catalog_queries, content_metadata, restricted_courses = test_utils.setup_scaffolding(
            create_catalog_query,
            create_content_metadata,
            create_restricted_courses,
            create_restricted_run_allowed_for_restricted_course,
        )
        main_catalog.enterprise_uuid = self.enterprise_uuid
        main_catalog.save()

        filtered_content_keys = ['course-v1:edX+course+run1', 'course-v1:edX+course+run2', ]
        url = self._get_content_metadata_url(main_catalog)
        for filter_content_key in filtered_content_keys:
            url += f"&content_keys={filter_content_key}"

        response = self.client.get(
            url,
            {'content_keys': filtered_content_keys}
        )

        self.assertEqual(response.data.get('count'), 1)
        results = response.data.get('results')[0]
        self.assertEqual(results.get('key'), 'edX+course')
        course_runs = results.get('course_runs')
        # only one (unrestricted) run is returned
        self.assertEqual(len(course_runs), 1)
        # contains only the unrestricted run
        self.assertEqual(course_runs[0].get('key'), 'course-v1:edX+course+run1')

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    @ddt.data(
        # Create a course with both an unrestricted (run1) and restricted run (run2), and the
        # restricted run is allowed by the CatalogQuery. But the course runs do not have
        # the RESTRICTION_FOR_B2B restriction type set
        {
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
                    'json_metadata': {
                        'key': 'edX+course',
                        'course_runs': [
                            {
                                'key': 'course-v1:edX+course+run1',
                                'status': 'published',
                                'is_enrollable': True,
                                'is_marketable': False,
                            },
                        ],
                    },
                    'associate_with_catalog_query': '11111111-1111-1111-1111-111111111111',
                },
            },
            'create_restricted_courses': {
                1: {
                    'content_key': 'edX+course',
                    'catalog_query': '11111111-1111-1111-1111-111111111111',
                    'json_metadata': {
                        'key': 'edX+course',
                        'course_runs': [
                            {
                                'key': 'course-v1:edX+course+run1',
                                'status': 'published',
                                'is_enrollable': True,
                                'is_marketable': False,
                            },
                            {
                                'key': 'course-v1:edX+course+run2',
                                'status': 'published',
                                'is_enrollable': True,
                                'is_marketable': False,
                            },
                        ],
                    },
                },
            },
            'create_restricted_run_allowed_for_restricted_course': [
                {'course': 1, 'run': 'course-v1:edX+course+run2'},
            ],
        },
    )
    @ddt.unpack
    def test_get_content_metadata_with_no_restriction_type(
        self,
        mock_api_client,
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
            'enable_learner_portal': True,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }

        main_catalog, catalog_queries, content_metadata, restricted_courses = test_utils.setup_scaffolding(
            create_catalog_query,
            create_content_metadata,
            create_restricted_courses,
            create_restricted_run_allowed_for_restricted_course,
        )
        main_catalog.enterprise_uuid = self.enterprise_uuid
        main_catalog.save()

        filtered_content_keys = ['course-v1:edX+course+run1', 'course-v1:edX+course+run2', ]
        url = self._get_content_metadata_url(main_catalog)
        for filter_content_key in filtered_content_keys:
            url += f"&content_keys={filter_content_key}"

        response = self.client.get(
            url,
            {'content_keys': filtered_content_keys}
        )

        self.assertEqual(response.data.get('count'), 1)

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    @ddt.data(
        # Create a course with both an unrestricted (run1) and restricted run (run2), and the restricted run is allowed
        # by the CatalogQuery.
        {
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
                    'json_metadata': {
                        'key': 'edX+course',
                        'course_runs': [
                            {
                                'key': 'course-v1:edX+course+run1',
                                'status': 'published',
                                'is_enrollable': True,
                                'is_marketable': True,
                                COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                            },
                        ],
                    },
                    'associate_with_catalog_query': '11111111-1111-1111-1111-111111111111',
                },
            },
            'create_restricted_courses': {
                1: {
                    'content_key': 'edX+course',
                    'catalog_query': '11111111-1111-1111-1111-111111111111',
                    'json_metadata': {
                        'key': 'edX+course',
                        'course_runs': [
                            {
                                'key': 'course-v1:edX+course+run1',
                                'status': 'published',
                                'is_enrollable': True,
                                'is_marketable': True,
                                COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                            },
                            {
                                'key': 'course-v1:edX+course+run2',
                                'status': 'published',
                                'is_enrollable': True,
                                'is_marketable': True,
                                COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                            },
                        ],
                    },
                },
            },
            'create_restricted_run_allowed_for_restricted_course': [
                {'course': 1, 'run': 'course-v1:edX+course+run2'},
            ],
        },
    )
    @ddt.unpack
    def test_get_content_metadata_no_content_filters(

            self,
            mock_api_client,
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
            'enable_learner_portal': True,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }

        main_catalog, catalog_queries, content_metadata, restricted_courses = test_utils.setup_scaffolding(
            create_catalog_query,
            create_content_metadata,
            create_restricted_courses,
            create_restricted_run_allowed_for_restricted_course,
        )
        main_catalog.enterprise_uuid = self.enterprise_uuid
        main_catalog.save()

        filtered_content_keys = ['course-v1:edX+course+run1', 'course-v1:edX+course+run2', ]
        url = self._get_content_metadata_url(main_catalog)

        response = self.client.get(url)

        self.assertEqual(response.data.get('count'), 1)
        results = response.data.get('results')[0]
        self.assertEqual(results.get('key'), 'edX+course')
        course_runs = results.get('course_runs')

        for course_run in course_runs:
            self.assertIn(course_run.get('key'), filtered_content_keys)
