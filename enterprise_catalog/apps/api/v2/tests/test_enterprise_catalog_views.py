import uuid
from datetime import datetime, timedelta
from unittest import mock

import ddt
import pytest
import pytz
from rest_framework import status

from enterprise_catalog.apps.api.base.tests.enterprise_catalog_views import (
    BaseEnterpriseCatalogViewSetTests,
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
class EnterpriseCatalogContainsContentItemsTests(BaseEnterpriseCatalogViewSetTests):
    """
    Tests for the EnterpriseCatalogViewSetV2, which is permissive of restricted course/run metadata.
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
        other_customer_catalog = EnterpriseCatalogFactory(enterprise_uuid=uuid.uuid4())

        base_url = self._get_contains_content_base_url(other_customer_catalog.uuid)
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
        content_key = 'fake-key+101x'
        relevant_content = ContentMetadataFactory(content_key=content_key)
        self.add_metadata_to_catalog(self.enterprise_catalog, [relevant_content])

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
            parent_content_key=restricted_course.content_key,
            content_type=COURSE_RUN,
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
        Tests that a catalog is considered to contain a restricted run,
        and that a different catalog that does *not* allow the restricted run
        is not considered to contain it.
        """
        other_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        content_one, _, restricted_run = self._create_restricted_course_and_run(other_catalog)

        self.add_metadata_to_catalog(self.enterprise_catalog, [content_one])
        self.add_metadata_to_catalog(other_catalog, [content_one])

        url = self._get_contains_content_base_url(other_catalog.uuid) + \
            f'?course_run_ids={restricted_run.content_key}'

        response = self.client.get(url)
        response_payload = response.json()

        self.assertTrue(response_payload.get('contains_content_items'))

        # self.enterprise_catalog does not contain the restricted run.
        url = self._get_contains_content_base_url(self.enterprise_catalog) + \
            f'?course_run_ids={restricted_run.content_key}'

        response = self.client.get(url)
        response_payload = response.json()

        self.assertFalse(response_payload.get('contains_content_items'))
