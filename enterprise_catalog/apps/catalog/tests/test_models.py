""" Tests for catalog models. """

import json
from collections import OrderedDict
from contextlib import contextmanager
from datetime import timedelta
from unittest import mock
from uuid import uuid4

import ddt
from django.conf import settings
from django.test import TestCase, override_settings

from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    COURSE_RUN_RESTRICTION_TYPE_KEY,
    EXEC_ED_2U_COURSE_TYPE,
    EXEC_ED_2U_ENTITLEMENT_MODE,
    PROGRAM,
    QUERY_FOR_RESTRICTED_RUNS,
    RESTRICTED_RUNS_ALLOWED_KEY,
    RESTRICTION_FOR_B2B,
)
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    RestrictedCourseMetadata,
    _should_allow_metadata,
    synchronize_restricted_content,
    update_contentmetadata_from_discovery,
)
from enterprise_catalog.apps.catalog.tests import factories
from enterprise_catalog.apps.catalog.utils import localized_utcnow


@ddt.ddt
class TestModels(TestCase):
    """ Models tests. """

    @ddt.data(
        {'content_type': COURSE_RUN, 'course_type': EXEC_ED_2U_COURSE_TYPE, 'expected_value': False},
        {'content_type': PROGRAM, 'course_type': EXEC_ED_2U_COURSE_TYPE, 'expected_value': False},
        {'content_type': COURSE, 'course_type': 'SOME-OTHER-TYPE', 'expected_value': False},
        {'content_type': COURSE, 'course_type': EXEC_ED_2U_COURSE_TYPE, 'expected_value': True},
    )
    @ddt.unpack
    def test_is_exec_ed_2u_course(self, content_type, course_type, expected_value):
        content_metadata = factories.ContentMetadataFactory(
            content_key='edX+testX',
            content_type=content_type,
        )
        content_metadata._json_metadata['course_type'] = course_type  # pylint: disable=protected-access
        self.assertEqual(content_metadata.is_exec_ed_2u_course, expected_value)

    @ddt.data(
        {'content_type': COURSE, 'course_type': 'SOME-OTHER-TYPE', 'expected_value': False},
        {'content_type': COURSE, 'course_type': EXEC_ED_2U_COURSE_TYPE, 'expected_value': True},
    )
    @ddt.unpack
    def test__should_allow_metadata(self, content_type, course_type, expected_value):
        """
        Ensure that specific course_type values are allowed/disallowed
        """
        content_metadata = factories.ContentMetadataFactory(
            content_key='edX+testX',
            content_type=content_type,
        )
        content_metadata._json_metadata['course_type'] = course_type  # pylint: disable=protected-access
        self.assertEqual(_should_allow_metadata(content_metadata.json_metadata), expected_value)

    @override_settings(DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT=0)
    @mock.patch('enterprise_catalog.apps.api_client.discovery.DiscoveryApiClient')
    def test_product_source_content_inclusion_logic(self, mock_client):
        """
        Test that we exclude 2u exec ed courses from the create content metadata task unless the query provided allows
        for it
        """
        edx_course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+edxSourceX'),
            ('key', 'edX+edxSourceX'),
            ('title', 'test course'),
            ('product_source', 'edX'),
        ])
        twou_course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+2uSourceX'),
            ('key', 'edX+2uSourceX'),
            ('title', 'test course 2'),
            ('product_source', OrderedDict(
                [('name', '2u'),
                 ('slug', '2u'),
                 ('description', '2U, Trilogy, Getsmarter -- external source for 2u courses and programs')]
            )),
        ])
        emeritus_course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+emeritusSourceX'),
            ('key', 'edX+emeritusSourceX'),
            ('title', 'test course 3'),
            ('product_source', 'emeritus'),
        ])
        null_source_course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+nullSourceX'),
            ('key', 'edX+nullSourceX'),
            ('title', 'test course 4'),
            ('product_source', None),
        ])
        mock_client.return_value.get_metadata_by_query.return_value = [
            edx_course_metadata,
            twou_course_metadata,
            emeritus_course_metadata,
            null_source_course_metadata,
        ]
        catalog = factories.EnterpriseCatalogFactory()
        self.assertEqual(ContentMetadata.objects.count(), 0)
        update_contentmetadata_from_discovery(catalog.catalog_query)
        mock_client.assert_called_once()
        self.assertEqual(ContentMetadata.objects.count(), 3)

    @override_settings(DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT=0)
    @mock.patch('enterprise_catalog.apps.api_client.discovery.DiscoveryApiClient')
    def test_contentmetadata_update_from_discovery(self, mock_client):
        """
        update_contentmetadata_from_discovery should update or create ContentMetadata
        objects from the discovery service /search/all api call.
        """
        course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+testX'),
            ('key', 'edX+testX'),
            ('title', 'test course'),
        ])
        course_run_metadata = OrderedDict([
            ('aggregation_key', 'courserun:edX+testX'),
            ('key', 'course-v1:edX+testX+1'),
            ('title', 'test course run'),
        ])
        program_metadata = OrderedDict([
            ('aggregation_key', 'program:c7d546f2-a442-49d2-8ef1-4cb64f46df88'),
            ('title', 'test program'),
            ('uuid', '6e8e47ed-28d8-4861-917e-cedca1135a3f'),
        ])
        mock_client.return_value.get_metadata_by_query.return_value = [
            course_metadata,
            course_run_metadata,
            program_metadata,
        ]
        catalog = factories.EnterpriseCatalogFactory()

        self.assertEqual(ContentMetadata.objects.count(), 0)
        update_contentmetadata_from_discovery(catalog.catalog_query)
        mock_client.assert_called_once()
        self.assertEqual(ContentMetadata.objects.count(), 3)

        associated_metadata = catalog.content_metadata

        # Assert stored content metadata is correct for each type
        course_cm = ContentMetadata.objects.get(content_key=course_metadata['key'])
        self.assertEqual(course_cm.content_type, COURSE)
        self.assertEqual(course_cm.parent_content_key, None)
        self.assertEqual(course_cm.json_metadata, course_metadata)
        assert course_cm in associated_metadata

        course_run_cm = ContentMetadata.objects.get(content_key=course_run_metadata['key'])
        self.assertEqual(course_run_cm.content_type, COURSE_RUN)
        self.assertEqual(course_run_cm.parent_content_key, course_metadata['key'])
        self.assertEqual(course_run_cm.json_metadata, course_run_metadata)
        assert course_run_cm in associated_metadata

        program_cm = ContentMetadata.objects.get(content_key=program_metadata['uuid'])
        self.assertEqual(program_cm.content_type, PROGRAM)
        self.assertEqual(program_cm.parent_content_key, None)
        self.assertEqual(program_cm.json_metadata, program_metadata)
        assert program_cm in associated_metadata

        # Run again with existing ContentMetadata database objects, temporarily modifying
        # the json_metadata of the existing course to remove a field that will later be
        # added. Assert the existing json_metadata field is updated with the correct metadata
        # to include /search/all fields (e.g., aggregation_key).
        course_cm = ContentMetadata.objects.get(content_key=course_metadata['key'])
        course_cm.json_metadata = {
            'key': course_metadata['key'],
            'title': course_metadata['title'],
        }
        course_cm.save()
        update_contentmetadata_from_discovery(catalog.catalog_query)
        self.assertEqual(ContentMetadata.objects.count(), 3)  # assert all ContentMetadata objects are preserved
        course_cm = ContentMetadata.objects.get(content_key=course_metadata['key'])
        # assert json_metadata is updated to include fields plucked from /search/all metadata.
        self.assertEqual(
            json.dumps(course_cm.json_metadata, sort_keys=True),
            json.dumps(course_metadata, sort_keys=True),
        )

        # Run again and expect that we will unassociate some content metadata
        # from catalog query while perserving the content metadata objects
        # themselves.
        mock_client.return_value.get_metadata_by_query.return_value = [program_metadata]
        update_contentmetadata_from_discovery(catalog.catalog_query)
        self.assertEqual(ContentMetadata.objects.count(), 3)

        associated_metadata = catalog.content_metadata
        assert course_cm not in associated_metadata
        assert course_run_cm not in associated_metadata
        assert program_cm in associated_metadata

    @override_settings(DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT=0)
    @mock.patch('enterprise_catalog.apps.api_client.discovery.DiscoveryApiClient')
    def test_contentmetadata_update_from_discovery_ignore_exec_ed(self, mock_client):
        """
        update_contentmetadata_from_discovery should update or create ContentMetadata
        objects from the discovery service /search/all api call.
        this test should filter out content which does not meet our course_type criteria
        """
        audit_course_metadata_key = f'edX+auditX-{str(uuid4())}'
        audit_course_metadata = OrderedDict([
            ('aggregation_key', f'course:{audit_course_metadata_key}'),
            ('key', audit_course_metadata_key),
            ('title', 'test course'),
            ('course_type', 'audit'),
        ])
        exec_ed_course_metadata_key = f'edX+exedEdX-{str(uuid4())}'
        exec_ed_course_metadata = OrderedDict([
            ('aggregation_key', f'course:{exec_ed_course_metadata_key}'),
            ('key', exec_ed_course_metadata_key),
            ('title', 'test course'),
            ('course_type', 'executive-education-2u'),
        ])
        course_run_metadata = OrderedDict([
            ('aggregation_key', f'courserun:{audit_course_metadata_key}'),
            ('key', f'course-v1:{audit_course_metadata_key}+1'),
            ('title', 'test course run'),
        ])
        program_metadata_uuid = str(uuid4())
        program_metadata = OrderedDict([
            ('aggregation_key', f'program:{program_metadata_uuid}'),
            ('title', 'test program'),
            ('uuid', program_metadata_uuid),
        ])
        mock_client.return_value.get_metadata_by_query.return_value = [
            audit_course_metadata,
            exec_ed_course_metadata,
            course_run_metadata,
            program_metadata,
        ]
        catalog = factories.EnterpriseCatalogFactory()

        self.assertEqual(ContentMetadata.objects.count(), 0)
        update_contentmetadata_from_discovery(catalog.catalog_query)
        mock_client.assert_called_once()
        self.assertEqual(ContentMetadata.objects.count(), 4)

        associated_metadata = catalog.content_metadata

        # Assert stored content metadata is correct for each type
        course_cm = ContentMetadata.objects.get(content_key=audit_course_metadata['key'])
        self.assertEqual(course_cm.content_type, COURSE)
        self.assertEqual(course_cm.parent_content_key, None)
        self.assertEqual(course_cm.json_metadata, audit_course_metadata)
        assert course_cm in associated_metadata

        course_run_cm = ContentMetadata.objects.get(content_key=course_run_metadata['key'])
        self.assertEqual(course_run_cm.content_type, COURSE_RUN)
        self.assertEqual(course_run_cm.parent_content_key, audit_course_metadata['key'])
        self.assertEqual(course_run_cm.json_metadata, course_run_metadata)
        assert course_run_cm in associated_metadata

        program_cm = ContentMetadata.objects.get(content_key=program_metadata['uuid'])
        self.assertEqual(program_cm.content_type, PROGRAM)
        self.assertEqual(program_cm.parent_content_key, None)
        self.assertEqual(program_cm.json_metadata, program_metadata)
        assert program_cm in associated_metadata

        # Run again with existing ContentMetadata database objects, temporarily modifying
        # the json_metadata of the existing course to remove a field that will later be
        # added. Assert the existing json_metadata field is updated with the correct metadata
        # to include /search/all fields (e.g., aggregation_key).
        course_cm = ContentMetadata.objects.get(content_key=audit_course_metadata['key'])
        course_cm.json_metadata = {
            'key': audit_course_metadata['key'],
            'title': audit_course_metadata['title'],
            'course_type': audit_course_metadata['course_type'],
        }
        course_cm.save()
        update_contentmetadata_from_discovery(catalog.catalog_query)
        self.assertEqual(ContentMetadata.objects.count(), 4)  # assert all ContentMetadata objects are preserved
        course_cm = ContentMetadata.objects.get(content_key=audit_course_metadata['key'])
        # assert json_metadata is updated to include fields plucked from /search/all metadata.
        self.assertEqual(
            json.dumps(course_cm.json_metadata, sort_keys=True),
            json.dumps(audit_course_metadata, sort_keys=True),
        )

        # Run again and expect that we will unassociate some content metadata
        # from catalog query while perserving the content metadata objects
        # themselves.
        mock_client.return_value.get_metadata_by_query.return_value = [program_metadata]
        update_contentmetadata_from_discovery(catalog.catalog_query)
        self.assertEqual(ContentMetadata.objects.count(), 4)

        associated_metadata = catalog.content_metadata
        assert course_cm not in associated_metadata
        assert course_run_cm not in associated_metadata
        assert program_cm in associated_metadata

    @override_settings(DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT=0)
    @mock.patch('enterprise_catalog.apps.api_client.discovery.DiscoveryApiClient')
    def test_contentmetadata_update_from_discovery_dry_run_create(self, mock_client):
        """
        update_contentmetadata_from_discovery should not create ContentMetadata
        objects from the discovery service /search/all api call under dry_run option
        """
        course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+testX'),
            ('key', 'edX+testX'),
            ('title', 'test course'),
        ])
        course_run_metadata = OrderedDict([
            ('aggregation_key', 'courserun:edX+testX'),
            ('key', 'course-v1:edX+testX+1'),
            ('title', 'test course run'),
        ])
        program_metadata = OrderedDict([
            ('aggregation_key', 'program:c7d546f2-a442-49d2-8ef1-4cb64f46df88'),
            ('title', 'test program'),
            ('uuid', '6e8e47ed-28d8-4861-917e-cedca1135a3f'),
        ])
        mock_client.return_value.get_metadata_by_query.return_value = [
            course_metadata,
            course_run_metadata,
            program_metadata,
        ]
        catalog = factories.EnterpriseCatalogFactory()

        self.assertEqual(ContentMetadata.objects.count(), 0)
        update_contentmetadata_from_discovery(catalog.catalog_query, dry_run=True)
        mock_client.assert_called_once()
        self.assertEqual(ContentMetadata.objects.count(), 0)

    @override_settings(DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT=0)
    @mock.patch('enterprise_catalog.apps.api_client.discovery.DiscoveryApiClient')
    def test_contentmetadata_update_from_discovery_dry_run_update(self, mock_client):
        """
        update_contentmetadata_from_discovery should not update ContentMetadata
        objects from the discovery service /search/all api call under dry_run option
        """
        course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+testX'),
            ('key', 'edX+testX'),
            ('title', 'test course'),
        ])
        course_run_metadata = OrderedDict([
            ('aggregation_key', 'courserun:edX+testX'),
            ('key', 'course-v1:edX+testX+1'),
            ('title', 'test course run'),
        ])
        program_metadata = OrderedDict([
            ('aggregation_key', 'program:c7d546f2-a442-49d2-8ef1-4cb64f46df88'),
            ('title', 'test program'),
            ('uuid', '6e8e47ed-28d8-4861-917e-cedca1135a3f'),
        ])
        mock_client.return_value.get_metadata_by_query.return_value = [
            course_metadata,
            course_run_metadata,
            program_metadata,
        ]
        catalog = factories.EnterpriseCatalogFactory()

        self.assertEqual(ContentMetadata.objects.count(), 0)
        update_contentmetadata_from_discovery(catalog.catalog_query)
        mock_client.assert_called_once()
        self.assertEqual(ContentMetadata.objects.count(), 3)

        associated_metadata = catalog.content_metadata

        # Assert stored content metadata is correct for each type
        course_cm = ContentMetadata.objects.get(content_key=course_metadata['key'])
        self.assertEqual(course_cm.content_type, COURSE)
        self.assertEqual(course_cm.parent_content_key, None)
        self.assertEqual(course_cm.json_metadata, course_metadata)
        assert course_cm in associated_metadata

        course_run_cm = ContentMetadata.objects.get(content_key=course_run_metadata['key'])
        self.assertEqual(course_run_cm.content_type, COURSE_RUN)
        self.assertEqual(course_run_cm.parent_content_key, course_metadata['key'])
        self.assertEqual(course_run_cm.json_metadata, course_run_metadata)
        assert course_run_cm in associated_metadata

        program_cm = ContentMetadata.objects.get(content_key=program_metadata['uuid'])
        self.assertEqual(program_cm.content_type, PROGRAM)
        self.assertEqual(program_cm.parent_content_key, None)
        self.assertEqual(program_cm.json_metadata, program_metadata)
        assert program_cm in associated_metadata

        # Run again with existing ContentMetadata database objects, temporarily modifying
        # the json_metadata of the existing course to remove a field that would later be
        # added in the dry_run=False case, verifying it doesn't update in the dry_run=True case
        course_cm = ContentMetadata.objects.get(content_key=course_metadata['key'])
        course_cm.json_metadata = {
            'key': course_metadata['key'],
            'title': course_metadata['title'],
        }
        course_cm.save()
        update_contentmetadata_from_discovery(catalog.catalog_query, dry_run=True)
        self.assertEqual(ContentMetadata.objects.count(), 3)  # assert all ContentMetadata objects are preserved
        course_cm = ContentMetadata.objects.get(content_key=course_metadata['key'])
        # assert json_metadata is not updated to include fields plucked from /search/all metadata.
        self.assertNotEqual(
            json.dumps(course_cm.json_metadata, sort_keys=True),
            json.dumps(course_metadata, sort_keys=True),
        )

    @contextmanager
    def _mock_enterprise_customer_cache(
        self,
        mock_enterprise_customer_return_value=None,
    ):
        """
        Helper to mock out all API client calls that would normally occur
        when ``EnterpriseCatalog.enterprise_customer`` is accessed.
        """
        path = 'enterprise_catalog.apps.api_client.enterprise_cache.'
        with mock.patch(path + 'EnterpriseApiClient') as mock_enterprise_api_client:
            mock_enterprise_api_client.return_value.get_enterprise_customer.return_value = \
                mock_enterprise_customer_return_value
            yield

    @ddt.data(
        {
            'is_learner_portal_enabled': True,
        },
        {
            'is_learner_portal_enabled': False,
        },
    )
    @ddt.unpack
    def test_get_content_enrollment_url(
        self,
        is_learner_portal_enabled,
    ):
        enterprise_uuid = uuid4()
        enterprise_slug = 'sluggy'
        content_key = 'course-key'

        enterprise_catalog = factories.EnterpriseCatalogFactory(enterprise_uuid=enterprise_uuid)
        content_metadata = factories.ContentMetadataFactory(
            content_key=content_key,
            content_type=COURSE,
        )
        enterprise_catalog.catalog_query.contentmetadata_set.add(*[content_metadata])

        mock_enterprise_customer_return_value = {
            'slug': enterprise_slug,
            'enable_learner_portal': is_learner_portal_enabled,
        }

        with self._mock_enterprise_customer_cache(
            mock_enterprise_customer_return_value,
        ):
            content_enrollment_url = enterprise_catalog.get_content_enrollment_url(content_metadata)

        if is_learner_portal_enabled:
            assert settings.ENTERPRISE_LEARNER_PORTAL_BASE_URL in content_enrollment_url
        else:
            assert settings.LMS_BASE_URL in content_enrollment_url

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    @ddt.data(
        {
            'is_learner_portal_enabled': True,
        },
        {
            'is_learner_portal_enabled': False,
        },
    )
    @ddt.unpack
    def test_enrollment_url_exec_ed(
        self,
        mock_enterprise_api_client,
        is_learner_portal_enabled,
    ):
        """
        Test that a correct enrollment URL is returned for exec ed. 2U courses.
        """
        enterprise_catalog = factories.EnterpriseCatalogFactory()
        content_metadata = factories.ContentMetadataFactory(
            content_key='the-content-key',
            content_type=COURSE,
        )
        content_metadata._json_metadata.update({  # pylint: disable=protected-access
            'course_type': EXEC_ED_2U_COURSE_TYPE,
            'entitlements': [{
                'mode': EXEC_ED_2U_ENTITLEMENT_MODE,
                'sku': 'happy-little-sku',
            }],
        })
        enterprise_catalog.catalog_query.contentmetadata_set.add(*[content_metadata])
        enterprise_slug = 'sluggy'
        mock_enterprise_customer_return_value = {
            'slug': enterprise_slug,
            'enable_learner_portal': is_learner_portal_enabled,
        }
        mock_enterprise_api_client.return_value.get_enterprise_customer.return_value =\
            mock_enterprise_customer_return_value

        actual_enrollment_url = enterprise_catalog.get_content_enrollment_url(content_metadata)

        if is_learner_portal_enabled:
            assert settings.ENTERPRISE_LEARNER_PORTAL_BASE_URL in actual_enrollment_url
        else:
            assert 'happy-little-sku' in actual_enrollment_url
            assert 'proxy-login' in actual_enrollment_url

    @override_settings(DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT=0)
    @mock.patch('enterprise_catalog.apps.api_client.discovery.DiscoveryApiClient')
    def test_associate_content_metadata_with_query_guardrails(self, mock_client):
        """
        Test the limitations of the `associate_content_metadata_with_query_guardrails` and situations where content
        association sets are blocked from updates
        """
        # Set up our catalog and query
        catalog = factories.EnterpriseCatalogFactory()

        # Mock discovery returning a single metadata record for our query
        course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+testX'),
            ('key', 'edX+testX'),
            ('title', 'test course'),
        ])
        mock_client.return_value.get_metadata_by_query.return_value = [course_metadata]

        # The catalog has no values, and falls under the guard rails minimum threshold so the update should be
        # uninhibited
        update_contentmetadata_from_discovery(catalog.catalog_query)
        assert len(catalog.catalog_query.contentmetadata_set.all()) == 1

        # Build an existing content metadata set that will surpass the minimum
        content_metadata = []
        for x in range(100):
            content_metadata.append(
                factories.ContentMetadataFactory(
                    content_key=f'the-content-key-{x}',
                    content_type=COURSE,
                )
            )
        catalog.catalog_query.contentmetadata_set.set(content_metadata, clear=True)

        # Move the modified to before today
        catalog.catalog_query.modified -= timedelta(days=2)
        # Now if we run the update, with discovery mocked to return a single item, the update will be blocked and
        # retain the 100 records since the modified at of the query isn't today
        update_contentmetadata_from_discovery(catalog.catalog_query)
        assert len(catalog.catalog_query.contentmetadata_set.all()) == 100

        # updates that results in a net positive change in number of content record associations will be allowed
        # so long as they fall under the threshold
        course_metadata_list = []
        for x in range(120):
            course_metadata_list.append(OrderedDict([
                ('aggregation_key', f'course:edX+testX-{x}'),
                ('key', f'edX+testX-{x}'),
                ('title', f'test course-{x}'),
            ]))
        # Mock discovery to return 101 returns
        mock_client.return_value.get_metadata_by_query.return_value = course_metadata_list
        update_contentmetadata_from_discovery(catalog.catalog_query)
        assert len(catalog.catalog_query.contentmetadata_set.all()) == 120
        for x in range(120):
            course_metadata_list.append(OrderedDict([
                ('aggregation_key', f'course:edX+testX-{x}'),
                ('key', f'edX+testX-{x}'),
                ('title', f'test course-{x}'),
            ]))
        mock_client.return_value.get_metadata_by_query.return_value = course_metadata_list
        update_contentmetadata_from_discovery(catalog.catalog_query)
        # with the 120 additional records returned, that exceeds the threshold
        assert len(catalog.catalog_query.contentmetadata_set.all()) == 120

        # Now that the current contentmetadata_set is of length 120 mock discovery to return just one record again
        mock_client.return_value.get_metadata_by_query.return_value = [course_metadata]
        # Move the modified at time to allow the update to go through
        catalog.catalog_query.modified = localized_utcnow()
        update_contentmetadata_from_discovery(catalog.catalog_query)
        assert len(catalog.catalog_query.contentmetadata_set.all()) == 1

    def test_bulk_update_changes_modified_time(self):
        """
        Test that `ContentMetadata.objects.bulk_update()` changes
        the modified time of the updated records.
        """
        original_modified_time = localized_utcnow()
        records = factories.ContentMetadataFactory.create_batch(10, modified=original_modified_time)

        for record in records:
            record._json_metadata['extra_stuff'] = 'foo'  # pylint: disable=protected-access

        ContentMetadata.objects.bulk_update(records, ['_json_metadata'], batch_size=10)

        for record in records:
            record.refresh_from_db()
            self.assertGreater(record.modified, original_modified_time)

    def test_restricted_runs_allowed_happy_path(self):
        """
        Test the happy path for computing a CatalogQuery's `restricted_runs_allowed`.
        """
        restricted_runs_dict = {
            "course:edX+FUN": [
                "course-v1:edX+FUN+3T2024",
                "course-v1:edX+FUN+4T2024",
            ],
            "course:edX+GAMES": [
                "course-v1:edX+GAMES+3T2024",
                "course-v1:edX+GAMES+4T2024",
            ]
        }
        content_filter = {
            'other': 'stuff',
            RESTRICTED_RUNS_ALLOWED_KEY: restricted_runs_dict
        }
        catalog_query = factories.CatalogQueryFactory(content_filter=content_filter)
        catalog = factories.EnterpriseCatalogFactory(
            catalog_query=catalog_query,
        )

        expected_restricted_runs_dict = {
            "edX+FUN": [
                "course-v1:edX+FUN+3T2024",
                "course-v1:edX+FUN+4T2024",
            ],
            "edX+GAMES": [
                "course-v1:edX+GAMES+3T2024",
                "course-v1:edX+GAMES+4T2024",
            ]
        }
        self.assertEqual(
            expected_restricted_runs_dict,
            catalog_query.restricted_runs_allowed,
        )
        self.assertEqual(
            expected_restricted_runs_dict,
            catalog.restricted_runs_allowed,
        )

    @ddt.data(
        ['some+course+run'],
        'some+course+run',
        {},
        [],
        '',
    )
    def test_restricted_runs_are_none(self, restricted_runs_dict):
        """
        Tests all the cases that should result in a restricted_runs_allowed of None.
        """
        content_filter = {
            'other': 'stuff',
            RESTRICTED_RUNS_ALLOWED_KEY: restricted_runs_dict
        }
        catalog_query = factories.CatalogQueryFactory(content_filter=content_filter)
        catalog = factories.EnterpriseCatalogFactory(
            catalog_query=catalog_query,
        )

        self.assertIsNone(catalog_query.restricted_runs_allowed)
        self.assertIsNone(catalog.restricted_runs_allowed)


