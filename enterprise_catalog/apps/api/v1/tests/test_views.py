import copy
import json
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta
from unittest import mock
from urllib.parse import urljoin

import ddt
import pytz
from django.conf import settings
from django.contrib.auth.models import Group
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
    PROVISIONING_ADMINS_GROUP,
)
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
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
class EnterpriseCatalogDefaultCatalogResultsTests(APITestMixin):
    """
    Tests for the DefaultCatalogResultsView class
    """
    mock_algolia_hits = {'hits': [{
        'aggregation_key': 'course:MITx+18.01.2x',
        'key': 'MITx+18.01.2x',
        'language': 'English',
        'transcript_languages': ['English', 'Arabic'],
        'level_type': 'Intermediate',
        'content_type': 'course',
        'partners': [
            {'name': 'Massachusetts Institute of Technology',
             'logo_image_url': 'https://edx.org/image.png'}
        ],
        'programs': ['Professional Certificate'],
        'program_titles': ['Totally Awesome Program'],
        'short_description': 'description',
        'subjects': ['Math'],
        'skills': [{
            'name': 'Probability And Statistics',
            'description': 'description'
        }, {
            'name': 'Engineering Design Process',
            'description': 'description'
        }],
        'title': 'Calculus 1B: Integration',
        'marketing_url': 'edx.org/foo-bar',
        'first_enrollable_paid_seat_price': 100,
        'advertised_course_run': {
            'key': 'MITx/18.01.2x/3T2015',
            'pacing_type': 'instructor_paced',
            'start': '2015-09-08T00:00:00Z',
            'end': '2015-09-08T00:00:01Z',
            'upgrade_deadline': 32503680000.0,
        },
        'objectID': 'course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf8-catalog-query-uuids-0'
    },
        {
        'aggregation_key': 'course:MITx+19',
        'key': 'MITx+19',
        'language': 'English',
        'transcript_languages': ['English', 'Arabic'],
        'level_type': 'Intermediate',
        'objectID': 'course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf9-catalog-query-uuids-0'
    },
        {
        'aggregation_key': 'course:MITx+20',
        'language': 'English',
        'transcript_languages': ['English', 'Arabic'],
        'level_type': 'Intermediate',
        'objectID': 'course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf7-catalog-query-uuids-0'
    }
    ]}

    def setUp(self):
        super().setUp()
        self.set_up_staff_user()

    def _get_contains_content_base_url(self):
        """
        Helper to construct the base url for the contains_content_items endpoint
        """
        return reverse('api:v1:default-course-set')

    def test_facet_validation(self):
        """
        Tests that the view validates Algolia facets provided by query params
        """
        url = self._get_contains_content_base_url()
        invalid_facets = 'invalid_facet=wrong&enterprise_catalog_query_titles=ayylmao'
        response = self.client.get(f'{url}?{invalid_facets}')
        assert response.status_code == 400
        assert response.json() == {'Error': "invalid facet(s): ['invalid_facet'] provided."}

    @mock.patch('enterprise_catalog.apps.api.v1.views.default_catalog_results.get_initialized_algolia_client')
    def test_valid_facet_validation(self, mock_algolia_client):
        """
        Tests a successful request with facets.
        """
        mock_algolia_client.return_value.algolia_index.search.side_effect = [self.mock_algolia_hits, {'hits': []}]
        url = self._get_contains_content_base_url()
        facets = 'enterprise_catalog_query_titles=foo&content_type=course'
        response = self.client.get(f'{url}?{facets}')
        assert response.status_code == 200

    @mock.patch('enterprise_catalog.apps.api.v1.views.default_catalog_results.get_initialized_algolia_client')
    def test_default_catalog_results_view_works_with_one_and_many_course_types(self, mock_algolia_client):
        """
        Test that the default catalog results view rejects requests where the query param course_type is not a list
        """
        mock_algolia_client.return_value.algolia_index.search.side_effect = [self.mock_algolia_hits, {'hits': []}]
        url = self._get_contains_content_base_url()
        facets = 'enterprise_catalog_query_titles=foo&course_type=course'
        response = self.client.get(f'{url}?{facets}')
        assert response.status_code == 200

        facets = 'enterprise_catalog_query_titles=foo&course_type=course&course_type=notcourse'
        response = self.client.get(f'{url}?{facets}')
        assert response.status_code == 200


