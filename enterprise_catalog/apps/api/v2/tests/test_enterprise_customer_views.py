import uuid
from datetime import datetime, timedelta
from unittest import mock

import ddt
import pytest
import pytz
from rest_framework import status

from enterprise_catalog.apps.api.base.tests.enterprise_customer_views import (
    BaseEnterpriseCustomerViewSetTests,
)
from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    RESTRICTED_RUNS_ALLOWED_KEY,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
    EnterpriseCatalogFactory,
    RestrictedCourseMetadataFactory,
    RestrictedRunAllowedForRestrictedCourseFactory,
)
from enterprise_catalog.apps.catalog.utils import localized_utcnow


@ddt.ddt
class EnterpriseCustomerViewSetTests(BaseEnterpriseCustomerViewSetTests):
    """
    Tests for the EnterpriseCustomerViewSetV2, which is permissive of restricted course/run metadata.
    """
    VERSION = 'v2'

    def setUp(self):
        super().setUp()

        self.customer_details_patcher = mock.patch(
            'enterprise_catalog.apps.catalog.models.EnterpriseCustomerDetails'
        )
        self.mock_customer_details = self.customer_details_patcher.start()
        self.NOW = localized_utcnow()
        self.mock_customer_details.return_value.last_modified_date = self.NOW

        self.addCleanup(self.customer_details_patcher.stop)

    def test_contains_content_items_unauthorized_non_catalog_learner(self):
        """
        Verify the contains_content_items endpoint rejects users that are not catalog learners
        """
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        url = self._get_contains_content_base_url() + '?course_run_ids=fakeX'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_contains_content_items_unauthorized_incorrect_jwt_context(self):
        """
        Verify the contains_content_items endpoint rejects users that are catalog learners
        with an incorrect JWT context (i.e., enterprise uuid)
        """
        self.remove_role_assignments()
        base_url = self._get_contains_content_base_url(enterprise_uuid=uuid.uuid4())
        url = base_url + '?course_run_ids=fakeX'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_contains_content_items_implicit_access(self):
        """
        Verify the contains_content_items endpoint responds with 200 OK for
        user with implicit JWT access
        """
        self.remove_role_assignments()
        url = self._get_contains_content_base_url() + '?program_uuids=fakeX'
        self.assert_correct_contains_response(url, False)

    def test_contains_content_items_no_params(self):
        """
        Verify the contains_content_items endpoint errors if no parameters are provided
        """
        response = self.client.get(self._get_contains_content_base_url())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_contains_content_items_not_in_catalogs(self):
        """
        Verify the contains_content_items endpoint returns False if the content is not in any associated catalog
        """
        self.add_metadata_to_catalog(self.enterprise_catalog, [ContentMetadataFactory()])

        url = self._get_contains_content_base_url() + '?program_uuids=this-is-not-the-uuid-youre-looking-for'
        self.assert_correct_contains_response(url, False)

    def test_contains_content_items_in_catalogs(self):
        """
        Verify the contains_content_items endpoint returns True if the content is in any associated catalog
        """
        content_metadata = ContentMetadataFactory()
        self.add_metadata_to_catalog(self.enterprise_catalog, [content_metadata])

        # Create a second catalog that has the content we're looking for
        content_key = 'fake-key+101x'
        second_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        relevant_content = ContentMetadataFactory(content_key=content_key)
        self.add_metadata_to_catalog(second_catalog, [relevant_content])

        url = self._get_contains_content_base_url() + '?course_run_ids=' + content_key
        self.assert_correct_contains_response(url, True)

    def _create_restricted_course_and_run(self, catalog):
        """
        Helper to setup restricted course and run.
        """
        content_one = ContentMetadataFactory(content_key='org+key1', content_type=COURSE)
        restricted_course = RestrictedCourseMetadataFactory.create(
            content_key='org+key1',
            content_type=COURSE,
            unrestricted_parent=content_one,
            catalog_query=catalog.catalog_query,
            _json_metadata=content_one.json_metadata,
        )
        restricted_run = ContentMetadataFactory.create(
            content_key='course-v1:org+key1+restrictedrun',
            content_type=COURSE_RUN,
            parent_content_key=restricted_course.content_key,
        )
        restricted_course.restricted_run_allowed_for_restricted_course.set(
            [restricted_run], clear=True,
        )
        catalog.catalog_query.content_filter[RESTRICTED_RUNS_ALLOWED_KEY] = {
            content_one.content_key: [restricted_run.content_key],
        }
        catalog.catalog_query.save()
        return content_one, restricted_course, restricted_run

    def test_contains_catalog_key_restricted_runs_allowed(self):
        """
        Tests that a customer is considered to contain a restricted run.
        """
        catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        catalog_b = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)

        content_one, _, restricted_run = self._create_restricted_course_and_run(catalog)

        self.add_metadata_to_catalog(catalog, [content_one])
        # add the top-level course to catalog_b, too
        self.add_metadata_to_catalog(catalog, [content_one])

        url = self._get_contains_content_base_url() + \
            f'?course_run_ids={restricted_run.content_key}&get_catalogs_containing_specified_content_ids=true'

        response = self.client.get(url)
        response_payload = response.json()

        self.assertTrue(response_payload.get('contains_content_items'))
        # catalog_b doesn't contain the restricted run
        self.assertEqual(response_payload['catalog_list'], [str(catalog.uuid)])

    def test_contains_catalog_key_restricted_run_present_but_not_associated_with_catalog(self):
        """
        Tests that a customer is not considered to contain a restricted run if the
        run exists in the database but is not explicitly linked to the customer's catalog
        (and even if the parent course *is* linked to the catalog).
        """
        catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        another_customers_catalog = EnterpriseCatalogFactory(enterprise_uuid=str(uuid.uuid4()))

        content_one, _, restricted_run = self._create_restricted_course_and_run(another_customers_catalog)

        self.add_metadata_to_catalog(catalog, [content_one])

        url = self._get_contains_content_base_url() + \
            f'?course_run_ids={restricted_run.content_key}&get_catalogs_containing_specified_content_ids=true'

        response = self.client.get(url)
        response_payload = response.json()

        self.assertFalse(response_payload.get('contains_content_items'))
        self.assertEqual(response_payload['catalog_list'], [])

    def test_filter_content_items_restricted_runs_allowed(self):
        """
        Tests that restricted runs are filtered in/out.
        """
        catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        catalog_b = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)

        content_one, _, restricted_run = self._create_restricted_course_and_run(catalog)

        self.add_metadata_to_catalog(catalog, [content_one, restricted_run])

        # add only the top-level course to catalog B
        self.add_metadata_to_catalog(catalog_b, [content_one])

        url = self._get_filter_content_base_url()

        response = self.client.post(url, data={'content_keys': [restricted_run.content_key]})
        response_payload = response.json()

        self.assertEqual(response_payload['filtered_content_keys'], [restricted_run.content_key])

        # filtering against only catalog B will have no results
        response = self.client.post(
            url,
            data={
                'content_keys': [restricted_run.content_key, content_one.content_key],
                'catalog_uuids': [str(catalog_b.uuid)],
            },
        )
        response_payload = response.json()

        self.assertEqual(
            response_payload['filtered_content_keys'],
            [str(content_one.content_key)],
        )

    def test_get_content_metadata_restricted_runs(self):
        """
        Tests that we can retrieve restricted content metadata for a customer.
        """
        catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)

        content_one, _, restricted_run = self._create_restricted_course_and_run(catalog)

        self.add_metadata_to_catalog(catalog, [content_one])

        # Test that we can retrieve the course record
        url = self._get_content_metadata_base_url(self.enterprise_uuid, content_one.content_key)

        response_payload = self.client.get(url).json()
        self.assertEqual(response_payload['key'], content_one.content_key)
        self.assertEqual(response_payload['content_type'], COURSE)

        # Test that we can retrieve the restricted run by key
        url = self._get_content_metadata_base_url(self.enterprise_uuid, restricted_run.content_key)

        response_payload = self.client.get(url).json()
        # this will be a top-level course, with course_runs nested within it
        self.assertEqual(response_payload['key'], content_one.content_key)
        self.assertEqual(response_payload['content_type'], COURSE)

        # Test that we can retrieve the restricted run by uuid
        url = self._get_content_metadata_base_url(self.enterprise_uuid, restricted_run.content_uuid)

        response_payload = self.client.get(url).json()
        # this will be a top-level course, with course_runs nested within it
        self.assertEqual(response_payload['key'], content_one.content_key)
        self.assertEqual(response_payload['content_type'], COURSE)

    def test_get_content_metadata_restricted_runs_not_found(self):
        """
        Tests that when restricted runs are not explicitly linked to a customer's catalog,
        they cannot be retrieved.
        """
        catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        another_customers_catalog = EnterpriseCatalogFactory(enterprise_uuid=str(uuid.uuid4()))

        content_one, _, restricted_run = self._create_restricted_course_and_run(another_customers_catalog)

        self.add_metadata_to_catalog(catalog, [content_one])
        self.add_metadata_to_catalog(another_customers_catalog, [content_one])

        # Test that we can retrieve the course record
        url = self._get_content_metadata_base_url(self.enterprise_uuid, content_one.content_key)

        response_payload = self.client.get(url).json()
        self.assertEqual(response_payload['key'], content_one.content_key)
        self.assertEqual(response_payload['content_type'], COURSE)

        # Test that we cannot retrieve the restricted run record
        url = self._get_content_metadata_base_url(self.enterprise_uuid, restricted_run.content_key)

        response = self.client.get(url)

        self.assertEqual(status.HTTP_404_NOT_FOUND, response.status_code)