@ddt.ddt
class TestRestrictedRunsModels(TestCase):
    """
    Tests for the following models pertaining to the "restricted runs" feature:
    * RestrictedCourseMetadata
    * RestrictedRunAllowedForRestrictedCourse
    """

    def _create_objects_and_relationships(
        self,
        create_catalog_query,
        create_content_metadata=None,
        create_restricted_courses=None,
        create_restricted_run_allowed_for_restricted_course=None,
    ):
        """
        Helper function to create an arbitrary number of CatalogQuery, ContentMetadata,
        RestrictedCourseMetadata, and RestrictedRunAllowedForRestrictedCourse objects for testing
        purposes.
        """
        catalog_queries = {
            cq_uuid: factories.CatalogQueryFactory(
                uuid=cq_uuid,
                content_filter=cq_info['content_filter'] | {'force_unique': cq_uuid},
            ) for cq_uuid, cq_info in create_catalog_query.items()
        }
        content_metadata = {}
        create_content_metadata = create_content_metadata or {}
        for course_key, course_info in create_content_metadata.items():
            course = factories.ContentMetadataFactory(
                content_key=course_key,
                content_type=COURSE,
                _json_metadata=course_info['json_metadata'],
            )
            content_metadata.update({course_key: course})
            if cq_uuid := course_info['associate_with_catalog_query']:
                course.catalog_queries.set([catalog_queries[cq_uuid]])
            for run_key, run_info in course_info['create_runs'].items():
                run = factories.ContentMetadataFactory(
                    content_key=run_key,
                    parent_content_key=course_key,
                    content_type=COURSE_RUN,
                )
                if run_info['is_restricted']:
                    # pylint: disable=protected-access
                    run._json_metadata.update({'restriction_type': 'custom-b2b-enterprise'})
                    run.save()
                content_metadata.update({run_key: run})
        restricted_courses = {
            id: factories.RestrictedCourseMetadataFactory(
                id=id,
                content_key=restricted_course_info['content_key'],
                unrestricted_parent=content_metadata[restricted_course_info['content_key']],
                catalog_query=catalog_queries[restricted_course_info['catalog_query']],
                _json_metadata=restricted_course_info['json_metadata'],
            ) for id, restricted_course_info in create_restricted_courses.items()
        } if create_restricted_courses else {}
        for mapping_info in create_restricted_run_allowed_for_restricted_course or []:
            factories.RestrictedRunAllowedForRestrictedCourseFactory(
                course=restricted_courses[mapping_info['course']],
                run=content_metadata[mapping_info['run']],
            )
        main_catalog = factories.EnterpriseCatalogFactory(
            catalog_query=catalog_queries['11111111-1111-1111-1111-111111111111'],
        )
        return main_catalog, catalog_queries, content_metadata, restricted_courses

    @ddt.data(
        # Skip creating any content metadata at all. The result should be empty.
        {
            'create_catalog_query': {
                '11111111-1111-1111-1111-111111111111': {
                    'content_filter': {},
                },
            },
            'expected_json_metadata': [],
            'expected_json_metadata_with_restricted': [],
        },
        # Create a simple course and run, but it is not part of the catalog. The result should be empty.
        {
            'create_catalog_query': {
                '11111111-1111-1111-1111-111111111111': {
                    'content_filter': {},
                },
                '22222222-2222-2222-2222-222222222222': {
                    'content_filter': {},
                },
            },
            'create_content_metadata': {
                'edX+course': {
                    'create_runs': {
                        'course-v1:edX+course+run1': {'is_restricted': False},
                    },
                    'json_metadata': {'foobar': 'base metadata'},
                    'associate_with_catalog_query': '22222222-2222-2222-2222-222222222222',  # different!
                },
            },
            'expected_json_metadata': [],
            'expected_json_metadata_with_restricted': [],
        },
        # Create a simple course and run, associated with the catalog.
        {
            'create_catalog_query': {
                '11111111-1111-1111-1111-111111111111': {
                    'content_filter': {},
                },
            },
            'create_content_metadata': {
                'edX+course': {
                    'create_runs': {
                        'course-v1:edX+course+run1': {'is_restricted': False},
                    },
                    'json_metadata': {'foobar': 'base metadata'},
                    'associate_with_catalog_query': '11111111-1111-1111-1111-111111111111',
                },
            },
            'expected_json_metadata': [
                {'foobar': 'base metadata'},
            ],
            'expected_json_metadata_with_restricted': [
                {'foobar': 'base metadata'},
            ],
        },
        # Create a course with a restricted run, but the run is not allowed by the main CatalogQuery.
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
                '22222222-2222-2222-2222-222222222222': {
                    'content_filter': {},
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
                    'catalog_query': '22222222-2222-2222-2222-222222222222',
                    'json_metadata': {'foobar': 'override metadata'},
                },
            },
            'create_restricted_run_allowed_for_restricted_course': [
                {'course': 1, 'run': 'course-v1:edX+course+run2'},
            ],
            'expected_json_metadata': [
                {'foobar': 'base metadata'},
            ],
            'expected_json_metadata_with_restricted': [
                {'foobar': 'base metadata'},
            ],
        },
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
            'expected_json_metadata': [
                {'foobar': 'base metadata'},
            ],
            'expected_json_metadata_with_restricted': [
                {'foobar': 'override metadata'},
            ],
        },
        # Create a course with ONLY an unrestricted run (run1), and the restricted run is allowed by the CatalogQuery.
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
                        'course-v1:edX+course+run1': {'is_restricted': True},
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
                {'course': 1, 'run': 'course-v1:edX+course+run1'},
            ],
            'expected_json_metadata': [
                {'foobar': 'base metadata'},
            ],
            'expected_json_metadata_with_restricted': [
                {'foobar': 'override metadata'},
            ],
        },
    )
    @ddt.unpack
    def test_catalog_content_metadata_with_restricted_runs(
        self,
        create_catalog_query,
        create_content_metadata=None,
        create_restricted_courses=None,
        create_restricted_run_allowed_for_restricted_course=None,
        expected_json_metadata=None,
        expected_json_metadata_with_restricted=None,
    ):
        """
        Test the content_metadata() method of EnterpriseCatalog instances, as well as the newer
        content_metadata_with_restricted() method.

        The second method should cause courses to be serialized with json_metadata conditionally
        overriden from a related RestrictedCourseMetadata instance, if one exists for the requested
        catalog.
        """
        main_catalog, _, _, _ = self._create_objects_and_relationships(
            create_catalog_query,
            create_content_metadata,
            create_restricted_courses,
            create_restricted_run_allowed_for_restricted_course,
        )
        expected_json_metadata = expected_json_metadata or []
        expected_json_metadata_with_restricted = expected_json_metadata_with_restricted or []
        actual_json_metadata = [m.json_metadata for m in main_catalog.content_metadata]
        actual_json_metadata_with_restricted = [m.json_metadata for m in main_catalog.content_metadata_with_restricted]
        assert actual_json_metadata == expected_json_metadata
        assert actual_json_metadata_with_restricted == expected_json_metadata_with_restricted

    @ddt.data(
        # Skip creating any content metadata at all. The result should be empty.
        {
            'create_catalog_query': {
                '11111111-1111-1111-1111-111111111111': {
                    'content_filter': {},
                },
            },
            'requested_content_keys': ['course-v1:edX+course+run1'],
            'expected_json_metadata': [],
            'expected_json_metadata_with_restricted': [],
        },
        # Create a simple course and run, but it is not part of the catalog. The result should be empty.
        {
            'create_catalog_query': {
                '11111111-1111-1111-1111-111111111111': {
                    'content_filter': {},
                },
                '22222222-2222-2222-2222-222222222222': {
                    'content_filter': {},
                },
            },
            'create_content_metadata': {
                'edX+course': {
                    'create_runs': {
                        'course-v1:edX+course+run1': {'is_restricted': False},
                    },
                    'json_metadata': {'foobar': 'base metadata'},
                    'associate_with_catalog_query': '22222222-2222-2222-2222-222222222222',  # different!
                },
            },
            'requested_content_keys': ['course-v1:edX+course+run1'],
            'expected_json_metadata': [],
            'expected_json_metadata_with_restricted': [],
        },
        # Create a simple course and run, associated with the catalog.
        {
            'create_catalog_query': {
                '11111111-1111-1111-1111-111111111111': {
                    'content_filter': {},
                },
            },
            'create_content_metadata': {
                'edX+course': {
                    'create_runs': {
                        'course-v1:edX+course+run1': {'is_restricted': False},
                    },
                    'json_metadata': {'foobar': 'base metadata'},
                    'associate_with_catalog_query': '11111111-1111-1111-1111-111111111111',
                },
            },
            'requested_content_keys': ['course-v1:edX+course+run1'],
            'expected_json_metadata': [
                {'foobar': 'base metadata'},
            ],
            'expected_json_metadata_with_restricted': [
                {'foobar': 'base metadata'},
            ],
        },
        # Create a course with a restricted run, but the run is not allowed by the main CatalogQuery.
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
                '22222222-2222-2222-2222-222222222222': {
                    'content_filter': {},
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
                    # Not the caller's catalog!
                    'catalog_query': '22222222-2222-2222-2222-222222222222',
                    'json_metadata': {'foobar': 'override metadata'},
                },
            },
            'create_restricted_run_allowed_for_restricted_course': [
                {'course': 1, 'run': 'course-v1:edX+course+run2'},
            ],
            'requested_content_keys': ['course-v1:edX+course+run2'],
            'expected_json_metadata': [
                # run2 was not found because it is restricted.
            ],
            'expected_json_metadata_with_restricted': [
                # run2 was not found because it is not allowed by the caller's catalog.
            ],
        },
        # Create a course with both an unrestricted (run1) and restricted run (run2), and the
        # restricted run is allowed by the CatalogQuery. Request the UNRESTRICTED run (run1) anyway
        # and assert that the override course metadata is returned.
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
            'requested_content_keys': ['course-v1:edX+course+run1'],
            'expected_json_metadata': [
                {'foobar': 'base metadata'},
            ],
            'expected_json_metadata_with_restricted': [
                # We supply the override course metadata *even though* the
                # requested content key represents an unrestricted run.
                {'foobar': 'override metadata'},
            ],
        },
        # Create a course with ONLY an unrestricted run (run1), and the restricted run is allowed by the CatalogQuery.
        # This type of course has colloquially been referred to as "Unicorn".
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
                        # The only run is a restricted run.
                        'course-v1:edX+course+run1': {'is_restricted': True},
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
                {'course': 1, 'run': 'course-v1:edX+course+run1'},
            ],
            'requested_content_keys': ['course-v1:edX+course+run1'],
            'expected_json_metadata': [
                # The RUN is invisible to the requester because it is restricted, so the COURSE
                # should not be found either.
            ],
            'expected_json_metadata_with_restricted': [
                {'foobar': 'override metadata'},
            ],
        },
    )
    @ddt.unpack
    def test_get_matching_content_with_restricted_runs(
        self,
        create_catalog_query,
        create_content_metadata=None,
        create_restricted_courses=None,
        create_restricted_run_allowed_for_restricted_course=None,
        requested_content_keys=None,
        expected_json_metadata=None,
        expected_json_metadata_with_restricted=None,
    ):
        """
        Test the get_matching_content() method of EnterpriseCatalog instances, both with and without
        passing include_restricted=True.

        An example of how we expect behavior to change after passing include_restricted:
        If the requester's catalog allows a restricted run, then passing that run into
        get_matching_content(include_restricted=False) will yield an empty list, whereas
        get_matching_content(include_restricted=True) will return the parent course.

        Restricted runs should always seem non-existent by default.
        """
        main_catalog, _, _, _ = self._create_objects_and_relationships(
            create_catalog_query,
            create_content_metadata,
            create_restricted_courses,
            create_restricted_run_allowed_for_restricted_course,
        )
        requested_content_keys = requested_content_keys or []
        expected_json_metadata = expected_json_metadata or []
        expected_json_metadata_with_restricted = expected_json_metadata_with_restricted or []
        actual_json_metadata = [m.json_metadata for m in main_catalog.get_matching_content(requested_content_keys)]
        actual_json_metadata_with_restricted = [
            m.json_metadata for m in main_catalog.get_matching_content(requested_content_keys, include_restricted=True)
        ]
        assert actual_json_metadata == expected_json_metadata
        assert actual_json_metadata_with_restricted == expected_json_metadata_with_restricted

    def test_store_canonical_record(self):
        """
        Test that the canonical record is stored with all restricted runs.
        """
        content_metadata_dict = {
            'key': 'edX+course',
            'uuid': '11111111-1111-1111-1111-111111111111',
            'content_type': COURSE,
            'course_runs': [
                {
                    'key': 'course-v1:edX+course+run1',
                    'is_restricted': False,
                    'status': 'published',
                },
                {
                    'key': 'course-v1:edX+course+run2',
                    'is_restricted': True,
                    'status': 'unpublished',
                    COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                },
                {
                    'key': 'course-v1:edX+course+run3',
                    'is_restricted': True,
                    'status': 'other',
                    COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                },
            ],
        }
        parent_record = factories.ContentMetadataFactory.create(
            content_key='edX+course',
            content_type=COURSE,
        )

        record = RestrictedCourseMetadata.store_canonical_record(content_metadata_dict)

        self.assertEqual(record.json_metadata['course_runs'], content_metadata_dict['course_runs'])
        self.assertEqual(record.content_key, content_metadata_dict['key'])
        self.assertEqual(record.content_uuid, content_metadata_dict['uuid'])
        self.assertEqual(record.content_type, content_metadata_dict['content_type'])
        self.assertEqual(record.unrestricted_parent, parent_record)
        self.assertIsNone(record.catalog_query)

    def test_store_record_with_query(self):
        """
        Tests that a restricted course to be associated with a particular query
        stores only course run information for unrestricted courses and restricted
        courses allowed by the query.
        """
        catalog_query = factories.CatalogQueryFactory(
            content_filter={
                'restricted_runs_allowed': {
                    'course:edX+course': [
                        'course-v1:edX+course+run2',
                    ],
                },
            },
        )
        content_metadata_dict = {
            'key': 'edX+course',
            'uuid': '11111111-1111-1111-1111-111111111111',
            'content_type': COURSE,
            'course_runs': [
                {
                    'key': 'course-v1:edX+course+run1',
                    'is_restricted': False,
                    'status': 'published',
                    'uuid': str(uuid4()),
                },
                {
                    'key': 'course-v1:edX+course+run2',
                    'is_restricted': True,
                    COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                    'status': 'unpublished',
                    'uuid': str(uuid4()),
                },
                {
                    'key': 'course-v1:edX+course+run3',
                    'is_restricted': True,
                    COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                    'status': 'other',
                    'uuid': str(uuid4()),
                },
            ],
        }
        parent_record = factories.ContentMetadataFactory.create(
            content_key='edX+course',
            content_type=COURSE,
        )

        record = RestrictedCourseMetadata.store_record_with_query(
            content_metadata_dict,
            catalog_query,
        )

        self.assertEqual(
            record.json_metadata['course_runs'],
            [
                {
                    'key': 'course-v1:edX+course+run1',
                    'is_restricted': False,
                    'status': 'published',
                    'uuid': content_metadata_dict['course_runs'][0]['uuid'],
                },
                {
                    'key': 'course-v1:edX+course+run2',
                    'is_restricted': True,
                    COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                    'status': 'unpublished',
                    'uuid': content_metadata_dict['course_runs'][1]['uuid']
                },
            ],
        )
        self.assertEqual(
            record.json_metadata['course_run_keys'],
            ['course-v1:edX+course+run1', 'course-v1:edX+course+run2'],
        )
        self.assertEqual(
            record.json_metadata['course_run_statuses'],
            ['published', 'unpublished'],
        )
        self.assertEqual(record.content_key, content_metadata_dict['key'])
        self.assertEqual(str(record.content_uuid), content_metadata_dict['uuid'])
        self.assertEqual(record.content_type, content_metadata_dict['content_type'])
        self.assertEqual(record.unrestricted_parent, parent_record)
        self.assertEqual(record.catalog_query, catalog_query)
        self.assertEqual(
            list(record.restricted_run_allowed_for_restricted_course.all().values_list(
                'content_key', flat=True,
            )),
            ['course-v1:edX+course+run2'],
        )

    @override_settings(SHOULD_FETCH_RESTRICTED_COURSE_RUNS=False)
    @mock.patch('enterprise_catalog.apps.catalog.models.DiscoveryApiClient')
    def test_synchronize_restricted_content_feature_disabled(self, mock_client):
        result = synchronize_restricted_content(mock.ANY)

        self.assertEqual([], result)
        self.assertFalse(mock_client.called)

    @override_settings(SHOULD_FETCH_RESTRICTED_COURSE_RUNS=True)
    @mock.patch('enterprise_catalog.apps.catalog.models.DiscoveryApiClient')
    def test_synchronize_restricted_content_query_has_no_restricted_content(self, mock_client):
        catalog_query = factories.CatalogQueryFactory(
            content_filter={'foo': 'bar'},
        )
        result = synchronize_restricted_content(catalog_query)

        self.assertEqual([], result)
        self.assertFalse(mock_client.called)

    @override_settings(DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT=0)
    @override_settings(SHOULD_FETCH_RESTRICTED_COURSE_RUNS=True)
    @mock.patch('enterprise_catalog.apps.catalog.models.DiscoveryApiClient')
    def test_synchronize_restricted_content(self, mock_client):
        """
        Tests that ``synchronize_restricted_content()`` creates restricted
        records.
        """
        catalog_query = factories.CatalogQueryFactory(
            content_filter={
                'restricted_runs_allowed': {
                    'course:edX+course': [
                        'course-v1:edX+course+run2',
                        'course-v1:edX+course+run3',
                    ],
                },
            },
        )
        content_metadata_dict = {
            'key': 'edX+course',
            'aggregation_key': 'course:edX+course',
            'uuid': '11111111-1111-1111-1111-111111111111',
            'content_type': COURSE,
            'course_runs': [
                {
                    'key': 'course-v1:edX+course+run1',
                    'aggregation_key': 'courserun:edX+course',
                    'is_restricted': False,
                    'status': 'published',
                    'uuid': str(uuid4()),
                },
                {
                    'key': 'course-v1:edX+course+run2',
                    'aggregation_key': 'courserun:edX+course',
                    'is_restricted': True,
                    COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                    'status': 'unpublished',
                    'uuid': str(uuid4()),
                },
                {
                    'key': 'course-v1:edX+course+run3',
                    'aggregation_key': 'courserun:edX+course',
                    'is_restricted': True,
                    COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                    'status': 'other',
                    'uuid': str(uuid4()),
                },
            ],
        }
        course_run_results = [
            {
                'key': 'course-v1:edX+course+run2',
                'aggregation_key': 'courserun:edX+course',
                'is_restricted': True,
                COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                'status': 'unpublished',
                'uuid': str(uuid4()),
                'other': 'stuff',
            },
            {
                'key': 'course-v1:edX+course+run3',
                'aggregation_key': 'courserun:edX+course',
                'is_restricted': True,
                COURSE_RUN_RESTRICTION_TYPE_KEY: RESTRICTION_FOR_B2B,
                'status': 'other',
                'uuid': str(uuid4()),
                'other': 'things',
            },
        ]
        parent_record = factories.ContentMetadataFactory.create(
            content_key='edX+course',
            content_type=COURSE,
        )
        mock_retrieve = mock_client.return_value.retrieve_metadata_for_content_filter
        mock_retrieve.side_effect = [
            [content_metadata_dict],
            course_run_results,
        ]

        result = synchronize_restricted_content(catalog_query)

        mock_retrieve.assert_has_calls([
            mock.call(
                {
                    'content_type': 'course',
                    'key': ['edX+course'],
                },
                QUERY_FOR_RESTRICTED_RUNS,
            ),
            mock.call(
                {
                    'content_type': 'courserun',
                    'key': ['course-v1:edX+course+run2', 'course-v1:edX+course+run3'],
                },
                QUERY_FOR_RESTRICTED_RUNS,
            ),
        ])
        self.assertEqual(result, ['edX+course', 'course-v1:edX+course+run2', 'course-v1:edX+course+run3'])
        self.assertIsNotNone(RestrictedCourseMetadata.objects.get(
            content_key=content_metadata_dict['key'],
            unrestricted_parent=parent_record,
            catalog_query=None,
        ))

        restricted_course = RestrictedCourseMetadata.objects.get(
            content_key=content_metadata_dict['key'],
            unrestricted_parent=parent_record,
            catalog_query=catalog_query,
        )
        restricted_runs = list(
            restricted_course.restricted_run_allowed_for_restricted_course.all().order_by(
                'content_key',
            )
        )
        self.assertEqual(
            [run.content_key for run in restricted_runs],
            ['course-v1:edX+course+run2', 'course-v1:edX+course+run3'],
        )
        self.assertEqual(restricted_runs[0].json_metadata['other'], 'stuff')
        self.assertEqual(restricted_runs[1].json_metadata['other'], 'things')
