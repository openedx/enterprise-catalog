"""
Tests for curation-related views.
"""
import itertools
import uuid

import ddt
from faker import Faker
from rest_framework import status
from rest_framework.reverse import reverse

from enterprise_catalog.apps.api.v1.tests.mixins import APITestMixin
from enterprise_catalog.apps.catalog.constants import COURSE, PROGRAM
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)
from enterprise_catalog.apps.curation.tests.factories import (
    EnterpriseCurationConfigFactory,
    HighlightedContentFactory,
    HighlightSetFactory,
)


fake = Faker()


class CurationAPITestBase(APITestMixin):
    """
    Provides shared test resource setup between curation-related API test classes.

    Contains boilerplate to create 5 highlighted content within 1 highlight set within 1 curation config for the default
    enterprise, and again for another enterprise.
    """
    def setUp(self):
        super().setUp()

        # Since the default behavior of ContentMetadataFactory is to generate ContentMetadata objects for all content
        # types including ones not supported by Curations/Highlighting feature, we set up a content type generator that
        # deterministically provides supported content types.
        supported_content_types = [COURSE, PROGRAM]
        content_type_generator = (
            supported_content_types[idx % len(supported_content_types)]
            for idx in itertools.count()
        )

        # Create the main test objects that the test users should be able to access.
        self.curation_config_one = EnterpriseCurationConfigFactory(enterprise_uuid=self.enterprise_uuid)
        self.highlight_set_one = HighlightSetFactory(enterprise_curation=self.curation_config_one)
        self.card_image_urls_one = [fake.image_url() + '.jpg' for idx in range(5)]
        self.highlighted_content_metadata_one = [
            ContentMetadataFactory(card_image_url=url, content_type=next(content_type_generator))
            for url in self.card_image_urls_one
        ]
        self.highlighted_content_list_one = [
            HighlightedContentFactory(catalog_highlight_set=self.highlight_set_one, content_metadata=cm)
            for cm in self.highlighted_content_metadata_one
        ]

        # Create an extra EnterpriseCurationConfig corresponding to a different enterprise customer that the default
        # test user should not be able to access.
        self.curation_config_two = EnterpriseCurationConfigFactory(enterprise_uuid=uuid.uuid4())
        self.highlight_set_two = HighlightSetFactory(enterprise_curation=self.curation_config_two)
        self.card_image_urls_two = [fake.image_url() + '.jpg' for idx in range(5)]
        self.highlighted_content_metadata_two = [
            ContentMetadataFactory(card_image_url=url, content_type=next(content_type_generator))
            for url in self.card_image_urls_two
        ]
        self.highlighted_content_list_two = [
            HighlightedContentFactory(catalog_highlight_set=self.highlight_set_two, content_metadata=cm)
            for cm in self.highlighted_content_metadata_two
        ]


