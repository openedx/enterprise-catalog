"""
Tests for the views of the ai_curation app.
"""
from unittest.mock import MagicMock, patch
from uuid import uuid4

from celery.states import STARTED, SUCCESS
from django.core.cache import cache as django_cache
from django.test import Client, TestCase
from django.urls import reverse
from rest_framework import status

from enterprise_catalog.apps.ai_curation.api.throttle import (
    GetAICurationThrottle,
)
from enterprise_catalog.apps.ai_curation.errors import USER_MESSAGE
from enterprise_catalog.apps.ai_curation.tests import factories
from enterprise_catalog.apps.ai_curation.utils import get_cache_key


class TestAICurationView(TestCase):
    def setUp(self):
        """
        Set up the test data.
        """
        super().setUp()
        self.client = Client()
        self.url = reverse('ai_curation:ai-curation')
        self.task = factories.TaskResultFactory.create()
        GetAICurationThrottle.allow_request = MagicMock(return_value=True)

        self.partially_filtered_ocm_courses = [
            {
                'aggregation_key': 'course:MITx+19',
                'subjects': ["Python", "Computer Science", "Data Analysis & Statistics"],
                'content_type': 'course',
                'course_type': 'executive-education-2u',
                'skills': ['Business', 'Data Analysis', 'Data Science', 'Statistics'],
                'title': 'Python for data science',
                'short_description': 'Learn java for data science',
                'outcome': 'Learn data science with Python',
                'program_titles': [],
                'tf_idf_score': 0.3,
                'tf_idf_percentile': 0.3,
            },
            {
                'aggregation_key': 'course:MITx+20',
                'subjects': ["Java", "C", 'C++'],
                'content_type': 'course',
                'course_type': 'verified',
                'skills': ['Programming Basics', 'Software Engineering'],
                'title': 'Programming Basics',
                'short_description': 'Learn Programming Basics',
                'outcome': 'Learn Programming Basics',
                'program_titles': ['Learn Programming Basics'],
                'tf_idf_score': 0.6,
                'tf_idf_percentile': 0.6,
            },
        ]
        self.partially_filtered_exec_ed_courses = [
            {
                'aggregation_key': 'course:MITx+21',
                'subjects': ["Java", "Computer Science", "Data Analysis & Statistics", ],
                'content_type': 'course',
                'course_type': 'executive-education-2u',
                'skills': ['Java', 'Computer Science', 'Data Science'],
                'title': 'Java for data science',
                'short_description': 'Learn Java for data science',
                'program_titles': ['Java for data science'],
                'outcome': 'Learn data science with Java',
                'tf_idf_score': 0.5,
                'tf_idf_percentile': 0.5,
            },
        ]

        self.programs = [
            {'title': 'Java for data science'},
            {'title': 'Learn Programming Basics'},
            {'title': 'Software Engineering for professionals'},
        ]

    def test_get(self):
        """
        Verify that the get method returns the correct data.
        """
        response = self.client.get(self.url, {'task_id': self.task.task_id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], self.task.status)

        response = self.client.get(self.url, {'task_id': str(uuid4())})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(self.url, {'task_id': 'invalid'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_with_threshold(self):
        """
        Verify that the get method returns the correct data when a threshold is provided.
        """
        # Mark the task as done.
        self.task.status = SUCCESS
        self.task.save()

        # Populate the cache with the test data
        django_cache.set(
            get_cache_key(task_id=self.task.task_id, content_type='ocm_courses'),
            self.partially_filtered_ocm_courses
        )
        django_cache.set(
            get_cache_key(task_id=self.task.task_id, content_type='exec_ed_courses'),
            self.partially_filtered_exec_ed_courses
        )
        django_cache.set(
            get_cache_key(task_id=self.task.task_id, content_type='programs'),
            self.programs
        )

        response = self.client.get(self.url, {'task_id': self.task.task_id, 'threshold': 0.4})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'SUCCESS')
        self.assertEqual(len(response.data['result']['ocm_courses']), 1)
        self.assertEqual(len(response.data['result']['exec_ed_courses']), 1)
        self.assertEqual(len(response.data['result']['programs']), 2)

        # Validate the correct courses/programs are returned
        self.assertEqual(response.data['result']['ocm_courses'][0]['aggregation_key'], 'course:MITx+20')
        self.assertEqual(response.data['result']['exec_ed_courses'][0]['aggregation_key'], 'course:MITx+21')
        self.assertEqual(response.data['result']['programs'][0]['title'], 'Java for data science')
        self.assertEqual(response.data['result']['programs'][1]['title'], 'Learn Programming Basics')

    def test_get_with_threshold_invalid_threshold(self):
        """
        Verify that the get method handles invalid threshold.
        """
        # Mark the task as done.
        self.task.status = SUCCESS
        self.task.save()

        # Populate the cache with the test data
        django_cache.set(
            get_cache_key(task_id=self.task.task_id, content_type='ocm_courses'),
            self.partially_filtered_ocm_courses
        )
        django_cache.set(
            get_cache_key(task_id=self.task.task_id, content_type='exec_ed_courses'),
            self.partially_filtered_exec_ed_courses
        )
        django_cache.set(
            get_cache_key(task_id=self.task.task_id, content_type='programs'),
            self.programs
        )

        response = self.client.get(self.url, {'task_id': self.task.task_id, 'threshold': 'invalid-value'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Invalid threshold.')

    def test_get_with_threshold_task_not_done(self):
        """
        Verify that the get method returns handles the case when user tries to tweak data but the task is not done.
        """
        # Mark the task as in progress.
        self.task.status = STARTED
        self.task.save()

        # Populate the cache with the test data
        django_cache.set(
            get_cache_key(task_id=self.task.task_id, content_type='ocm_courses'),
            self.partially_filtered_ocm_courses
        )
        django_cache.set(
            get_cache_key(task_id=self.task.task_id, content_type='exec_ed_courses'),
            self.partially_filtered_exec_ed_courses
        )
        django_cache.set(
            get_cache_key(task_id=self.task.task_id, content_type='programs'),
            self.programs
        )

        response = self.client.get(self.url, {'task_id': self.task.task_id, 'threshold': '0.5'})
        self.assertEqual(response.status_code, status.HTTP_425_TOO_EARLY)
        self.assertEqual(response.data['error'], 'Evaluation of curations is not complete yet.')

    def test_get_with_threshold_cache_not_found(self):
        """
        Verify that the get method returns handles the case when user tries to tweak data but cache entry is missing.
        """
        # Mark the task as done.
        self.task.status = SUCCESS
        self.task.save()

        # Clear the cache
        django_cache.clear()

        response = self.client.get(self.url, {'task_id': self.task.task_id, 'threshold': '0.3'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], USER_MESSAGE)

    @patch('enterprise_catalog.apps.ai_curation.api.v1.views.trigger_ai_curations')
    def test_post(self, mock_trigger_ai_curations):
        """
        Verify that the job calls the trigger_ai_curations with the test data
        """
        mock_trigger_ai_curations.delay = MagicMock(return_value=self.task)
        data = {'query': 'Give all courses from edX org.', 'catalog_name': 'Test Catalog'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('task_id', response.data)
        self.assertIn('status', response.data)
        self.assertEqual(response.data['status'], self.task.status)

        mock_trigger_ai_curations.delay.assert_called_once()

    def test_post_with_query(self):
        """
        Verify that the api returns error if query length is greater than 300 characters
        """
        data = {'query': 'a' * 301, 'catalog_name': 'Test Catalog'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'query': ['Ensure this field has no more than 300 characters.']})
