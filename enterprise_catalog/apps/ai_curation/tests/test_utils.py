"""
Tests for ai_curation app utils.
"""
import json
import logging
from unittest import mock
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from enterprise_catalog.apps.ai_curation.errors import AICurationError
from enterprise_catalog.apps.ai_curation.utils.algolia_utils import (
    fetch_catalog_metadata_from_algolia,
)
from enterprise_catalog.apps.ai_curation.utils.open_ai_utils import (
    chat_completions,
    get_filtered_subjects,
    get_keywords_to_prose,
    get_query_keywords,
)


CHAT_COMPLETIONS_API_KEYWARGS = {"model": 'gpt-4', "temperature": 0.3, "max_tokens": 500}


class TestUtils(TestCase):
    """
    Tests for the AI Curation util functions.
    """
    mock_algolia_hits = {'hits': [
        {
            'aggregation_key': 'course:MITx+19',
            'subjects': ["Business & Management", "Computer Science", "Data Analysis & Statistics"],
            'content_type': 'course',
            'course_type': 'executive-education-2u',
            'objectID': 'course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf9-catalog-query-uuids-0'
        },
        {
            'aggregation_key': 'course:MITx+20',
            'subjects': ["Business & Management", "Economics & Finance", "Philosophy & Ethics", "Engineering"],
            'content_type': 'course',
            'course_type': 'verified',
            'objectID': 'course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf7-catalog-query-uuids-0'
        },
        {
            'aggregation_key': 'program:MITx+21',
            'subjects': ["Computer Science", "Engineering", "Electronics"],
            'content_type': 'program',
            'objectID': 'course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf7-catalog-query-uuids-0'
        }
    ]}

    @mock.patch('enterprise_catalog.apps.ai_curation.utils.algolia_utils.get_initialized_algolia_client')
    def test_fetch_catalog_metadata_from_algolia(self, mock_algolia_client):
        """
        Verify that the catalog metadata from algolia is fetched correctly.
        """
        mock_algolia_client.return_value.algolia_index.search.side_effect = [self.mock_algolia_hits, {'hits': []}]
        ocm_courses, exec_ed_courses, programs, subjects = fetch_catalog_metadata_from_algolia('test_query_title')

        self.assertEqual([c['aggregation_key'] for c in ocm_courses], ['course:MITx+20'])
        self.assertEqual([c['aggregation_key'] for c in exec_ed_courses], ['course:MITx+19'])
        self.assertEqual([p['aggregation_key'] for p in programs], ['program:MITx+21'])
        self.assertEqual(
            sorted(subjects),
            [
                "Business & Management", "Computer Science", "Data Analysis & Statistics", "Economics & Finance",
                "Electronics", "Engineering", "Philosophy & Ethics"
            ]
        )


