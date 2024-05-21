"""
Tests for ai_curation app utils.
"""
import json
import logging
from unittest import mock
from unittest.mock import MagicMock, patch

import httpx
from django.conf import settings
from django.test import TestCase
from openai import APIConnectionError

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
    @patch('enterprise_catalog.apps.ai_curation.openai_client.client.chat.completions.create')
    def test_get_filtered_subjects(self, mock_create, mock_logger):
        """
        Test that get_filtered_subjects returns the correct filtered subjects
        """
        mock_create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps(['subject1', 'subject2'])))]
        )
        subjects = ['subject1', 'subject2', 'subject3', 'subject4']
        query = 'test query'
        expected_content = settings.AI_CURATION_FILTER_SUBJECTS_PROMPT.format(query=query, subjects=subjects)

        result = get_filtered_subjects(query, subjects)

        mock_create.assert_called_once_with(
            messages=[{'role': 'system', 'content': expected_content}], **CHAT_COMPLETIONS_API_KEYWARGS
        )
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

    @patch('enterprise_catalog.apps.ai_curation.openai_client.LOGGER')
    @patch('enterprise_catalog.apps.ai_curation.openai_client.client.chat.completions.create')
    def test_invalid_json(self, mock_create, mock_logger):
        """
        Test that correct exception is raised if chat.completions.create send an invalid json
        """
        mock_create.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content='non json response'))])

        messages = [
            {
                'role': 'system',
                'content': 'I am a prompt'
            }
        ]
        with self.assertRaises(AICurationError):
            chat_completions(messages)

        assert mock_create.call_count == 3
        assert mock_logger.error.called
        mock_logger.error.assert_has_calls([
            mock.call(
                '[AI_CURATION] Invalid JSON response received from chatgpt: Prompt: [%s], Response: [%s]',
                [{'role': 'system', 'content': 'I am a prompt'}],
                mock.ANY
            ),
            mock.call(
                '[AI_CURATION] Invalid JSON response received from chatgpt: Prompt: [%s], Response: [%s]',
                [{'role': 'system', 'content': 'I am a prompt'}],
                mock.ANY
            ),
            mock.call(
                '[AI_CURATION] Invalid JSON response received from chatgpt: Prompt: [%s], Response: [%s]',
                [{'role': 'system', 'content': 'I am a prompt'}],
                mock.ANY
            )
        ])

    @patch('enterprise_catalog.apps.ai_curation.openai_client.LOGGER')
    @patch('enterprise_catalog.apps.ai_curation.openai_client.client.chat.completions.create')
    def test_valid_json_with_wrong_type(self, mock_create, mock_logger):
        """
        Test that correct exception is raised if chat.completions.create send a valid json but wrong type
        """
        mock_create.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content='{"a": 1}'))])

        messages = [
            {
                'role': 'system',
                'content': 'I am a prompt'
            }
        ]
        with self.assertRaises(AICurationError):
            chat_completions(messages)

        assert mock_create.call_count == 3
        assert mock_logger.error.called
        mock_logger.error.assert_has_calls([
            mock.call(
                '[AI_CURATION] JSON response received but response type is incorrect: Prompt: [%s], Response: [%s]',
                [{'role': 'system', 'content': 'I am a prompt'}],
                mock.ANY
            ),
            mock.call(
                '[AI_CURATION] JSON response received but response type is incorrect: Prompt: [%s], Response: [%s]',
                [{'role': 'system', 'content': 'I am a prompt'}],
                mock.ANY
            ),
            mock.call(
                '[AI_CURATION] JSON response received but response type is incorrect: Prompt: [%s], Response: [%s]',
                [{'role': 'system', 'content': 'I am a prompt'}],
                mock.ANY
            )
        ])

    @patch('enterprise_catalog.apps.ai_curation.utils.open_ai_utils.LOGGER')
    @patch('enterprise_catalog.apps.ai_curation.openai_client.client.chat.completions.create')
    def test_get_query_keywords(self, mock_create, mock_logger):
        """
        Test that get_query_keywords returns the correct keywords
        """
        mock_create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps(['keyword1', 'keyword2'])))]
        )
        query = 'test query'
        expected_content = settings.AI_CURATION_QUERY_TO_KEYWORDS_PROMPT.format(query=query)

        result = get_query_keywords(query)

        mock_create.assert_called_once_with(
            messages=[{'role': 'system', 'content': expected_content}], **CHAT_COMPLETIONS_API_KEYWARGS
        )
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
    @patch('enterprise_catalog.apps.ai_curation.openai_client.client.chat.completions.create')
    @patch('enterprise_catalog.apps.ai_curation.utils.open_ai_utils.get_query_keywords')
    def test_get_keywords_to_prose(self, mock_get_query_keywords, mock_create, mock_logger):
        """
        Test that get_keywords_to_prose returns the correct prose
        """
        mock_get_query_keywords.return_value = ['keyword1', 'keyword2']
        mock_create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps(['I am a prose'])))]
        )
        query = 'test query'
        keywords = ['keyword1', 'keyword2']
        expected_content = settings.AI_CURATION_KEYWORDS_TO_PROSE_PROMPT.format(query=query, keywords=keywords)

        result = get_keywords_to_prose(query)

        mock_create.assert_called_once_with(
            messages=[{'role': 'system', 'content': expected_content}], **CHAT_COMPLETIONS_API_KEYWARGS
        )
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
    @patch('enterprise_catalog.apps.ai_curation.openai_client.client.chat.completions.create')
    def test_chat_completions_retries(self, mock_create, mock_logger):
        """
        Test that retries work as expected for chat_completions
        """
        mock_create.side_effect = APIConnectionError(request=httpx.Request("GET", "https://api.example.com"))
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

        assert mock_create.call_count == 3
        assert mock_backoff_logger['info'].call_count == 2
        mock_backoff_logger['info'].assert_has_calls(
            [
                mock.call(
                    'Backing off %s(...) for %.1fs (%s)',
                    'chat_completions',
                    mock.ANY,
                    'openai.APIConnectionError: Connection error.'
                ),
                mock.call(
                    'Backing off %s(...) for %.1fs (%s)',
                    'chat_completions',
                    mock.ANY,
                    'openai.APIConnectionError: Connection error.'
                )
            ]
        )
        assert mock_backoff_logger['error'].call_count == 1
        mock_backoff_logger['error'].assert_has_calls(
            [
                mock.call(
                    'Giving up %s(...) after %d tries (%s)',
                    'chat_completions',
                    3,
                    'openai.APIConnectionError: Connection error.'
                )
            ]
        )
        assert mock_logger.exception.called
        mock_logger.exception.assert_has_calls([mock.call('[AI_CURATION] API Error: Prompt: [%s]', messages)])