@ddt.ddt
class EnterpriseCurationConfigReadOnlyViewSetTests(CurationAPITestBase):
    """
    Test EnterpriseCurationConfigReadOnlyViewSet.
    """
    def test_unauthorized_list(self):
        """
        Test viewset rejects list for learners that do not have any needed feature role which would give them access to
        any EnterpriseCurationConfiguration contexts.
        """
        url = reverse('api:v1:enterprise-curations-list')

        # Create an unprivileged learner user. (privileges removed in the next step)
        self.set_up_catalog_learner()

        # Remove both explicit and implicit role grants.
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()

        response = self.client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @ddt.data(
        {'is_catalog_staff': False, 'is_role_assigned_via_jwt': False},
        {'is_catalog_staff': False, 'is_role_assigned_via_jwt': True},
        {'is_catalog_staff': True, 'is_role_assigned_via_jwt': False},
        {'is_catalog_staff': True, 'is_role_assigned_via_jwt': True},
    )
    @ddt.unpack
    def test_authorized_list(self, is_catalog_staff, is_role_assigned_via_jwt):
        """
        Test viewset allows list for catalog learners and enterprise staff users, and the results include only curation
        configs corresponding to their own enterprise.
        """
        url = reverse('api:v1:enterprise-curations-list')

        # Create either a catalog learner user or enterprise staff user, each with access to only one catalog.
        if is_catalog_staff:
            self.set_up_staff()
        else:
            self.set_up_catalog_learner()

        # Remove either explicit or implicit role grants.
        if is_role_assigned_via_jwt:
            self.remove_role_assignments()
        else:
            self.set_up_invalid_jwt_role()

        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        curation_config_results = response.json()['results']
        assert len(curation_config_results) == 1
        assert curation_config_results[0]['uuid'] == str(self.curation_config_one.uuid)

    @ddt.data(
        {'is_catalog_staff': False, 'is_role_assigned_via_jwt': False, 'curation_config_exists': False},
        {'is_catalog_staff': False, 'is_role_assigned_via_jwt': False, 'curation_config_exists': True},
        {'is_catalog_staff': False, 'is_role_assigned_via_jwt': True, 'curation_config_exists': False},
        {'is_catalog_staff': False, 'is_role_assigned_via_jwt': True, 'curation_config_exists': True},
        {'is_catalog_staff': True, 'is_role_assigned_via_jwt': False, 'curation_config_exists': False},
        {'is_catalog_staff': True, 'is_role_assigned_via_jwt': False, 'curation_config_exists': True},
        {'is_catalog_staff': True, 'is_role_assigned_via_jwt': True, 'curation_config_exists': False},
        {'is_catalog_staff': True, 'is_role_assigned_via_jwt': True, 'curation_config_exists': True},
    )
    @ddt.unpack
    def test_unauthorized_detail_different_customer(
        self, is_catalog_staff, is_role_assigned_via_jwt, curation_config_exists
    ):
        """
        Test that the detail endpoint rejects requests for an EnterpriseCurationConfig that does exist, but that
        learners and staff should not have access to.
        """
        if curation_config_exists:
            url = reverse('api:v1:enterprise-curations-detail', kwargs={'uuid': self.curation_config_two.uuid})
        else:
            url = reverse('api:v1:enterprise-curations-detail', kwargs={'uuid': str(uuid.uuid4())})

        # Create either a catalog learner user or enterprise staff user, each with access to only one catalog.
        if is_catalog_staff:
            self.set_up_staff()
        else:
            self.set_up_catalog_learner()

        # Remove either explicit or implicit role grants.
        if is_role_assigned_via_jwt:
            self.remove_role_assignments()
        else:
            self.set_up_invalid_jwt_role()

        response = self.client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @ddt.data(
        {'is_catalog_staff': False, 'is_role_assigned_via_jwt': False},
        {'is_catalog_staff': False, 'is_role_assigned_via_jwt': True},
        {'is_catalog_staff': True, 'is_role_assigned_via_jwt': False},
        {'is_catalog_staff': True, 'is_role_assigned_via_jwt': True},
    )
    @ddt.unpack
    def test_authorized_detail(self, is_catalog_staff, is_role_assigned_via_jwt):
        """
        Test viewset allows calling the detail endpoint for catalog learners and enterprise staff users that should have
        access to the specific EnterpriseCurationConfig being requested.
        """
        url = reverse('api:v1:enterprise-curations-detail', kwargs={'uuid': self.curation_config_one.uuid})

        # Create either a catalog learner user or enterprise staff user, each with access to only one catalog.
        if is_catalog_staff:
            self.set_up_staff()
        else:
            self.set_up_catalog_learner()

        # Remove either explicit or implicit role grants.
        if is_role_assigned_via_jwt:
            self.remove_role_assignments()
        else:
            self.set_up_invalid_jwt_role()

        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['uuid'] == str(self.curation_config_one.uuid)

    def test_content_ordered_by_created(self):
        """
        Test that the highlighted content is serialized in the same order as they were added.
        """
        url = reverse('api:v1:enterprise-curations-detail', kwargs={'uuid': self.curation_config_one.uuid})
        self.set_up_catalog_learner()

        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        highlighted_content_uuids = response.json()['highlight_sets'][0]['highlighted_content_uuids']
        expected_highlighted_content_uuids = [str(hc.uuid) for hc in self.highlighted_content_list_one]
        assert highlighted_content_uuids == expected_highlighted_content_uuids

    def test_selected_card_image_url_is_first(self):
        """
        Test that the `card_image_url` of the highlight set is that of the first highlighted content.

        This is more of a basic smoke test, since HighlightSetViewSetTests::test_deterministic_card_image() is far more
        thorough.
        """
        url = reverse('api:v1:enterprise-curations-detail', kwargs={'uuid': self.curation_config_one.uuid})
        self.set_up_catalog_learner()

        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['highlight_sets'][0]['card_image_url'] == self.card_image_urls_one[0]