class TestChatCompletionUtils(TestCase):
    @patch('enterprise_catalog.apps.ai_curation.utils.open_ai_utils.LOGGER')
    @patch('enterprise_catalog.apps.ai_curation.openai_client.requests.post')
    def test_get_filtered_subjects(self, mock_requests, mock_logger):
        """
        Test that get_filtered_subjects returns the correct filtered subjects
        """
        mock_requests.return_value.json.return_value = {
            "role": "assistant",
            "content": json.dumps(['subject1', 'subject2'])
        }
        subjects = ['subject1', 'subject2', 'subject3', 'subject4']
        query = 'test query'
        expected_content = settings.AI_CURATION_FILTER_SUBJECTS_PROMPT.format(query=query, subjects=subjects)

        result = get_filtered_subjects(query, subjects)

        mock_requests.assert_called_once()
        mock_logger.info.assert_has_calls(
            [
                mock.call(
                    '[AI_CURATION] Filtering subjects. Prompt: [%s]',
                    [{'role': 'system', 'content': expected_content}]
                ),
                mock.call('[AI_CURATION] Filtering subjects. Response: [%s]', ['subject1', 'subject2'])
            ]
        )
        assert result == ['subject1', 'subject2']

    @patch('enterprise_catalog.apps.ai_curation.utils.open_ai_utils.LOGGER')
    @patch('enterprise_catalog.apps.ai_curation.openai_client.requests.post')
    def test_get_query_keywords(self, mock_requests, mock_logger):
        """
        Test that get_query_keywords returns the correct keywords
        """
        mock_requests.return_value.json.return_value = {
            "role": "assistant",
            "content": json.dumps(['keyword1', 'keyword2'])
        }
        query = 'test query'
        expected_content = settings.AI_CURATION_QUERY_TO_KEYWORDS_PROMPT.format(query=query)

        result = get_query_keywords(query)

        mock_requests.assert_called_once()
        mock_logger.info.assert_has_calls(
            [
                mock.call(
                    '[AI_CURATION] Generating keywords. Prompt: [%s]',
                    [{'role': 'system', 'content': expected_content}]
                ),
                mock.call('[AI_CURATION] Generating keywords. Response: [%s]', ['keyword1', 'keyword2'])
            ]
        )
        assert result == ['keyword1', 'keyword2']

    @patch('enterprise_catalog.apps.ai_curation.utils.open_ai_utils.LOGGER')
    @patch('enterprise_catalog.apps.ai_curation.openai_client.requests.post')
    @patch('enterprise_catalog.apps.ai_curation.utils.open_ai_utils.get_query_keywords')
    def test_get_keywords_to_prose(self, mock_get_query_keywords, mock_requests, mock_logger):
        """
        Test that get_keywords_to_prose returns the correct prose
        """
        mock_get_query_keywords.return_value = ['keyword1', 'keyword2']
        mock_requests.return_value.json.return_value = {
            "role": "assistant",
            "content": json.dumps(['I am a prose'])
        }
        query = 'test query'
        keywords = ['keyword1', 'keyword2']
        expected_content = settings.AI_CURATION_KEYWORDS_TO_PROSE_PROMPT.format(query=query, keywords=keywords)

        result = get_keywords_to_prose(query)

        mock_requests.assert_called_once()
        mock_logger.info.assert_has_calls(
            [
                mock.call(
                    '[AI_CURATION] Generating prose from keywords. Prompt: [%s]',
                    [{'role': 'system', 'content': expected_content}]
                ),
                mock.call('[AI_CURATION] Generating prose from keywords. Response: [%s]', ['I am a prose'])
            ]
        )
        assert result == 'I am a prose'

    @patch('enterprise_catalog.apps.ai_curation.openai_client.LOGGER')
    @patch('enterprise_catalog.apps.ai_curation.openai_client.requests.post')
    def test_chat_completions_retries(self, mock_requests, mock_logger):
        """
        Test that retries work as expected for chat_completions
        """
        mock_requests.side_effect = ConnectionError()
        messages = [
            {
                'role': 'system',
                'content': 'I am a prompt'
            }
        ]
        with self.assertRaises(AICurationError):
            backoff_logger = logging.getLogger('backoff')
            with mock.patch.multiple(backoff_logger, info=mock.DEFAULT, error=mock.DEFAULT) as mock_backoff_logger:
                chat_completions(messages=messages)

        assert mock_requests.call_count == 3
        assert mock_backoff_logger['info'].call_count == 2
        assert mock_backoff_logger['error'].call_count == 1
        assert mock_logger.exception.called
        mock_logger.exception.assert_has_calls([mock.call('[AI_CURATION] API Error: Prompt: [%s]', messages)])

    @patch('enterprise_catalog.apps.ai_curation.openai_client.LOGGER')
    @patch('enterprise_catalog.apps.ai_curation.openai_client.requests.post')
    def test_chat_completions_decode_json(self, mock_requests, mock_logger):
        """
        Test that json decode error is raised for improper json response
        """
        mock_requests.return_value.json.return_value = {
            "role": "assistant",
            "content": "subjects: ['subject1', 'subject2']"
        }
        messages = [
            {
                'role': 'system',
                'content': 'I am a prompt'
            }
        ]
        with self.assertRaises(AICurationError):
            backoff_logger = logging.getLogger('backoff')
            with mock.patch.multiple(backoff_logger, info=mock.DEFAULT, error=mock.DEFAULT) as mock_backoff_logger:
                chat_completions(messages=messages)

        assert mock_requests.call_count == 3
        assert mock_backoff_logger['info'].call_count == 2
        assert mock_backoff_logger['error'].call_count == 1
        assert mock_logger.exception.called
        mock_logger.exception.assert_has_calls([mock.call('[AI_CURATION] API Error: Prompt: [%s]', messages)])
