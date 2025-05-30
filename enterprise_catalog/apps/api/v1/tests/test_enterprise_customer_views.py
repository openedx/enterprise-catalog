import uuid
from datetime import datetime, timedelta
from unittest import mock

import pytz
from algoliasearch.exceptions import AlgoliaException
from django.test import override_settings
from rest_framework import status

from enterprise_catalog.apps.api.base.tests.enterprise_customer_views import (
    BaseEnterpriseCustomerViewSetTests,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
    EnterpriseCatalogFactory,
)


class EnterpriseCustomerViewSetTests(BaseEnterpriseCustomerViewSetTests):
    """
    Tests for the EnterpriseCustomerViewSet
    """
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

    @override_settings(
        ALGOLIA={
            'APPLICATION_ID': 'fake-app-id',
            'API_KEY': 'fake-api-key',
            'SEARCH_API_KEY': 'fake-search-api-key',
            'INDEX_NAME': 'fake-index',
            'REPLICA_INDEX_NAME': 'fake-replica-index',
        },
    )
    def test_secured_algolia_api_key_generation(self):
        """
        Test that the secured Algolia API key is generated correctly.
        """
        url = self._get_secured_algolia_api_key_base_url(self.enterprise_uuid)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected_catalog_to_catalog_query_mappings = {
            str(self.enterprise_catalog.uuid): str(self.enterprise_catalog.catalog_query.uuid),
        }
        self.assertIsInstance(response.data['algolia']['secured_api_key'], str)
        self.assertTrue(bool(response.data['algolia']['secured_api_key']))  # Ensures the string isn't empty

        # Validate ISO format for valid_until
        valid_until = response.data['algolia']['valid_until']
        try:
            datetime.fromisoformat(valid_until)
        except ValueError:  # pragma: no cover
            self.fail(f"Invalid ISO format for valid_until: {valid_until}")

        # Validate catalog uuids to catalog query uuids mapping
        self.assertEqual(
            response.data['catalog_uuids_to_catalog_query_uuids'],
            expected_catalog_to_catalog_query_mappings,
        )

    @override_settings(ALGOLIA={})
    def test_secured_algolia_api_key_missing_search_api_key(self):
        """
        Test that the secured Algolia API key is not generated if the search API key is missing.
        """
        url = self._get_secured_algolia_api_key_base_url(self.enterprise_uuid)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        expected_error_response = {
            'user_message': 'Error generating secured Algolia API key.',
            'developer_message': (
                'Cannot generate secured Algolia API key without the ALGOLIA.SEARCH_API_KEY in settings.'
            ),
        }
        self.assertEqual(response.data, expected_error_response)

    @mock.patch(
        "algoliasearch.search_client.SearchClient.generate_secured_api_key",
        side_effect=AlgoliaException("Mocked exception"),
    )
    @override_settings(ALGOLIA={'SEARCH_API_KEY': 'fake-search-api-search'})
    def test_secured_algolia_api_key_algolia_exception(self, mock_generate_key):  # pylint: disable=unused-argument
        """
        Test that the secured Algolia API key is not generated if an AlgoliaException occurs.
        """
        url = self._get_secured_algolia_api_key_base_url(self.enterprise_uuid)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        expected_error_response = {
            'user_message': 'Error generating secured Algolia API key.',
            'developer_message': 'Mocked exception',
        }
        self.assertEqual(response.data, expected_error_response)

    def test_secured_algolia_api_key_no_catalogs(self):
        """
        Test that the secured Algolia API key is not generated if there are no catalogs.
        """
        fake_enterprise_uuid = uuid.uuid4()
        self.set_up_catalog_learner(enterprise_uuid=fake_enterprise_uuid)
        url = self._get_secured_algolia_api_key_base_url(enterprise_uuid=fake_enterprise_uuid)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        expected_error_response = {
            'user_message': 'Error generating secured Algolia API key.',
            'developer_message': 'No enterprise catalogs found for the specified enterprise customer.',
        }
        self.assertEqual(response.data, expected_error_response)

    def test_secured_algolia_api_key_no_catalog_queries(self):
        """
        Test that the secured Algolia API key is not generated if there are no catalog queries.
        """
        fake_enterprise_uuid = uuid.uuid4()
        EnterpriseCatalogFactory(
            enterprise_uuid=fake_enterprise_uuid,
            catalog_query=None,  # Ensure no catalog query is associated with the catalog
        )
        self.set_up_catalog_learner(enterprise_uuid=fake_enterprise_uuid)
        url = self._get_secured_algolia_api_key_base_url(enterprise_uuid=fake_enterprise_uuid)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        expected_error_response = {
            'user_message': 'Error generating secured Algolia API key.',
            'developer_message': 'No catalog queries found for the specified enterprise customer.',
        }
        self.assertEqual(response.data, expected_error_response)