@ddt.ddt
class EnterpriseCatalogCRUDViewSetTests(APITestMixin):
    """
    Tests for the EnterpriseCatalogCRUDViewSet
    """

    def setUp(self):
        super().setUp()
        self.set_up_staff()
        self.enterprise_catalog = EnterpriseCatalogFactory(
            enterprise_uuid=self.enterprise_uuid,
            enterprise_name=self.enterprise_name,
        )
        self.new_catalog_uuid = uuid.uuid4()
        self.new_catalog_data = {
            'uuid': self.new_catalog_uuid,
            'title': 'Test Title',
            'enterprise_customer': self.enterprise_uuid,
            'enterprise_customer_name': self.enterprise_name,
            'enabled_course_modes': ['verified'],
            'publish_audit_enrollment_urls': True,
            'content_filter': {'content_type': 'course'},
        }
        self.allowed_group = Group.objects.create(name=PROVISIONING_ADMINS_GROUP)

    def _assert_correct_new_catalog_data(self, catalog_uuid):
        """
        Helper for verifying the data for a created/updated catalog
        """
        new_enterprise_catalog = EnterpriseCatalog.objects.get(uuid=catalog_uuid)
        self.assertEqual(new_enterprise_catalog.title, self.new_catalog_data['title'])
        self.assertEqual(new_enterprise_catalog.enabled_course_modes, ['verified'])
        self.assertEqual(
            new_enterprise_catalog.publish_audit_enrollment_urls,
            self.new_catalog_data['publish_audit_enrollment_urls'],
        )
        self.assertEqual(
            new_enterprise_catalog.catalog_query.content_filter,
            OrderedDict([('content_type', 'course')]),
        )

    def test_detail_unauthorized_catalog_learner(self):
        """
        Verify the viewset rejects catalog learners for the detail route
        """
        self.set_up_catalog_learner()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_unauthorized_catalog_learner(self):
        """
        Verify the viewset rejects patch for catalog learners
        """
        self.set_up_catalog_learner()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_put_unauthorized_catalog_learner(self):
        """
        Verify the viewset rejects put for catalog learners
        """
        self.set_up_catalog_learner()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.put(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_unauthorized_catalog_learner(self):
        """
        Verify the viewset rejects post for catalog learners
        """
        self.set_up_catalog_learner()
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.post(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @ddt.data(
        (False),
        (True),
    )
    def test_detail(self, is_implicit_check):
        """
        Verify the viewset returns the details for a single enterprise catalog
        """
        if is_implicit_check:
            self.remove_role_assignments()

        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(uuid.UUID(data['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(data['title'], self.enterprise_catalog.title)
        self.assertEqual(uuid.UUID(data['enterprise_customer']), self.enterprise_catalog.enterprise_uuid)

    def test_detail_provisioning_admin(self):
        """
        Verify the viewset returns the details if requesting user is a PA
        """
        self.set_up_staff_user()
        self.remove_role_assignments()
        self.set_up_invalid_jwt_role()
        self.user.groups.add(self.allowed_group)
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(uuid.UUID(data['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(data['title'], self.enterprise_catalog.title)
        self.assertEqual(uuid.UUID(data['enterprise_customer']), self.enterprise_catalog.enterprise_uuid)

    def test_detail_unauthorized_non_catalog_admin(self):
        """
        Verify the viewset rejects users that are not catalog admins for the detail route
        """
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_detail_unauthorized_incorrect_jwt_context(self):
        """
        Verify the viewset rejects users that are catalog admins with an invalid
        context (i.e., enterprise uuid) for the detail route.
        """
        enterprise_catalog = EnterpriseCatalogFactory()
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @ddt.data(
        (False),
        (True),
    )
    def test_patch(self, is_implicit_check):
        """
        Verify the viewset handles patching an enterprise catalog
        """
        if is_implicit_check:
            self.remove_role_assignments()

        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Verify that only the data we specifically patched changed
        self.assertEqual(response.data['title'], patch_data['title'])
        patched_catalog = EnterpriseCatalog.objects.get(uuid=self.enterprise_catalog.uuid)
        self.assertEqual(patched_catalog.catalog_query, self.enterprise_catalog.catalog_query)
        self.assertEqual(patched_catalog.enterprise_uuid, self.enterprise_catalog.enterprise_uuid)
        self.assertEqual(patched_catalog.enabled_course_modes, self.enterprise_catalog.enabled_course_modes)
        self.assertEqual(
            patched_catalog.publish_audit_enrollment_urls,
            self.enterprise_catalog.publish_audit_enrollment_urls,
        )

    def test_patch_provisioning_admins(self):
        """
        Verify the viewset handles patching an enterprise catalog
        """
        self.set_up_staff_user()
        self.remove_role_assignments()
        self.set_up_invalid_jwt_role()
        self.user.groups.add(self.allowed_group)
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Verify that only the data we specifically patched changed
        self.assertEqual(response.data['title'], patch_data['title'])
        patched_catalog = EnterpriseCatalog.objects.get(uuid=self.enterprise_catalog.uuid)
        self.assertEqual(patched_catalog.catalog_query, self.enterprise_catalog.catalog_query)
        self.assertEqual(patched_catalog.enterprise_uuid, self.enterprise_catalog.enterprise_uuid)
        self.assertEqual(patched_catalog.enabled_course_modes, self.enterprise_catalog.enabled_course_modes)
        self.assertEqual(
            patched_catalog.publish_audit_enrollment_urls,
            self.enterprise_catalog.publish_audit_enrollment_urls,
        )

    def test_patch_unauthorized_non_catalog_admin(self):
        """
        Verify the viewset rejects patch for users that are not catalog admins
        """
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_unauthorized_incorrect_jwt_context(self):
        """
        Verify the viewset rejects patch for users that are catalog admins with an invalid
        context (i.e., enterprise uuid)
        """
        enterprise_catalog = EnterpriseCatalogFactory()
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': enterprise_catalog.uuid})
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @ddt.data(
        (False),
        (True),
    )
    def test_put(self, is_implicit_check):
        """
        Verify the viewset handles replacing an enterprise catalog
        """
        if is_implicit_check:
            self.remove_role_assignments()

        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.put(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self._assert_correct_new_catalog_data(self.enterprise_catalog.uuid)  # The UUID should not have changed

    def test_put_provisioning_admins(self):
        """
        Verify the viewset allows access to PAs
        """
        self.set_up_staff_user()
        self.remove_role_assignments()
        self.set_up_invalid_jwt_role()
        self.user.groups.add(self.allowed_group)
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.put(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self._assert_correct_new_catalog_data(self.enterprise_catalog.uuid)  # The UUID should not have changed

    def test_put_unauthorized_non_catalog_admin(self):
        """
        Verify the viewset rejects put for users that are not catalog admins
        """
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.put(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_put_unauthorized_incorrect_jwt_context(self):
        """
        Verify the viewset rejects put for users that are catalog admins with an invalid
        context (i.e., enterprise uuid)
        """
        enterprise_catalog = EnterpriseCatalogFactory()
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': enterprise_catalog.uuid})
        response = self.client.put(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_put_integrity_error_regression(self):
        """
        Verify updating an enterprise catalog with a
        catalog query that has a content filter identical to an existing
        one causes an integrity error.

        The expected error is in serializers.py find_and_modify_catalog_query
        """
        catalog_query_1 = CatalogQueryFactory(
            title='catalog_query_1',
            content_filter={"a": "b"},
        )
        EnterpriseCatalogFactory(
            enterprise_uuid=self.enterprise_uuid,
            enterprise_name=self.enterprise_name,
            catalog_query=catalog_query_1,
        )
        catalog_query_2 = CatalogQueryFactory(
            title='catalog_query_2',
            content_filter={"c": "d"},
        )
        enterprise_catalog_2 = EnterpriseCatalogFactory(
            enterprise_uuid=self.enterprise_uuid,
            enterprise_name=self.enterprise_name,
            catalog_query=catalog_query_2,
        )
        put_data = {
            'uuid': enterprise_catalog_2.uuid,
            'title': enterprise_catalog_2.title,
            'enterprise_customer': enterprise_catalog_2.enterprise_uuid,
            'enterprise_customer_name': enterprise_catalog_2.enterprise_name,
            'enabled_course_modes': enterprise_catalog_2.enabled_course_modes,
            'publish_audit_enrollment_urls': enterprise_catalog_2.publish_audit_enrollment_urls,
            'content_filter': {"a": "b"},
        }

        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': enterprise_catalog_2.uuid})
        response = self.client.put(url, data=put_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @ddt.data(
        (False),
        (True),
    )
    def test_post(self, is_implicit_check):
        """
        Verify the viewset handles creating an enterprise catalog
        """
        if is_implicit_check:
            self.remove_role_assignments()

        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.post(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self._assert_correct_new_catalog_data(self.new_catalog_uuid)

    def test_post_provisioning_admins(self):
        """
        Verify the viewset handles creating an enterprise catalog
        """
        self.set_up_staff_user()
        self.remove_role_assignments()
        self.set_up_invalid_jwt_role()
        self.user.groups.add(self.allowed_group)
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.post(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self._assert_correct_new_catalog_data(self.new_catalog_uuid)

    def test_post_integrity_error(self):
        """
        Verify the viewset raises error when creating a duplicate enterprise catalog
        """
        url = reverse('api:v1:enterprise-catalog-list')
        self.client.post(url, self.new_catalog_data)
        with self.assertRaises(IntegrityError):
            self.client.post(url, self.new_catalog_data)
        # Note: we're hitting the endpoint twice here, but this task should
        # only be run once, as we should error from an integrity error the
        # second time through

    def test_post_unauthorized_non_catalog_admin(self):
        """
        Verify the viewset rejects post for users that are not catalog admins
        """
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.post(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_unauthorized_incorrect_jwt_context(self):
        """
        Verify the viewset rejects post for users that are catalog admins with an invalid
        context (i.e., enterprise uuid)
        """
        catalog_data = {
            'uuid': self.new_catalog_uuid,
            'title': 'Test Title',
            'enterprise_customer': uuid.uuid4(),
            'enabled_course_modes': '["verified"]',
            'publish_audit_enrollment_urls': True,
            'content_filter': '{"content_type":"course"}',
        }
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.post(url, catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@ddt.ddt
class EnterpriseCatalogCRUDViewSetListTests(APITestMixin):
    """
    Tests for the EnterpriseCatalogCRUDViewSet list endpoint.
    """

    def setUp(self):
        super().setUp()
        self.set_up_staff_user()
        self.enterprise_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        self.allowed_group = Group.objects.create(name=PROVISIONING_ADMINS_GROUP)

    def test_list_for_superusers(self):
        """
        Verify the viewset returns a list of all enterprise catalogs for superusers
        """
        self.set_up_superuser()
        url = reverse('api:v1:enterprise-catalog-list')
        second_enterprise_catalog = EnterpriseCatalogFactory()
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        results = response.data['results']
        self.assertEqual(uuid.UUID(results[0]['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(uuid.UUID(results[1]['uuid']), second_enterprise_catalog.uuid)

    def test_list_for_provisioning_admins(self):
        """
        Verify the viewset returns a list of all enterprise catalogs for provisioning admins
        """
        self.set_up_staff_user()
        self.remove_role_assignments()
        self.set_up_invalid_jwt_role()
        self.user.groups.add(self.allowed_group)
        url = reverse('api:v1:enterprise-catalog-list')
        second_enterprise_catalog = EnterpriseCatalogFactory()
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        results = response.data['results']
        self.assertEqual(
            uuid.UUID(results[0]['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(
            uuid.UUID(results[1]['uuid']), second_enterprise_catalog.uuid)

    def test_empty_list_for_non_catalog_admin(self):
        """
        Verify the viewset returns an empty list for users that are staff but not catalog admins.
        """
        self.set_up_invalid_jwt_role()
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    @ddt.data(
        False,
        True,
    )
    def test_one_catalog_for_catalog_admins(self, is_role_assigned_via_jwt):
        """
        Verify the viewset returns a single catalog (when multiple exist) for catalog admins of a certain enterprise.
        """
        if is_role_assigned_via_jwt:
            self.assign_catalog_admin_jwt_role()
        else:
            self.assign_catalog_admin_feature_role()

        # create an additional catalog from a different enterprise,
        # and make sure we don't see it in the response results.
        EnterpriseCatalogFactory(enterprise_uuid=uuid.uuid4())

        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        results = response.data['results']
        self.assertEqual(uuid.UUID(results[0]['uuid']), self.enterprise_catalog.uuid)

    @ddt.data(
        False,
        True,
    )
    def test_multiple_catalogs_for_catalog_admins(self, is_role_assigned_via_jwt):
        """
        Verify the viewset returns multiple catalogs for catalog admins of two different enterprises.
        """
        second_enterprise_catalog = EnterpriseCatalogFactory(enterprise_uuid=uuid.uuid4())

        if is_role_assigned_via_jwt:
            self.assign_catalog_admin_jwt_role(
                self.enterprise_uuid,
                second_enterprise_catalog.enterprise_uuid,
            )
        else:
            self.assign_catalog_admin_feature_role(enterprise_uuids=[
                self.enterprise_uuid,
                second_enterprise_catalog.enterprise_uuid,
            ])

        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        results = response.data['results']
        self.assertEqual(uuid.UUID(results[0]['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(uuid.UUID(results[1]['uuid']), second_enterprise_catalog.uuid)

    @ddt.data(
        False,
        True,
    )
    def test_every_catalog_for_catalog_admins(self, is_role_assigned_via_jwt):
        """
        Verify the viewset returns catalogs of all enterprises for admins with wildcard permission.
        """
        if is_role_assigned_via_jwt:
            self.assign_catalog_admin_jwt_role('*')
        else:
            # This will cause a feature role assignment to be created with a null enterprise UUID,
            # which is interpretted as having access to catalogs of ANY enterprise.
            self.assign_catalog_admin_feature_role(enterprise_uuids=[None])

        catalog_b = EnterpriseCatalogFactory(enterprise_uuid=uuid.uuid4())
        catalog_c = EnterpriseCatalogFactory(enterprise_uuid=uuid.uuid4())

        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)
        results = response.data['results']
        self.assertEqual(uuid.UUID(results[0]['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(uuid.UUID(results[1]['uuid']), catalog_b.uuid)
        self.assertEqual(uuid.UUID(results[2]['uuid']), catalog_c.uuid)

    @ddt.data(
        False,
        True,
    )
    def test_catalog_list_for_catalog_admins_with_enterprise_param(self, is_role_assigned_via_jwt):
        """
        Verify the viewset returns a single catalog (when multiple exist) with GET params will provided.
        """
        if is_role_assigned_via_jwt:
            self.assign_catalog_admin_jwt_role()
        else:
            self.assign_catalog_admin_feature_role()

        # create an additional catalog from a different enterprise,
        # make it so that the filter of GET params is applied and sure we don't see it in the response results.
        EnterpriseCatalogFactory(enterprise_uuid=uuid.uuid4())

        url = urljoin(reverse('api:v1:enterprise-catalog-list'), f'?enterprise_customer={str(self.enterprise_uuid)}')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        catalog_list = response.json()['results']
        self.assertEqual(len(catalog_list), 1)
        self.assertEqual(uuid.UUID(catalog_list[0]['uuid']), self.enterprise_catalog.uuid)

    def test_list_unauthorized_catalog_learner(self):
        """
        Verify the viewset rejects list for catalog learners
        """
        self.set_up_catalog_learner()
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class EnterpriseCatalogCsvDataViewTests(APITestMixin):
    """
    Tests for the CatalogCsvDataView view.
    """
    mock_algolia_hits = {'hits': [{
        'aggregation_key': 'course:MITx+18.01.2x',
        'key': 'MITx+18.01.2x',
        'language': 'English',
        'transcript_languages': ['English', 'Arabic'],
        'level_type': 'Intermediate',
        'content_type': 'course',
        'enterprise_catalog_query_titles': ['A la carte', 'Business', 'DemoX'],
        'partners': [
            {'name': 'Massachusetts Institute of Technology',
             'logo_image_url': 'https://edx.org/image.png'}
        ],
        'programs': ['Professional Certificate'],
        'program_titles': ['Totally Awesome Program'],
        'short_description': 'description',
        'subjects': ['Math'],
        'skills': [{
            'name': 'Probability And Statistics',
            'description': 'description'
        }, {
            'name': 'Engineering Design Process',
            'description': 'description'
        }],
        'title': 'Calculus 1B: Integration',
        'marketing_url': 'edx.org/foo-bar',
        'first_enrollable_paid_seat_price': 100,
        'advertised_course_run': {
            'key': 'MITx/18.01.2x/3T2015',
            'pacing_type': 'instructor_paced',
            'start': '2015-09-08T00:00:00Z',
            'end': '2015-09-08T00:00:01Z',
            'upgrade_deadline': 32503680000.0,
            'max_effort': 10,
            'min_effort': 1,
            'weeks_to_complete': 1,
        },
        'outcome': '<p>learn</p>',
        'prerequisites_raw': '<p>interest</p>',
        'objectID': 'course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf8-catalog-query-uuids-0'
    },
        {
        'aggregation_key': 'course:MITx+19',
        'key': 'MITx+19',
        'language': 'English',
        'transcript_languages': ['English', 'Arabic'],
        'level_type': 'Intermediate',
        'objectID': 'course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf9-catalog-query-uuids-0'
    },
        {
        'aggregation_key': 'course:MITx+20',
        'language': 'English',
        'transcript_languages': ['English', 'Arabic'],
        'level_type': 'Intermediate',
        'objectID': 'course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf7-catalog-query-uuids-0'
    }
    ]}

    expected_result_data = (
        "Title,Partner Name,Start,End,Verified Upgrade Deadline,Program Type,Program Name,Pacing,"
        "Level,Price,Language,Subtitles,URL,Short Description,Subjects,Key,Short Key,Skills,Min Effort,"
        "Max Effort,Length,What You’ll Learn,Pre-requisites,Associated Catalogs\r\nCalculus 1B: "
        "Integration,Massachusetts Institute of Technology,2015-09-08,"
        "2015-09-08,3000-01-01,Professional Certificate,Totally "
        'Awesome Program,instructor_paced,Intermediate,100,English,"English, Arabic",edx.org/foo-bar,description,'
        'Math,MITx/18.01.2x/3T2015,course:MITx+18.01.2x,"Probability And Statistics, '
        'Engineering Design Process",1,10,1,learn,interest,"A la carte, Business"\r\n'
    )

    def setUp(self):
        super().setUp()
        self.set_up_staff_user()

    def _get_contains_content_base_url(self):
        """
        Helper to construct the base url for the contains_content_items endpoint
        """
        return reverse('api:v1:catalog-csv-data')

    def _get_mock_algolia_hits_with_missing_values(self):
        mock_hits_missing_values = copy.deepcopy(self.mock_algolia_hits)
        mock_hits_missing_values['hits'][0]['advertised_course_run'].pop('upgrade_deadline')
        mock_hits_missing_values['hits'][0].pop('marketing_url')
        mock_hits_missing_values['hits'][0].pop('first_enrollable_paid_seat_price')
        mock_hits_missing_values['hits'][0]['advertised_course_run']['end'] = None
        return mock_hits_missing_values

    def test_facet_validation(self):
        """
        Tests that the view validates Algolia facets provided by query params
        """
        url = self._get_contains_content_base_url()
        invalid_facets = 'invalid_facet=wrong'
        response = self.client.get(f'{url}?{invalid_facets}')
        assert response.status_code == 400
        assert response.data == "Error: invalid facet(s): ['invalid_facet'] provided."

    @mock.patch('enterprise_catalog.apps.api.v1.views.catalog_csv_data.get_initialized_algolia_client')
    def test_valid_facet_validation(self, mock_algolia_client):
        """
        Tests a successful request with facets.
        """
        mock_algolia_client.return_value.algolia_index.search.side_effect = [self.mock_algolia_hits, {'hits': []}]
        url = self._get_contains_content_base_url()
        facets = 'language=English'
        response = self.client.get(f'{url}?{facets}')
        assert response.status_code == 200

        expected_response = {
            'csv_data': self.expected_result_data
        }
        assert response.data == expected_response

    @mock.patch('enterprise_catalog.apps.api.v1.views.catalog_csv_data.get_initialized_algolia_client')
    def test_csv_row_construction_handles_missing_values(self, mock_algolia_client):
        """
        Tests that the view properly handles situations where data is missing from the Algolia hit.
        """
        mock_side_effects = [self._get_mock_algolia_hits_with_missing_values(), {'hits': []}]
        mock_algolia_client.return_value.algolia_index.search.side_effect = mock_side_effects
        url = self._get_contains_content_base_url()
        facets = 'language=English'
        response = self.client.get(f'{url}?{facets}')
        assert response.status_code == 200
        excpected_csv_data = (
            "Title,Partner Name,Start,End,Verified Upgrade Deadline,Program Type,Program Name,"
            "Pacing,Level,Price,Language,Subtitles,URL,Short Description,Subjects,Key,Short Key,Skills,"
            "Min Effort,Max Effort,Length,What You’ll Learn,Pre-requisites,Associated Catalogs\r\n"
            "Calculus 1B: Integration,Massachusetts Institute of Technology,2015-09-08,"
            ",,Professional Certificate,Totally Awesome "
            'Program,instructor_paced,Intermediate,,English,"English, Arabic",,description,'
            'Math,MITx/18.01.2x/3T2015,course:MITx+18.01.2x,"Probability And Statistics, '
            'Engineering Design Process",1,10,1,learn,interest,"A la carte, Business"\r\n'
        )
        expected_response = {
            'csv_data': excpected_csv_data
        }
        assert response.data == expected_response


class EnterpriseCatalogWorkbookViewTests(APITestMixin):
    """
    Tests for the CatalogWorkbookView view.
    """
    mock_algolia_hits = {
        "hits": [
            {
                "aggregation_key": "course:MITx+18.01.2x",
                "key": "MITx+18.01.2x",
                "language": "English",
                "level_type": "Intermediate",
                "content_type": "course",
                "enterprise_catalog_query_titles": ["A la carte", "Business", "DemoX"],
                "partners": [
                    {
                        "name": "Massachusetts Institute of Technology",
                        "logo_image_url": "https://edx.org/image.png"
                    }
                ],
                "programs": [
                    "Professional Certificate"
                ],
                "program_titles": [
                    "Totally Awesome Program"
                ],
                "short_description": "description",
                "subjects": [
                    "Math"
                ],
                "skills": [
                    {
                        "name": "Probability And Statistics",
                        "description": "description"
                    },
                    {
                        "name": "Engineering Design Process",
                        "description": "description"
                    }
                ],
                "title": "Calculus 1B: Integration",
                "marketing_url": "edx.org/foo-bar",
                "first_enrollable_paid_seat_price": 100,
                "advertised_course_run": {
                    "key": "MITx/18.01.2x/3T2015",
                    "pacing_type": "instructor_paced",
                    "start": "2015-09-08T00:00:00Z",
                    "end": "2015-09-08T00:00:01Z",
                    "upgrade_deadline": 32503680000.0,
                    "max_effort": 10,
                    "min_effort": 1,
                    "weeks_to_complete": 1
                },
                "course_runs": [
                    {
                        "key": "MITx/18.01.2x/3T2015",
                        "pacing_type": "instructor_paced",
                        "start": "2015-09-08T00:00:00Z",
                        "end": "2015-09-08T00:00:01Z",
                        "upgrade_deadline": 32503680000.0,
                        "max_effort": 10,
                        "min_effort": 1,
                        "weeks_to_complete": 1
                    }
                ],
                "outcome": "<p>learn</p>",
                "prerequisites_raw": "<p>interest</p>",
                "objectID": "course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf8-catalog-query-uuids-0"
            },
            {
                "aggregation_key": "course:OxfordX+PSF",
                "content_type": "course",
                "full_description": "<p><strong>Duration:</strong> 6 weeks (excluding orientation)</p>\n<p>",
                "key": "OxfordX+PSF",
                "language": "English",
                "level_type": "Introductory",
                "outcome": "<p>On completion of this programme",
                "partners": [
                    {
                        "name": "University of Oxford",
                        "logo_image_url": "https://prod-discovery.edx-cdn.org/organization/logos/2b6474eb5fac.png"
                    }
                ],
                "prerequisites_raw": "",
                "programs": [

                ],
                "program_titles": [

                ],
                "short_description": "<p>Respond to unique industry challenges",
                "subjects": [
                    "Business & Management"
                ],
                "skills": [
                    {
                        "name": "Finance",
                        "description": "",
                        "category": {
                            "name": "Finance"
                        },
                        "subcategory": {
                            "name": "Financial Accounting",
                            "category": {
                                "name": "Finance"
                            }
                        }
                    }
                ],
                "title": "Oxford Leading Professional Service Firms Programme",
                "advertised_course_run": {
                    "key": "course-v1:OxfordX+PSF+2T2022",
                    "pacing_type": "instructor_paced",
                    "availability": "Current",
                    "start": "2022-06-15T00:00:00Z",
                    "end": "2022-07-24T23:59:59Z",
                    "min_effort": 7,
                    "max_effort": 10,
                    "weeks_to_complete": 6,
                    "upgrade_deadline": 32503680000.0
                },
                "course_runs": [

                ],
                "marketing_url": "https://www.edx.org/course/oxford-leadinaffiliate_partner",
                "course_type": "executive-education-2u",
                "entitlements": [
                    {
                        "mode": "paid-executive-education",
                        "price": "2843.00",
                        "currency": "USD",
                        "sku": "67A1CAE",
                        "expires": "None"
                    }
                ],
                "additional_metadata": {
                    "external_identifier": "242576ed-7443-4c3c-a8a8-d624862a1951",
                    "external_url": "https://oxford-onlineprogrammes.getsmarter.com/prional-service-firms-programme/",
                    "lead_capture_form_url": "https://www.getsmarter.com/presentat1951",
                    "facts": [
                        {
                            "heading": "Top trends",
                            "blurb": "<p>Emerging technologies are one of the top trends impacting PSFs"
                        }
                    ],
                    "certificate_info": {
                        "heading": "About the certificate",
                        "blurb": "<p>Learn how to achieve"
                    },
                    "organic_url": "https://www.getsmarter.com/products/oxford-leacel&utm_campaign=edx_OXF-PSF",
                    "start_date": "2023-03-01T00:00:00Z",
                    "end_date": "2023-04-09T23:59:59Z",
                    "registration_deadline": "2023-02-21T23:59:59Z",
                    "variant_id": "065fcd63-55a9-43e3-b9f9-ca3ba3129ebf",
                    "course_term_override": "",
                    "product_status": "published",
                    "product_meta": "None"
                },
                "objectID": "course-d3dc62b5-531d-40a7-b44f-1acf687b1148-catalog-query-uuids-0",
                "_highlightResult": {
                    "additional_information": {
                        "value": "",
                        "matchLevel": "none",
                        "matchedWords": [

                        ]
                    }
                },
                "skill_names": [
                    {
                        "value": "People Management",
                        "matchLevel": "none",
                        "matchedWords": [

                        ]
                    }
                ]
            },
            {
                "aggregation_key": "course:MITx+19",
                "key": "MITx+19",
                "language": "English",
                "level_type": "Intermediate",
                "objectID": "course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf9-catalog-query-uuids-0"
            },
            {
                "aggregation_key": "course:MITx+20",
                "language": "English",
                "level_type": "Intermediate",
                "objectID": "course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf7-catalog-query-uuids-0"
            },
            {
                "aggregation_key": "course:MITx+18.01.2x",
                "course_keys": ['MITx+18.01.2x'],
                "content_type": "program",
                "enterprise_catalog_query_titles": ["A la carte", "Business", "DemoX"],
                "partners": [
                    {
                        "name": "Harvard University",
                        "logo_image_url": "https://edx.org/image.png"
                    }
                ],
                "title": "Calculus 1B: Integration",
                "subtitle": "this is a subtitle",
                "program_type": "Professional Certificate"
            }
        ]
    }

    def setUp(self):
        super().setUp()
        self.set_up_staff_user()

    def _get_contains_content_base_url(self):
        """
        Helper to construct the base url for the contains_content_items endpoint
        """
        return reverse('api:v1:catalog-workbook')

    @mock.patch('enterprise_catalog.apps.api.v1.views.catalog_workbook.get_initialized_algolia_client')
    def test_empty_results_error(self, mock_algolia_client):
        """
        Tests when algolia returns no hits.
        """
        mock_algolia_client.return_value.algolia_index.search.side_effect = [{'hits': []}]
        url = self._get_contains_content_base_url()
        facets = 'language=English'
        response = self.client.get(f'{url}?{facets}')
        assert response.status_code == 400

    @mock.patch('enterprise_catalog.apps.api.v1.views.catalog_workbook.get_initialized_algolia_client')
    def test_success(self, mock_algolia_client):
        """
        Tests basic, successful output.
        """
        mock_algolia_client.return_value.algolia_index.search.side_effect = [self.mock_algolia_hits, {'hits': []}]
        url = self._get_contains_content_base_url()
        facets = 'language=English'
        response = self.client.get(f'{url}?{facets}')
        assert response.status_code == 200


class EnterpriseCatalogContainsContentItemsTests(APITestMixin):
    """
    Tests on the contains_content_items on enterprise catalogs endpoint
    """

    def setUp(self):
        super().setUp()
        # Set up catalog.has_learner_access permissions
        self.set_up_catalog_learner()
        self.enterprise_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)

    def _get_contains_content_base_url(self, enterprise_catalog):
        """
        Helper to construct the base url for the contains_content_items endpoint
        """
        return reverse(
            'api:v1:enterprise-catalog-content-contains-content-items',
            kwargs={'uuid': enterprise_catalog.uuid}
        )

    def test_contains_content_items_no_params(self):
        """
        Verify the contains_content_items endpoint errors if no parameters are provided
        """
        response = self.client.get(self._get_contains_content_base_url(self.enterprise_catalog))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_contains_content_items_unauthorized_incorrect_jwt_context(self):
        """
        Verify the contains_content_items endpoint rejects users with an invalid JWT context (i.e., enterprise uuid)
        """
        enterprise_catalog = EnterpriseCatalogFactory()
        self.remove_role_assignments()
        url = self._get_contains_content_base_url(enterprise_catalog) + '?course_run_ids=fakeX'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_contains_content_items_implicit_access(self):
        """
        Verify the contains_content_items endpoint responds with 200 OK for user with implicit JWT access
        """
        self.remove_role_assignments()
        url = self._get_contains_content_base_url(self.enterprise_catalog) + '?course_run_ids=fakeX'
        self.assert_correct_contains_response(url, False)

    def test_contains_content_items_no_catalog_query(self):
        """
        Verify the contains_content_items endpoint returns False if there is no associated catalog query
        """
        no_catalog_query_catalog = EnterpriseCatalogFactory(
            catalog_query=None,
            enterprise_uuid=self.enterprise_uuid,
        )
        url = self._get_contains_content_base_url(no_catalog_query_catalog) + '?program_uuids=test-uuid'
        self.assert_correct_contains_response(url, False)

    def test_contains_content_items_keys_in_catalog(self):
        """
        Verify the contains_content_items endpoint returns True if the keys are explicitly in the catalog
        """
        content_key = 'test-key'
        associated_metadata = ContentMetadataFactory(content_key=content_key)
        self.add_metadata_to_catalog(self.enterprise_catalog, [associated_metadata])

        url = self._get_contains_content_base_url(self.enterprise_catalog) + '?course_run_ids=' + content_key
        self.assert_correct_contains_response(url, True)

        # now query for some stuff that's *not* in the catalog
        # to get a different response.
        next_query_params = '?course_run_ids=' + 'test-key-foo,test-key-bar'
        next_url = self._get_contains_content_base_url(self.enterprise_catalog) + next_query_params

        self.assert_correct_contains_response(next_url, False)

        # ..and finally, exercise the per-view cache on the original url.
        # There should now only be queries to select the django user record, session record, and
        # any available enterprise role assignments.
        with self.assertNumQueries(4):
            self.assert_correct_contains_response(url, True)

    def test_contains_content_items_parent_keys_in_catalog(self):
        """
        Verify the contains_content_items endpoint returns True if the parent's key is in the catalog
        """
        parent_metadata = ContentMetadataFactory(content_key='parent-key')
        associated_metadata = ContentMetadataFactory(
            content_key='child-key+101x',
            parent_content_key=parent_metadata.content_key
        )
        self.add_metadata_to_catalog(self.enterprise_catalog, [associated_metadata])

        query_string = '?course_run_ids=' + parent_metadata.content_key
        url = self._get_contains_content_base_url(self.enterprise_catalog) + query_string
        self.assert_correct_contains_response(url, True)

    def test_contains_content_items_course_run_keys_in_catalog(self):
        """
        Verify the contains_content_items endpoint returns True if a course run's key is in the catalog
        """
        content_key = 'course-content-key'
        course_run_content_key = 'course-run-content-key'
        associated_course_metadata = ContentMetadataFactory(
            content_key=content_key,
            content_type=COURSE,
            json_metadata={
                'key': content_key,
                'course_runs': [{'key': course_run_content_key}],
            }
        )
        # create content metadata for course run associated with above course
        ContentMetadataFactory(content_key=course_run_content_key, parent_content_key=content_key)
        self.add_metadata_to_catalog(self.enterprise_catalog, [associated_course_metadata])

        url = self._get_contains_content_base_url(self.enterprise_catalog) + '?course_run_ids=' + course_run_content_key
        self.assert_correct_contains_response(url, True)

    def test_contains_content_items_keys_not_in_catalog(self):
        """
        Verify the contains_content_items endpoint returns False if neither it or its parent's keys are in the catalog
        """
        associated_metadata = ContentMetadataFactory(content_key='some-unrelated-key')
        self.add_metadata_to_catalog(self.enterprise_catalog, [associated_metadata])

        url = self._get_contains_content_base_url(self.enterprise_catalog) + '?course_run_ids=' + 'test-key'
        self.assert_correct_contains_response(url, False)


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
        return reverse('api:v1:get-content-metadata', kwargs={'uuid': enterprise_catalog.uuid})

    def _get_expected_json_metadata(self, content_metadata, is_learner_portal_enabled):  # pylint: disable=too-many-statements
        """
        Helper to get the expected json_metadata from the passed in content_metadata instance
        """
        content_type = content_metadata.content_type
        json_metadata = content_metadata.json_metadata.copy()
        enrollment_url = '{}/enterprise/{}/{}/{}/enroll/?catalog={}&utm_medium=enterprise&utm_source={}'

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

        # course
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

            json_metadata['course_runs'] = course_runs
            json_metadata['active'] = is_any_course_run_active(course_runs)

        # course run
        if content_type == COURSE_RUN:
            if is_learner_portal_enabled:
                course_key = content_metadata.parent_content_key or get_parent_content_key(json_metadata)
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

        # program
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


class EnterpriseCatalogRefreshDataFromDiscoveryTests(APITestMixin):
    """
    Tests for the update catalog metadata view
    """

    def setUp(self):
        super().setUp()
        self.set_up_staff()
        self.catalog_query = CatalogQueryFactory()
        self.enterprise_catalog = EnterpriseCatalogFactory(
            enterprise_uuid=self.enterprise_uuid,
            catalog_query=self.catalog_query,
        )

    @mock.patch('enterprise_catalog.apps.api.v1.views.enterprise_catalog_refresh_data_from_discovery.chain')
    @mock.patch(
        'enterprise_catalog.apps.api.v1.views.enterprise_catalog_refresh_data_from_discovery.'
        'update_catalog_metadata_task'
    )
    @mock.patch(
        'enterprise_catalog.apps.api.v1.views.enterprise_catalog_refresh_data_from_discovery.'
        'update_full_content_metadata_task'
    )
    @mock.patch(
        'enterprise_catalog.apps.api.v1.views.enterprise_catalog_refresh_data_from_discovery.'
        'index_enterprise_catalog_in_algolia_task'
    )
    def test_refresh_catalog(
        self,
        mock_index_task,
        mock_update_full_metadata_task,
        mock_update_metadata_task,
        mock_chain,
    ):
        """
        Verify the refresh_metadata endpoint correctly calls the chain of updating/indexing tasks.
        """
        # Mock the submitted task id for proper rendering
        mock_chain().apply_async().task_id = 1
        # Reset the call count since it was called in the above mock
        mock_chain.reset_mock()

        url = reverse('api:v1:update-enterprise-catalog', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Note that since we're mocking celery's chain, the return values from the previous task don't get passed to
        # the next one, although we do use that functionality in the real view
        mock_chain.assert_called_once_with(
            mock_update_metadata_task.si(self.catalog_query.id),
            mock_update_full_metadata_task.si(),
            mock_index_task.si(),
        )

    def test_refresh_catalog_on_get_returns_405_not_allowed(self):
        """
        Verify the refresh_metadata endpoint does not update the catalog metadata with a get request
        """
        url = reverse('api:v1:update-enterprise-catalog', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_refresh_catalog_on_invalid_uuid_returns_400_bad_request(self):
        """
        Verify the refresh_metadata endpoint returns an HTTP_400_BAD_REQUEST status when passed an invalid ID
        """
        random_uuid = uuid.uuid4()
        url = reverse('api:v1:update-enterprise-catalog', kwargs={'uuid': random_uuid})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class EnterpriseCustomerViewSetTests(APITestMixin):
    """
    Tests for the EnterpriseCustomerViewSet
    """

    def setUp(self):
        super().setUp()
        # clean up any stale test objects
        CatalogQuery.objects.all().delete()
        ContentMetadata.objects.all().delete()
        EnterpriseCatalog.objects.all().delete()

        self.enterprise_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)

        # Set up catalog.has_learner_access permissions
        self.set_up_catalog_learner()

    def tearDown(self):
        super().tearDown()
        # clean up any stale test objects
        CatalogQuery.objects.all().delete()
        ContentMetadata.objects.all().delete()
        EnterpriseCatalog.objects.all().delete()

    def _get_contains_content_base_url(self, enterprise_uuid=None):
        """
        Helper to construct the base url for the contains_content_items endpoint
        """
        return reverse(
            'api:v1:enterprise-customer-contains-content-items',
            kwargs={'enterprise_uuid': enterprise_uuid or self.enterprise_uuid},
        )

    def _get_filter_content_base_url(self, enterprise_uuid=None):
        """
        Helper to construct the base url for the filter_content_items endpoint
        """
        return reverse(
            'api:v1:enterprise-customer-filter-content-items',
            kwargs={'enterprise_uuid': enterprise_uuid or self.enterprise_uuid},
        )

    def _get_generate_diff_base_url(self, enterprise_catalog_uuid=None):
        """
        Helper to construct the base url for the catalog `generate_diff` endpoint
        """
        return reverse(
            'api:v1:generate-catalog-diff',
            kwargs={'uuid': enterprise_catalog_uuid or self.enterprise_catalog.uuid},
        )

    def test_generate_diff_unauthorized_non_catalog_learner(self):
        """
        Verify the generate_diff endpoint rejects users that are not catalog learners
        """
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        url = self._get_generate_diff_base_url()
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_generate_diff_get_supports_up_to_max_content_keys(self):
        """
        Test that GET requests to generate_diff supports up to but not more than the max number of content keys.
        """
        content = ContentMetadataFactory()
        self.add_metadata_to_catalog(self.enterprise_catalog, [content])
        url = self._get_generate_diff_base_url() + '?content_keys=key'

        for key in range(150):
            url += f"&content_keys=key{key}"

        response = self.client.get(url)
        assert response.status_code == 400
        assert response.data == 'catalog_diff GET requests supports up to 100. If more content keys required, please ' \
                                'use a POST body.'

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    def test_generate_diff_matched_modified_uses_content(self, mock_api_client):
        """
        Test that the generate_diff endpoint, when matching content keys, takes the content modified times into
        consideration when generating the matched key's `date_updated`.
        """
        now = self.enterprise_catalog.modified
        customer_modified = str(now - timedelta(hours=1))
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': True,
            'modified': customer_modified,
        }
        content_modified = now + timedelta(hours=1)
        content = ContentMetadataFactory(modified=content_modified)

        self.add_metadata_to_catalog(self.enterprise_catalog, [content])
        url = self._get_generate_diff_base_url()
        response = self.client.post(url, {"content_keys": [content.content_key]})
        assert response.data.get('items_found')[0].get('date_updated') == content_modified

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    def test_generate_diff_matched_modified_uses_customer(self, mock_api_client):
        """
        Test that the generate_diff endpoint, when matching content keys, takes the customer's modified times into
        consideration when generating the matched key's `date_updated`.
        """
        now = self.enterprise_catalog.modified
        customer_modified = now + timedelta(hours=1)
        customer_modified_str = str(customer_modified)
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': True,
            'modified': customer_modified_str,
        }
        content = ContentMetadataFactory(modified=now - timedelta(hours=1))

        self.add_metadata_to_catalog(self.enterprise_catalog, [content])
        url = self._get_generate_diff_base_url()
        response = self.client.post(url, {"content_keys": [content.content_key]})
        assert response.data.get('items_found')[0].get('date_updated') == customer_modified

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    def test_generate_diff_matched_modified_uses_catalog(self, mock_api_client):
        """
        Test that the generate_diff endpoint, when matching content keys, takes the catalog modified times into
        consideration when generating the matched key's `date_updated`.
        """
        now = self.enterprise_catalog.modified
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': True,
            'modified': str(now - timedelta(hours=1)),
        }
        content = ContentMetadataFactory(modified=now - timedelta(hours=1))

        self.add_metadata_to_catalog(self.enterprise_catalog, [content])
        url = self._get_generate_diff_base_url()

        response = self.client.post(url, {"content_keys": [content.content_key]})
        assert response.data.get('items_found')[0].get('date_updated') == now

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    def test_generate_diff_get_parses_all_buckets(self, mock_api_client):
        """
        Test that GET requests to the generate_diff endpoint behave the same as POST requests.
        """
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': True,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }
        content = ContentMetadataFactory()
        content2 = ContentMetadataFactory()
        content3 = ContentMetadataFactory()
        content4 = ContentMetadataFactory()

        self.add_metadata_to_catalog(self.enterprise_catalog, [content, content2, content3, content4])
        url = self._get_generate_diff_base_url()
        response = self.client.post(
            url,
            {"content_keys": [content.content_key, content2.content_key, "bad+key", "bad+key2"]},
        )
        assert response.status_code == 200
        response_data = response.data

        for item in response_data.get('items_not_found'):
            assert item in [{'content_key': 'bad+key'}, {'content_key': 'bad+key2'}]

        for item in response_data.get('items_not_included'):
            assert item in [{'content_key': content3.content_key}, {'content_key': content4.content_key}]

        for item in response_data.get('items_found'):
            assert item in [
                {'content_key': content.content_key, 'date_updated': content.modified},
                {'content_key': content2.content_key, 'date_updated': content2.modified}
            ]

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    def test_generate_diff_returns_whole_catalog_w_empty_key_list(self, mock_api_client):
        """
        Test that the generate_diff endpoint will return all content keys under the catalog not provided under the
        `items_not_included` bucket
        """
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': True,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }
        content = ContentMetadataFactory()
        self.add_metadata_to_catalog(self.enterprise_catalog, [content])
        url = self._get_generate_diff_base_url()
        response = self.client.post(url)
        assert response.data.get('items_not_included') == [{'content_key': content.content_key}]
        assert not response.data.get('items_not_found')
        assert not response.data.get('items_found')

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    def test_generate_diff_returns_content_items_found(self, mock_api_client):
        """
        Test that the generate_diff endpoint will return under the `items_found` bucket all content keys within the
        catalog that were provided.
        """
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': True,
            'modified': str(datetime.now().replace(tzinfo=pytz.UTC)),
        }
        content = ContentMetadataFactory()
        content2 = ContentMetadataFactory()
        self.add_metadata_to_catalog(self.enterprise_catalog, [content, content2])

        url = self._get_generate_diff_base_url()
        response = self.client.post(url, {'content_keys': [content.content_key, content2.content_key]})
        for item in response.data.get('items_found'):
            assert item.get('content_key') in [content.content_key, content2.content_key]
        assert not response.data.get('items_not_found')
        assert not response.data.get('items_not_included')

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    def test_generate_diff_returns_content_items_not_found(self, mock_api_client):
        """
        Test that the generate_diff endpoint will return all content keys provided that were not found under the catalog
        under the `items_not_found` bucket.
        """
        mock_api_client.return_value.get_enterprise_customer.return_value = {
            'slug': self.enterprise_slug,
            'enable_learner_portal': True,
            'modified': str(datetime.now()),
        }
        key = 'bad+key'
        key2 = 'bad+key2'
        url = self._get_generate_diff_base_url()
        response = self.client.post(url, {'content_keys': [key, key2]})
        for item in response.data.get('items_not_found'):
            assert item in [{'content_key': key}, {'content_key': key2}]
        assert not response.data.get('items_found')
        assert not response.data.get('items_not_included')

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

    def test_no_catalog_list_given_without_get_catalogs_containing_specified_content_ids_query(self):
        """
        Verify that the contains_content_items endpoint does not return a list of catalogs without a querystring
        """
        content_metadata = ContentMetadataFactory()
        self.add_metadata_to_catalog(self.enterprise_catalog, [content_metadata])

        # Create a second catalog that has the content we're looking for
        content_key = 'fake-key+101x'
        second_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        relevant_content = ContentMetadataFactory(content_key=content_key)
        self.add_metadata_to_catalog(second_catalog, [relevant_content])
        url = self._get_contains_content_base_url() + '?course_run_ids=' + content_key
        response = self.client.get(url)
        assert 'catalog_list' not in response.json().keys()

    def test_contains_catalog_list_with_catalog_list_param(self):
        """
        Verify the contains_content_items endpoint returns a list of catalogs the course is in if the correct
        parameter is passed
        """
        content_metadata = ContentMetadataFactory()
        self.add_metadata_to_catalog(self.enterprise_catalog, [content_metadata])

        # Create a two catalogs that have the content we're looking for
        content_key = 'fake-key+101x'
        second_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        relevant_content = ContentMetadataFactory(content_key=content_key)
        self.add_metadata_to_catalog(second_catalog, [relevant_content])
        url = self._get_contains_content_base_url() + '?course_run_ids=' + content_key + \
            '&get_catalog_list=True'
        self.assert_correct_contains_response(url, True)

        response = self.client.get(url)
        catalog_list = response.json()['catalog_list']
        assert set(catalog_list) == {str(second_catalog.uuid)}

    def test_contains_catalog_list_with_content_ids_param(self):
        """
        Verify the contains_content_items endpoint returns a list of catalogs the course is in if the correct
        parameter is passed
        """
        content_metadata = ContentMetadataFactory()
        self.add_metadata_to_catalog(self.enterprise_catalog, [content_metadata])

        # Create a two catalogs that have the content we're looking for
        content_key = 'fake-key+101x'
        second_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        relevant_content = ContentMetadataFactory(content_key=content_key)
        self.add_metadata_to_catalog(second_catalog, [relevant_content])
        url = self._get_contains_content_base_url() + '?course_run_ids=' + content_key + \
            '&get_catalogs_containing_specified_content_ids=True'
        self.assert_correct_contains_response(url, True)

        response = self.client.get(url)
        catalog_list = response.json()['catalog_list']
        assert set(catalog_list) == {str(second_catalog.uuid)}

    def test_contains_catalog_list_parent_key(self):
        """
        Verify the contains_content_items endpoint returns a list of catalogs the course is in
        """
        content_metadata = ContentMetadataFactory()
        self.add_metadata_to_catalog(self.enterprise_catalog, [content_metadata])

        # Create a two catalogs that have the content we're looking for
        parent_content_key = 'fake-parent-key+105x'
        content_key = 'fake-key+101x'
        second_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        relevant_content = ContentMetadataFactory(content_key=content_key, parent_content_key=parent_content_key)
        self.add_metadata_to_catalog(second_catalog, [relevant_content])
        content_key_2 = 'fake-key+102x'
        third_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        relevant_content = ContentMetadataFactory(content_key=content_key_2, parent_content_key=parent_content_key)
        self.add_metadata_to_catalog(third_catalog, [relevant_content])

        url = self._get_contains_content_base_url() + '?course_run_ids=' + parent_content_key + \
            '&get_catalogs_containing_specified_content_ids=True'
        response = self.client.get(url).json()
        assert response['contains_content_items'] is True
        catalog_list = response['catalog_list']
        assert set(catalog_list) == {str(second_catalog.uuid), str(third_catalog.uuid)}

    def test_contains_catalog_list_content_items_not_in_catalog(self):
        """
        Verify the contains_content_items endpoint returns a list of catalogs the course is in for multiple catalogs
        """
        content_metadata = ContentMetadataFactory()
        self.add_metadata_to_catalog(self.enterprise_catalog, [content_metadata])

        content_key = 'fake-key+101x'

        url = self._get_contains_content_base_url() + '?course_run_ids=' + content_key + \
            '&get_catalogs_containing_specified_content_ids=True'
        response = self.client.get(url)
        catalog_list = response.json()['catalog_list']
        assert catalog_list == []

    def test_filter_content_items_unauthorized_non_catalog_learner(self):
        """
        Verify the filter_content_items endpoint rejects users that are not catalog learners
        """
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        url = self._get_filter_content_base_url()
        request_json = {
            "content_keys": []
        }
        response = self.client.post(url, request_json).json()
        detail = response.get('detail')
        self.assertEqual(detail, 'MISSING: catalog.has_learner_access')

    def test_filter_content_items_unauthorized_incorrect_jwt_context(self):
        """
        Verify the filter_content_items endpoint rejects users that are catalog learners
        with an incorrect JWT context (i.e., enterprise uuid)
        """
        self.remove_role_assignments()
        url = self._get_filter_content_base_url(enterprise_uuid=uuid.uuid4())
        request_json = {
            "content_keys": []
        }
        response = self.client.post(url, request_json).json()
        detail = response.get('detail')
        self.assertEqual(detail, 'MISSING: catalog.has_learner_access')

    def test_filter_content_items_implicit_access(self):
        """
        Verify the filter_content_items endpoint responds with 200 OK for
        user with implicit JWT access
        """
        self.remove_role_assignments()
        url = self._get_filter_content_base_url()
        request_json = {
            "content_keys": []
        }
        response = self.client.post(url, request_json).json()
        self.assertEqual(response.get('filtered_content_keys'), [])

    def test_filter_content_items_not_in_catalogs(self):
        """
        Verify the filter_content_items endpoint returns empty list if the keys are not in any
        associated catalogs. Also the keys that are not included in the request but are part of
        catalog are also not returned.
        """
        self.add_metadata_to_catalog(
            self.enterprise_catalog, [ContentMetadataFactory(content_key='some-random-course')]
        )
        url = self._get_filter_content_base_url()
        request_json = {
            "content_keys": ['key-not-part-of-catalog']
        }
        response = self.client.post(url, request_json).json()
        self.assertEqual(response.get('filtered_content_keys'), [])

    def test_filter_content_items_in_catalogs(self):
        """
        Verify the filter_content_items endpoint returns the keys if the content is in any associated catalogs.
        """
        content_metadata = ContentMetadataFactory()
        self.add_metadata_to_catalog(self.enterprise_catalog, [content_metadata])

        # Create a second catalog that has the content we're looking for
        relevent_content_key = 'relevant-key'
        second_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        relevant_content = ContentMetadataFactory(content_key=relevent_content_key)
        self.add_metadata_to_catalog(second_catalog, [relevant_content])

        url = self._get_filter_content_base_url()
        request_json = {
            "content_keys": [relevent_content_key],
        }
        response = self.client.post(url, request_json).json()
        self.assertEqual(response.get('filtered_content_keys'), [relevent_content_key])

    def test_filter_content_items_parent_key(self):
        """
        Verify the filter_content_items endpoint returns content keys even when they are found as
        parent_content_key in multiple catalogs and verify it appears only once in the response.
        """
        content_metadata = ContentMetadataFactory()
        self.add_metadata_to_catalog(self.enterprise_catalog, [content_metadata])

        # Create a two catalogs that have the content we're looking for
        parent_content_key = 'fake-parent-key+105x'
        content_key = 'fake-key+101x'
        second_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        relevant_content = ContentMetadataFactory(content_key=content_key, parent_content_key=parent_content_key)
        self.add_metadata_to_catalog(second_catalog, [relevant_content])
        content_key_2 = 'fake-key+102x'
        third_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        relevant_content = ContentMetadataFactory(content_key=content_key_2, parent_content_key=parent_content_key)
        self.add_metadata_to_catalog(third_catalog, [relevant_content])

        url = self._get_filter_content_base_url()
        request_json = {
            "content_keys": [parent_content_key],
        }
        response = self.client.post(url, request_json).json()
        self.assertEqual(response.get('filtered_content_keys'), [parent_content_key])

    def test_filter_content_items_specified_catalogs(self):
        """
        Verify the filter_content_items endpoint only looks into the specified catalogs when they are passed.
        """
        content_key_outside_specified_catalog = 'some-random-course'
        content_metadata = ContentMetadataFactory(content_key=content_key_outside_specified_catalog)
        self.add_metadata_to_catalog(self.enterprise_catalog, [content_metadata])

        # Create a second catalog that has the content we're looking for
        relevant_content_key = 'relevant-key'
        second_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        relevant_content = ContentMetadataFactory(content_key=relevant_content_key)
        self.add_metadata_to_catalog(second_catalog, [relevant_content])

        url = self._get_filter_content_base_url()

        # request payload containt one key outside specified catalog
        request_json = {
            "content_keys": [relevant_content_key, content_key_outside_specified_catalog],
            "catalog_uuids": [str(second_catalog.uuid)]
        }
        response = self.client.post(url, request_json).json()

        # response should only contain content keys found in the "second_catalog"
        self.assertEqual(response.get('filtered_content_keys'), [relevant_content_key])


@ddt.ddt
class DistinctCatalogQueriesViewTests(APITestMixin):
    """
    Tests for the DistinctCatalogQueriesView.
    """
    url = reverse('api:v1:distinct-catalog-queries')

    def setUp(self):
        super().setUp()
        self.set_up_staff()
        self.catalog_query_one = CatalogQueryFactory()
        self.enterprise_catalog_one = EnterpriseCatalogFactory(
            enterprise_uuid=self.enterprise_uuid,
            catalog_query=self.catalog_query_one,
        )

    @ddt.data(
        False,
        True,
    )
    def test_catalogs_different_uuids(self, use_different_query):
        """
        Tests that two catalogs with different CatalogQueries will return
        2 distinct CatalogQuery IDs and two catalogs with the same
        CatalogQueries will return 1 distinct CatalogQuery ID.
        """
        if use_different_query:
            catalog_query_two = CatalogQueryFactory()
        else:
            catalog_query_two = self.catalog_query_one
        enterprise_catalog_two = EnterpriseCatalogFactory(
            enterprise_uuid=self.enterprise_uuid,
            catalog_query=catalog_query_two,
        )
        request_json = {
            'enterprise_catalog_uuids': [
                str(self.enterprise_catalog_one.uuid),
                str(enterprise_catalog_two.uuid),
            ]
        }
        response = self.client.post(self.url, request_json).json()

        if use_different_query:
            assert response['num_distinct_query_ids'] == 2
            assert str(catalog_query_two.id) in response['catalog_uuids_by_catalog_query_id']
        else:
            assert response['num_distinct_query_ids'] == 1
        assert str(self.catalog_query_one.id) in response['catalog_uuids_by_catalog_query_id']


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


@ddt.ddt
class AcademiesViewSetTests(APITestMixin):
    """
    Tests for the AcademyViewSet.
    """
    mock_algolia_hits = {'facetHits': [
        {
            'value': 'leadership',
            'count': 4
        },
        {
            'value': 'management',
            'count': 0
        }
    ]}

    def setUp(self):
        super().setUp()
        self.set_up_catalog_learner()
        self.tag1 = TagFactory(title=self.mock_algolia_hits['facetHits'][0]['value'])
        self.tag2 = TagFactory(title=self.mock_algolia_hits['facetHits'][1]['value'])
        self.academy1 = AcademyFactory()
        self.academy2 = AcademyFactory(tags=[self.tag1, self.tag2])
        self.enterprise_catalog_query = CatalogQueryFactory(uuid=uuid.uuid4())
        self.enterprise_catalog1 = EnterpriseCatalogFactory(catalog_query=self.enterprise_catalog_query)
        self.enterprise_catalog1.academies.add(self.academy1)
        self.enterprise_catalog2 = EnterpriseCatalogFactory(catalog_query=self.enterprise_catalog_query)
        self.enterprise_catalog2.academies.add(self.academy2)

    @mock.patch('enterprise_catalog.apps.api_client.enterprise_cache.EnterpriseApiClient')
    @mock.patch('enterprise_catalog.apps.api.v1.serializers.get_initialized_algolia_client')
    def test_list_for_academies(self, mock_algolia_client, mock_client):  # pylint: disable=unused-argument
        """
        Verify the viewset returns enterprise specific academies
        """
        mock_algolia_client.return_value.algolia_index.search_for_facet_values.side_effect = [
            self.mock_algolia_hits, {'facetHits': []}
        ]
        params = {
            'enterprise_customer': str(self.enterprise_catalog2.enterprise_customer.uuid)
        }
        url = reverse('api:v1:academies-list') + '?{}'.format(urlencode(params))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        results = response.data['results']
        self.assertEqual(uuid.UUID(results[0]['uuid']), self.academy2.uuid)

    @mock.patch('enterprise_catalog.apps.api.v1.serializers.get_initialized_algolia_client')
    def test_retrieve_for_academies(self, mock_algolia_client):
        """
        Verify the viewset retrieves an academy
        """
        mock_algolia_client.return_value.algolia_index.search_for_facet_values.side_effect = [
            self.mock_algolia_hits, {'facetHits': []}
        ]
        url = reverse('api:v1:academies-detail', kwargs={
            'uuid': self.academy2.uuid,
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(uuid.UUID(response.data['uuid']), self.academy2.uuid)

    @mock.patch('enterprise_catalog.apps.api.v1.serializers.get_initialized_algolia_client')
    def test_retrieve_for_tags_no_hits(self, mock_algolia_client):
        """
        Verify the viewset retrieves tags of an academy only if algolia hits for tag are > 0
        """
        mock_algolia_client.return_value.algolia_index.search_for_facet_values.side_effect = [
            self.mock_algolia_hits, {'facetHits': []}
        ]
        url = reverse('api:v1:academies-detail', kwargs={
            'uuid': self.academy2.uuid,
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(uuid.UUID(response.data['uuid']), self.academy2.uuid)
        self.assertEqual(len(response.data['tags']), 1)
        self.assertEqual(
            response.data['tags'][0].get('title'),
            self.mock_algolia_hits['facetHits'][0]['value']
        )

    def test_list_with_missing_enterprise_customer(self):
        """
        Verify the viewset returns no records when enterprise customer is missing in params
        """
        url = reverse('api:v1:academies-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)


@ddt.ddt
class ContentMetadataViewTests(APITestMixin):
    """
    Tests for the readonly ContentMetadata viewset.
    """
    def setUp(self):
        super().setUp()
        self.set_up_staff()
        self.content_metadata_object = ContentMetadataFactory(
            content_type='course',
            content_uuid=uuid.uuid4(),
        )

    def test_list_success(self):
        """
        Test a successful, expected api response for the metadata list endpoint
        """
        url = reverse('api:v1:content-metadata-list')
        response = self.client.get(url)
        response_json = response.json()
        assert len(response_json.get('results')) == 1
        assert response_json.get('results')[0].get("key") == self.content_metadata_object.content_key

    def test_list_with_content_keys(self):
        """
        Test a successful, expected api response for the metadata list endpoint with a supplied content keys query
        param
        """
        ContentMetadataFactory(content_type='course')
        junk_identifier = urlencode({'content_identifiers': 'edx+101'})
        encoded_key = urlencode({'content_identifiers': self.content_metadata_object.content_key})
        query_param_string = f"?{encoded_key}&{junk_identifier}"
        url = reverse('api:v1:content-metadata-list') + query_param_string
        response = self.client.get(url)
        response_json = response.json()
        assert len(response_json.get('results')) == 1
        assert response_json.get('results')[0].get("key") == self.content_metadata_object.content_key
        assert response_json.get('results')[0].get("course_runs")[0].get('start') == '2024-02-12T11:00:00Z'

    def test_get_success(self):
        """
        Test a successful, expected api response for the metadata fetch endpoint
        """
        url = reverse(
            'api:v1:content-metadata-detail',
            kwargs={'pk': self.content_metadata_object.id}
        )
        response = self.client.get(url)
        response_json = response.json()
        assert response_json.get('title') == self.content_metadata_object.json_metadata.get('title')

    def test_filter_list_by_uuid(self):
        """
        Test that the list content_identifiers query param accepts uuids
        """
        query_param_string = f"?content_identifiers={self.content_metadata_object.content_uuid}"
        url = reverse('api:v1:content-metadata-list') + query_param_string
        response = self.client.get(url)
        response_json = response.json()
        assert len(response_json.get('results')) == 1
        assert response_json.get('results')[0].get("key") == self.content_metadata_object.content_key
        assert response_json.get('results')[0].get("course_runs")[0].get('start') == '2024-02-12T11:00:00Z'


@ddt.ddt
class CatalogQueryViewTests(APITestMixin):
    """
    Tests for the readonly ContentMetadata viewset.
    """
    def setUp(self):
        super().setUp()
        self.set_up_catalog_learner()
        self.catalog_query_object = CatalogQueryFactory()
        self.catalog_object = EnterpriseCatalogFactory(catalog_query=self.catalog_query_object)
        self.assign_catalog_admin_jwt_role(str(self.catalog_object.enterprise_uuid))
        # Factory doesn't set up a hash, so do it manually
        self.catalog_query_object.content_filter_hash = get_content_filter_hash(
            self.catalog_query_object.content_filter
        )
        self.catalog_query_object.save()

    def test_get_query_by_hash(self):
        """
        Test that the list content_identifiers query param accepts uuids
        """
        query_param_string = f"?hash={self.catalog_query_object.content_filter_hash}"
        url = reverse('api:v1:get-query-by-hash') + query_param_string
        response = self.client.get(url)
        response_json = response.json()
        # The user is a part of the enterprise that has a catalog that contains this query
        # so they can view the data
        assert response_json.get('uuid') == str(self.catalog_query_object.uuid)
        assert str(response_json.get('content_filter')) == str(self.catalog_query_object.content_filter)

        # Permissions verification while looking up by hash
        different_catalog = EnterpriseCatalogFactory()
        # Factory doesn't set up a hash, so do it manually
        different_catalog.catalog_query.content_filter_hash = get_content_filter_hash(
            different_catalog.catalog_query.content_filter
        )
        different_catalog.save()
        query_param_string = f"?hash={different_catalog.catalog_query.content_filter_hash}"
        url = reverse('api:v1:get-query-by-hash') + query_param_string
        response = self.client.get(url)
        response_json = response.json()
        assert response_json == {'detail': 'Catalog query not found.'}

        # If the user is staff, they get access to everything
        self.set_up_staff()
        response = self.client.get(url)
        response_json = response.json()
        assert response_json.get('uuid') == str(different_catalog.catalog_query.uuid)

        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        response = self.client.get(url)
        assert response.status_code == 404

        self.client.logout()
        response = self.client.get(url)
        assert response.status_code == 401

    def test_get_query_by_hash_not_found(self):
        """
        Test that the get query by hash endpoint returns expected not found
        """
        query_param_string = f"?hash={self.catalog_query_object.content_filter_hash[:-6]}aaaaaa"
        url = reverse('api:v1:get-query-by-hash') + query_param_string
        response = self.client.get(url)
        response_json = response.json()
        assert response_json == {'detail': 'Catalog query not found.'}

    def test_get_query_by_illegal_hash(self):
        """
        Test that the get query by hash endpoint validates filter hashes
        """
        query_param_string = "?hash=foobar"
        url = reverse('api:v1:get-query-by-hash') + query_param_string
        response = self.client.get(url)
        response_json = response.json()
        assert response_json == {'hash': ['Invalid filter hash.']}

    def test_get_query_by_hash_requires_hash(self):
        """
        Test that the get query by hash requires a hash query param
        """
        url = reverse('api:v1:get-query-by-hash')
        response = self.client.get(url)
        response_json = response.json()
        assert response_json == ['You must provide at least one of the following query parameters: hash.']

    def test_catalog_query_retrieve(self):
        """
        Test that the Catalog Query viewset supports retrieving individual queries
        """
        self.assign_catalog_admin_jwt_role(
            self.enterprise_uuid,
            self.catalog_query_object.enterprise_catalogs.first().enterprise_uuid,
        )
        url = reverse('api:v1:catalog-queries-detail', kwargs={'pk': self.catalog_query_object.pk})
        response = self.client.get(url)
        response_json = response.json()
        assert response_json.get('uuid') == str(self.catalog_query_object.uuid)

        different_customer_catalog = EnterpriseCatalogFactory()
        # We don't have a jwt token that includes an admin role for the new enterprise so it is
        # essentially hidden to the requester
        url = reverse('api:v1:catalog-queries-detail', kwargs={'pk': different_customer_catalog.catalog_query.pk})
        response = self.client.get(url)
        assert response.status_code == 404

        # If the user is staff, they get access to everything
        self.set_up_staff()
        response = self.client.get(url)
        response_json = response.json()
        assert response_json.get('uuid') == str(different_customer_catalog.catalog_query.uuid)

        self.client.logout()
        response = self.client.get(url)
        assert response.status_code == 401

    def test_catalog_query_list(self):
        """
        Test that the Catalog Query viewset supports listing queries
        """
        # Create another catalog associated with another enterprise and therefore hidden to the requesting user
        EnterpriseCatalogFactory()
        self.assign_catalog_admin_jwt_role(
            self.enterprise_uuid,
            self.catalog_query_object.enterprise_catalogs.first().enterprise_uuid,
            self.catalog_object.enterprise_uuid,
        )
        url = reverse('api:v1:catalog-queries-list')
        response = self.client.get(url)
        response_json = response.json()
        assert response_json.get('count') == 1
        assert response_json.get('results')[0].get('uuid') == str(self.catalog_query_object.uuid)

        # If the user is staff, they get access to everything
        self.set_up_staff()
        response = self.client.get(url)
        response_json = response.json()
        assert response_json.get('count') == 2

        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        response = self.client.get(url)
        assert response.json() == {'count': 0, 'next': None, 'previous': None, 'results': []}

        self.client.logout()
        response = self.client.get(url)
        assert response.status_code == 401


@ddt.ddt
class VideoReadOnlyViewSetTests(APITestMixin):
    """
    Tests for the VideoReadOnlyViewSet.
    """
    def setUp(self):
        super().setUp()
        self.set_up_catalog_learner()
        self.video = VideoFactory()
        self.video_skill = VideoSkillFactory(video=self.video)
        self.video_transcript_summary = VideoTranscriptSummaryFactory(video=self.video)

    def test_retrieve_for_videos(self):
        """
        Verify the viewset retrieves the correct video
        """
        url = reverse('api:v1:video-detail', kwargs={
            'edx_video_id': self.video.edx_video_id,
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['edx_video_id'], self.video.edx_video_id)
        self.assertEqual(response.data['video_usage_key'], self.video.video_usage_key)
        self.assertEqual(response.data['skills'][0]['name'], self.video_skill.name)
        self.assertEqual(response.data['summary_transcripts'][0], self.video_transcript_summary.summary)
        self.assertEqual(
            response.data['parent_content_metadata']['key'],
            self.video.parent_content_metadata.content_key
        )