class EnterpriseCurationConfigViewSetTests(CurationAPITestBase):
    """
    Test EnterpriseCurationConfigViewSet.
    """
    def test_unauthorized_patch_learner(self):
        """
        Test that learners cannot edit any EnterpriseCurationConfig.
        """
        url = reverse('api:v1:enterprise-curations-admin-detail', kwargs={'uuid': self.curation_config_one.uuid})
        # Create a learner user with learner (readonly) permissions on curation_config_one.
        self.set_up_catalog_learner()
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthorized_patch_another_curation_config(self):
        """
        Test that one enterprise customer cannot edit the title of anoother customers' EnterpriseCurationConfig.
        """
        url = reverse('api:v1:enterprise-curations-admin-detail', kwargs={'uuid': self.curation_config_two.uuid})
        # Create privileged staff user that should only have acces to curation_config_one.
        self.set_up_staff()
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_patch(self):
        """
        Test that an enterprise customer can edit their own EnterpriseCurationConfig objects.
        """
        url = reverse('api:v1:enterprise-curations-admin-detail', kwargs={'uuid': self.curation_config_one.uuid})
        self.set_up_staff()
        patch_data = {'is_highlight_feature_active': False}
        response = self.client.patch(url, patch_data)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['is_highlight_feature_active'] is False

        # May as well confirm that it persisted in the database:
        url = reverse('api:v1:enterprise-curations-detail', kwargs={'uuid': self.curation_config_one.uuid})
        response_get = self.client.get(url)
        assert response_get.json()['is_highlight_feature_active'] is False


class HighlightSetReadOnlyViewSetTests(CurationAPITestBase):
    """
    Test HighlightSetReadOnlyViewSet.
    """
    def test_unauthorized_list(self):
        """
        A completely unprivileged learner should not be able to list highlight sets.
        """
        url = reverse('api:v1:highlight-sets-list')

        # Create an unprivileged learner user.
        self.set_up_catalog_learner()
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()

        response = self.client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_catalog_learner(self):
        """
        A catalog learner should be able to list the highlight sets of their own enterprise customer, but not that of
        other enterprise customers.
        """
        url = reverse('api:v1:highlight-sets-list')
        self.set_up_catalog_learner()
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        highlight_sets_results = response.json()['results']
        assert len(highlight_sets_results) == 1
        assert highlight_sets_results[0]['uuid'] == str(self.highlight_set_one.uuid)

    def test_content_ordered_by_created(self):
        """
        Test that the highlighted content is serialized in the same order as they were added.
        """
        detail_url = reverse('api:v1:highlight-sets-detail', kwargs={'uuid': self.highlight_set_one.uuid})
        self.set_up_catalog_learner()

        response = self.client.get(detail_url)
        assert response.status_code == status.HTTP_200_OK
        highlighted_content = response.json()['highlighted_content']
        highlighted_content_keys = [cm['content_key'] for cm in highlighted_content]
        expected_highlighted_content_keys = [cm.content_key for cm in self.highlighted_content_metadata_one]
        assert highlighted_content_keys == expected_highlighted_content_keys


