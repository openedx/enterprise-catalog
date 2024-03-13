"""
Tests for the views of the ai_curation app.
"""
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import Client, TestCase
from django.urls import reverse
from rest_framework import status

from enterprise_catalog.apps.ai_curation.api.throttle import (
    GetAICurationThrottle,
)
from enterprise_catalog.apps.ai_curation.enums import AICurationStatus
from enterprise_catalog.apps.ai_curation.tests import factories


class TestAICurationView(TestCase):
    def setUp(self):
        """
        Set up the test data.
        """
        super().setUp()
        self.client = Client()
        self.url = reverse('ai_curation:ai-curation')
        self.task = factories.TaskResultFactory.create()

    def test_get(self):
        """
        Verify that the get method returns the correct data.
        """
        GetAICurationThrottle.allow_request = MagicMock(return_value=True)
        response = self.client.get(self.url, {'task_id': self.task.task_id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], self.task.status)

        response = self.client.get(self.url, {'task_id': str(uuid4())})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(self.url, {'task_id': 'invalid'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('enterprise_catalog.apps.ai_curation.api.v1.views.trigger_ai_curations')
    def test_post(self, mock_trigger_ai_curations):
        """
        Verify that the job calls the trigger_ai_curations with the test data
        """
        data = {'query': 'Give all courses from edX org.', 'catalog_id': str(uuid4())}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('task_id', response.data)
        self.assertEqual(response.data['status'], AICurationStatus.PENDING)

        mock_trigger_ai_curations.delay.assert_called_once()

    def test_post_with_query(self):
        """
        Verify that the api returns error if query length is greater than 300 characters
        """
        data = {'query': 'a' * 301, 'catalog_id': str(uuid4())}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'query': ['Ensure this field has no more than 300 characters.']})
