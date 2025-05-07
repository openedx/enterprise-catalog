"""
Xpert AI client
"""

import json

import requests
from django.conf import settings


CONNECT_TIMOUET_SECONDS = 5
READ_TIMEOUT_SECONDS = 20


def chat_completion(system_message, user_messages):
    """
    Generate response using xpert api.

    Arguments:
        system_message (str): System message to be sent to the API.
        user_messages (list): List of user messages to be sent to the API.

    Returns:
        (str): Prompt response from Xpert AI.
    """
    headers = {
        'Content-Type': 'application/json',
    }

    body = {
        'client_id': settings.XPERT_AI_CLIENT_ID,
        'system_message': system_message,
        'messages': user_messages,
    }

    response = requests.post(
        settings.XPERT_AI_API_V2,
        headers=headers,
        data=json.dumps(body),
        timeout=(CONNECT_TIMOUET_SECONDS, READ_TIMEOUT_SECONDS)
    )

    return response.json()[0].get('content')
