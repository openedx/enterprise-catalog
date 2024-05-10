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
    EXEC_ED_2U_COURSE_TYPE,
    EXEC_ED_2U_ENTITLEMENT_MODE,
    PROGRAM,
)
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    _should_allow_metadata,
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
        content_metadata.json_metadata['course_type'] = course_type
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
        content_metadata.json_metadata['course_type'] = course_type
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
        content_metadata.json_metadata.update({
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
