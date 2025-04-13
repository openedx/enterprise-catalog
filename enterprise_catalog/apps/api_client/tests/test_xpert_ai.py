"""
Tests for the Xpert AI client.
"""
import json
from unittest import mock

from django.conf import settings
from django.test import TestCase

from enterprise_catalog.apps.api_client.xpert_ai import (
    CONNECT_TIMOUET_SECONDS,
    READ_TIMEOUT_SECONDS,
    chat_completion,
)


class ChatCompletionTests(TestCase):
    """
    Tests for the chat_completion function.
    """

    @mock.patch('requests.post')
    def test_chat_completion_success(self, mock_post):
        """
        Verify chat_completion makes the correct POST request and returns the content.
        """
        system_message = "You are a helpful assistant."
        user_messages = [{"role": "user", "content": "Tell me a joke."}]
        expected_response_content = "Why do programmers prefer dark mode? Because light attracts bugs."

        # Mock response
        mock_response = mock.Mock()
        mock_response.json.return_value = [{'content': expected_response_content}]
        mock_post.return_value = mock_response

        actual_content = chat_completion(system_message, user_messages)

        # Validate
        self.assertEqual(actual_content, expected_response_content)
        mock_post.assert_called_once_with(
            settings.XPERT_AI_API_V2,
            headers={'Content-Type': 'application/json'},
            data=json.dumps({
                'client_id': settings.XPERT_AI_CLIENT_ID,
                'system_message': system_message,
                'messages': user_messages,
            }),
            timeout=(CONNECT_TIMOUET_SECONDS, READ_TIMEOUT_SECONDS)
        )
