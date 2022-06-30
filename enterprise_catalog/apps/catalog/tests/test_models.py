""" Tests for catalog models. """

import json
from collections import OrderedDict
from unittest import mock
from uuid import uuid4

import ddt
from django.conf import settings
from django.test import TestCase, override_settings

from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    PROGRAM,
)
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    update_contentmetadata_from_discovery,
)
from enterprise_catalog.apps.catalog.tests import factories


@ddt.ddt
class TestModels(TestCase):
    """ Models tests. """

    @override_settings(DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT=0)
    @mock.patch('enterprise_catalog.apps.api_client.discovery_cache.DiscoveryApiClient')
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
            ('aggregation_key', 'program:fake-uuid'),
            ('title', 'test program'),
            ('uuid', 'fake-uuid'),
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
    @mock.patch('enterprise_catalog.apps.api_client.discovery_cache.DiscoveryApiClient')
    def test_contentmetadata_update_from_discovery_ignore_exec_ed(self, mock_client):
        """
        update_contentmetadata_from_discovery should update or create ContentMetadata
        objects from the discovery service /search/all api call.
        this test should filter out content which does not meet our course_type criteria
        """
        # this course SHOULD appear in the catalog we save
        audit_course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+testX'),
            ('key', 'edX+testX'),
            ('title', 'test course'),
            ('course_type', 'audit'),
        ])
        # this course SHOULD NOT appear in the catalog we save
        exec_ed_course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+testX'),
            ('key', 'edX+testX'),
            ('title', 'test course'),
            ('course_type', 'executive-education-2u'),
        ])
        course_run_metadata = OrderedDict([
            ('aggregation_key', 'courserun:edX+testX'),
            ('key', 'course-v1:edX+testX+1'),
            ('title', 'test course run'),
        ])
        program_metadata = OrderedDict([
            ('aggregation_key', 'program:fake-uuid'),
            ('title', 'test program'),
            ('uuid', 'fake-uuid'),
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
        self.assertEqual(ContentMetadata.objects.count(), 3)

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
        self.assertEqual(ContentMetadata.objects.count(), 3)  # assert all ContentMetadata objects are preserved
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
        self.assertEqual(ContentMetadata.objects.count(), 3)

        associated_metadata = catalog.content_metadata
        assert course_cm not in associated_metadata
        assert course_run_cm not in associated_metadata
        assert program_cm in associated_metadata

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.LicenseManagerApiClient')
    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EcommerceApiClient')
    @ddt.data(
        {
            'is_integrated_customer_with_subsidies_and_offer': False,
            'is_course_in_subscriptions_catalog': True,
            'is_course_in_coupons_catalog': True,
            'should_direct_to_lp': True,
        },
        {
            'is_integrated_customer_with_subsidies_and_offer': True,
            'is_course_in_subscriptions_catalog': False,
            'is_course_in_coupons_catalog': False,
            'should_direct_to_lp': False,
        },
        {
            'is_integrated_customer_with_subsidies_and_offer': True,
            'is_course_in_subscriptions_catalog': True,
            'is_course_in_coupons_catalog': False,
            'should_direct_to_lp': True,
        },
        {
            'is_integrated_customer_with_subsidies_and_offer': True,
            'is_course_in_subscriptions_catalog': False,
            'is_course_in_coupons_catalog': True,
            'should_direct_to_lp': True,
        }
    )
    @ddt.unpack
    def test_get_content_enrollment_url(
        self,
        mock_ecommerce_client,
        mock_license_manager_client,
        mock_enterprise_api_client,
        is_integrated_customer_with_subsidies_and_offer,
        is_course_in_subscriptions_catalog,
        is_course_in_coupons_catalog,
        should_direct_to_lp
    ):
        enterprise_uuid = uuid4()
        enterprise_slug = 'sluggy'
        content_key = 'course-key'

        INTEGRATED_CUSTOMERS_WITH_SUBSIDIES_AND_OFFERS = []
        if is_integrated_customer_with_subsidies_and_offer:
            INTEGRATED_CUSTOMERS_WITH_SUBSIDIES_AND_OFFERS.append(str(enterprise_uuid))

        with self.settings(
            INTEGRATED_CUSTOMERS_WITH_SUBSIDIES_AND_OFFERS=INTEGRATED_CUSTOMERS_WITH_SUBSIDIES_AND_OFFERS
        ):
            enterprise_catalog = factories.EnterpriseCatalogFactory(enterprise_uuid=enterprise_uuid)
            content_metadata = factories.ContentMetadataFactory(content_key=content_key)
            enterprise_catalog.catalog_query.contentmetadata_set.add(*[content_metadata])

            mock_enterprise_api_client.return_value.get_enterprise_customer.return_value = {
                'slug': enterprise_slug,
                'enable_learner_portal': True,
            }

            if is_course_in_coupons_catalog:
                mock_ecommerce_client().get_coupons_overview.return_value = [
                    {
                        'enterprise_catalog_uuid': enterprise_catalog.uuid
                    }
                ]
            else:
                mock_ecommerce_client().get_coupons_overview.return_value = []

            if is_course_in_subscriptions_catalog:
                mock_license_manager_client().get_customer_agreement.return_value = {
                    'subscriptions': [{
                        'enterprise_catalog_uuid': enterprise_catalog.uuid
                    }]
                }
            else:
                mock_license_manager_client().get_customer_agreement.return_value = None

            content_enrollment_url = enterprise_catalog.get_content_enrollment_url(
                content_resource=COURSE,
                content_key=content_key,
                parent_content_key=None,
            )

            if should_direct_to_lp:
                assert settings.ENTERPRISE_LEARNER_PORTAL_BASE_URL in content_enrollment_url
            else:
                assert settings.LMS_BASE_URL in content_enrollment_url