@ddt.ddt
class HighlightSetViewSetTests(CurationAPITestBase):
    """
    Test HighlightSetViewSet.

    NOTE: Some tests are missing (e.g. creation/deletion) due to the current fluid state of the API due to development
    of the curations feature; I decided to just defer those tests for now.  For the purposes of testing security, the
    patch tests should be sufficient. -Troy
    """
    def test_unauthorized_patch_learner(self):
        """
        Test that catalog learners cannot edit any HighlightSet, because they should only have readonly access.
        """
        url = reverse('api:v1:highlight-sets-admin-detail', kwargs={'uuid': self.highlight_set_one.uuid})
        # Create a learner user with learner (readonly) permissions on curation_config_one.
        self.set_up_catalog_learner()
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @ddt.data(
        {'highlight_set_exists': False},
        {'highlight_set_exists': False},
    )
    @ddt.unpack
    def test_unauthorized_patch_another_customer(self, highlight_set_exists):
        """
        Test that one enterprise customer cannot edit the title of another customers' HighlightSet.
        """
        if highlight_set_exists:
            url = reverse('api:v1:highlight-sets-admin-detail', kwargs={'uuid': self.highlight_set_two.uuid})
        else:
            url = reverse('api:v1:highlight-sets-admin-detail', kwargs={'uuid': str(uuid.uuid4())})
        # Create privileged staff user that should only have acces to self.highlight_set_one.
        self.set_up_staff()
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_patch(self):
        """
        Test that an enterprise customer can edit their own HighlightSet objects.
        """
        url = reverse('api:v1:highlight-sets-admin-detail', kwargs={'uuid': self.highlight_set_one.uuid})
        self.set_up_staff()
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['title'] == 'Patch title'

        # May as well confirm that it persisted in the database:
        url = reverse('api:v1:highlight-sets-detail', kwargs={'uuid': self.highlight_set_one.uuid})
        response_get = self.client.get(url)
        assert response_get.json()['title'] == 'Patch title'

    def test_deterministic_card_image(self):
        """
        Test that the card image is always the earliest still-existing highlighted content added.

        Before removing any content from the highlight set, the selected URL has an original index of 0:
            0 1 2 3 4
            ^
        After removing the second element, the selected URL still has an original index of 0:
            0 2 3 4
            ^
        After removing the first element, the selected URL now has an original index of 2:
            2 3 4
            ^
        After adding an element, the selected URL still has an original index of 2:
            2 3 4 (new)
            ^
        Finally, after removing ALL elements, the selected URL is null (JSON null).
        """
        detail_url = reverse('api:v1:highlight-sets-admin-detail', kwargs={'uuid': self.highlight_set_one.uuid})
        self.set_up_staff()

        response = self.client.get(detail_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['card_image_url'] == self.card_image_urls_one[0]

        # Remove the highlighted content with original index of 1, and check that the selected card_image_url is still
        # that of original index 0.
        remove_url = reverse(
            'api:v1:highlight-sets-admin-remove-content',
            kwargs={'uuid': self.highlight_set_one.uuid},
        )
        response = self.client.post(
            remove_url, {'content_keys': [self.highlighted_content_list_one[1].content_metadata.content_key]},
        )
        assert response.status_code == status.HTTP_201_CREATED
        # Sanity check that something was actually removed.
        assert len(response.json()['highlight_set']['highlighted_content']) == 4
        assert response.json()['highlight_set']['card_image_url'] == self.card_image_urls_one[0]

        # Remove the highlighted content with original index of 0, and check that the selected card_image_url is updated
        # to that of original index 2.
        response = self.client.post(
            remove_url, {'content_keys': [self.highlighted_content_list_one[0].content_metadata.content_key]},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.json()['highlight_set']['highlighted_content']) == 3
        assert response.json()['highlight_set']['card_image_url'] == self.card_image_urls_one[2]

        # Adding new content should have no impact to the card_image_url at the HighlightSet level.
        add_url = reverse(
            'api:v1:highlight-sets-admin-add-content',
            kwargs={'uuid': self.highlight_set_one.uuid},
        )
        response = self.client.post(
            add_url, {'content_keys': [self.highlighted_content_list_one[0].content_metadata.content_key]},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.json()['highlight_set']['highlighted_content']) == 4
        assert response.json()['highlight_set']['card_image_url'] == self.card_image_urls_one[2]

        # Remove ALL content.
        response = self.client.post(
            remove_url, {'content_keys': [cm.content_key for cm in self.highlighted_content_metadata_one]},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.json()['highlight_set']['highlighted_content']) == 0
        assert response.json()['highlight_set']['card_image_url'] is None
