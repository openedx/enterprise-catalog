""" Tests for catalog models. """

import json
from collections import OrderedDict
from contextlib import contextmanager
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
    update_contentmetadata_from_discovery,
)
from enterprise_catalog.apps.catalog.tests import factories


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

    @override_settings(DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT=0)
    @mock.patch('enterprise_catalog.apps.api_client.discovery_cache.DiscoveryApiClient')
    def test_2U_exec_ed_content_inclusion_logic(self, mock_client):
        """
        Test that we exclude 2u exec ed courses from the create content metadata task unless the query provided allows
        for it
        """
        exec_ed_2u_course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+testX'),
            ('key', 'edX+testX'),
            ('title', 'test course'),
            ('course_type', 'executive-education-2u'),
        ])
        exec_ed_2u_course_run_metadata = OrderedDict([
            ('aggregation_key', 'courserun:TheEconomist+CAB'),
            ('key', 'course-v1:edX+testX'),
            ('title', 'test course run'),
            ('content_type', 'courserun'),
            ('seat_types', ['unpaid-executive-education']),
        ])
        edx_course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+testX2'),
            ('key', 'edX+testX2'),
            ('title', 'ayylmao'),
            ('course_type', 'professional'),
        ])
        mock_client.return_value.get_metadata_by_query.return_value = [
            exec_ed_2u_course_metadata,
            exec_ed_2u_course_run_metadata,
            edx_course_metadata,
        ]
        catalog = factories.EnterpriseCatalogFactory()
        self.assertEqual(ContentMetadata.objects.count(), 0)
        update_contentmetadata_from_discovery(catalog.catalog_query)
        mock_client.assert_called_once()
        self.assertEqual(ContentMetadata.objects.count(), 1)

        catalog.catalog_query.include_exec_ed_2u_courses = True
        catalog.catalog_query.save()
        update_contentmetadata_from_discovery(catalog.catalog_query)
        self.assertEqual(ContentMetadata.objects.count(), 3)

    @override_settings(DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT=0)
    @mock.patch('enterprise_catalog.apps.api_client.discovery_cache.DiscoveryApiClient')
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
        mock_client.return_value.get_metadata_by_query.return_value = [
            edx_course_metadata,
            twou_course_metadata,
            emeritus_course_metadata,
        ]
        catalog = factories.EnterpriseCatalogFactory()
        self.assertEqual(ContentMetadata.objects.count(), 0)
        update_contentmetadata_from_discovery(catalog.catalog_query)
        mock_client.assert_called_once()
        self.assertEqual(ContentMetadata.objects.count(), 2)

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

    @contextmanager
    def _mock_enterprise_customer_cache(
        self,
        mock_enterprise_customer_return_value,
        mock_customer_agreement_return_value,
        mock_coupon_overview_return_value,
    ):
        """
        Helper to mock out all API client calls that would normally occur
        when ``EnterpriseCatalog.enterprise_customer`` is accessed.
        """
        path = 'enterprise_catalog.apps.api_client.enterprise_cache.'
        with mock.patch(path + 'EnterpriseApiClient') as mock_enterprise_api_client, \
                mock.patch(path + 'LicenseManagerApiClient') as mock_license_manager_client, \
                mock.patch(path + 'EcommerceApiClient') as mock_ecommerce_client:
            mock_enterprise_api_client.return_value.get_enterprise_customer.return_value = \
                mock_enterprise_customer_return_value
            mock_ecommerce_client.return_value.get_coupons_overview.return_value = \
                mock_coupon_overview_return_value
            mock_license_manager_client.return_value.get_customer_agreement.return_value = \
                mock_customer_agreement_return_value
            yield

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
            content_metadata = factories.ContentMetadataFactory(
                content_key=content_key,
                content_type=COURSE,
            )
            enterprise_catalog.catalog_query.contentmetadata_set.add(*[content_metadata])

            mock_enterprise_customer_return_value = {
                'slug': enterprise_slug,
                'enable_learner_portal': True,
            }
            mock_customer_agreement_return_value = {
                'subscriptions': [{'enterprise_catalog_uuid': enterprise_catalog.uuid}],
            } if is_course_in_subscriptions_catalog else None
            mock_coupon_overview_return_value = [
                {'enterprise_catalog_uuid': enterprise_catalog.uuid},
            ] if is_course_in_coupons_catalog else []

            with self._mock_enterprise_customer_cache(
                mock_enterprise_customer_return_value,
                mock_customer_agreement_return_value,
                mock_coupon_overview_return_value,
            ):
                content_enrollment_url = enterprise_catalog.get_content_enrollment_url(content_metadata)

            if should_direct_to_lp:
                assert settings.ENTERPRISE_LEARNER_PORTAL_BASE_URL in content_enrollment_url
            else:
                assert settings.LMS_BASE_URL in content_enrollment_url

    def test_enrollment_url_exec_ed(self):
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
        enterprise_catalog.catalog_query.include_exec_ed_2u_courses = True
        actual_enrollment_url = enterprise_catalog.get_content_enrollment_url(content_metadata)
        assert 'happy-little-sku' in actual_enrollment_url

    @ddt.data(
        {'content_type': COURSE, 'course_type': EXEC_ED_2U_COURSE_TYPE, 'course_mode': 'honor',
         'sku': None, 'query_includes_ee_courses': True},
        {'content_type': COURSE, 'course_type': EXEC_ED_2U_COURSE_TYPE, 'course_mode': 'honor',
         'sku': '123456', 'query_includes_ee_courses': True},
        {'content_type': COURSE, 'course_type': EXEC_ED_2U_COURSE_TYPE, 'course_mode': EXEC_ED_2U_ENTITLEMENT_MODE,
         'sku': None, 'query_includes_ee_courses': True},
        {'content_type': COURSE, 'course_type': EXEC_ED_2U_COURSE_TYPE, 'course_mode': EXEC_ED_2U_ENTITLEMENT_MODE,
         'sku': '123456', 'query_includes_ee_courses': False},
    )
    @ddt.unpack
    def test_enrollment_url_exec_ed_is_null(
        self, content_type, course_type, course_mode, sku, query_includes_ee_courses
    ):
        """
        Tests for all scenarios when a null value should be
        returned as the enrollment URL for exec ed 2U courses.
        The content_metadata object below is always an exec ed 2U course,
        because the content_type is always "course" and the course_type is always
        the exec ed 2U course type.
        """
        enterprise_catalog = factories.EnterpriseCatalogFactory()
        content_metadata = factories.ContentMetadataFactory(
            content_key='the-content-key',
            content_type=content_type
        )
        content_metadata.json_metadata['course_type'] = course_type
        if course_mode:
            content_metadata.json_metadata['entitlements'] = [{'mode': course_mode}]
        if sku:
            content_metadata.json_metadata['entitlements'][0]['sku'] = sku

        enterprise_catalog.catalog_query.contentmetadata_set.add(*[content_metadata])
        enterprise_catalog.catalog_query.include_exec_ed_2u_courses = query_includes_ee_courses
        self.assertIsNone(enterprise_catalog.get_content_enrollment_url(content_metadata))
