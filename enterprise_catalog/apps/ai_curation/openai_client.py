import functools
import json
import logging
import re

import backoff
import requests
from django.conf import settings
from requests.exceptions import ConnectTimeout

from enterprise_catalog.apps.ai_curation.errors import (
    AICurationError,
    InvalidJSONResponseError,
)


LOGGER = logging.getLogger(__name__)


def api_error_handler(func):
    """
    Decorator that activates when the API continues to raise persistent errors even after retries.

    Raises a custom exception with the following attributes:
        - message (str): A user-friendly message
        - dev_message (str): The actual error message returned by the API
        - status_code (int): The actual error code returned by the API
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (ConnectionError, AICurationError) as ex:
            LOGGER.exception('[AI_CURATION] API Error: Prompt: [%s]', kwargs.get('messages'))
            # status_code attribute is not available for all exceptions, such as APIConnectionError and APITimeoutError
            status_code = getattr(ex, 'status_code', None)
            message = getattr(ex, 'message', None)
            raise AICurationError(dev_message=message, status_code=status_code) from ex
    return wrapper


@api_error_handler
@backoff.on_exception(
    backoff.expo,
    (ConnectTimeout, ConnectionError, InvalidJSONResponseError),
    max_tries=3,
)
def chat_completions(
    messages,
    response_format='json',
    system_message=settings.XPERT_AICURATION_SYSTEM_MESSAGE,
):
    """
    Pass message list to chat endpoint, as defined by the XPERT_AI_API_V2 setting.

    Args:
        messages (list): List of messages to send to the chat.completions endpoint
        response_format (str): Format of the response. Can be 'json' or 'text'
        system_message (str): System message to be used in the request
            Defaults to settings.XPERT_AICURATION_SYSTEM_MESSAGE

    Returns:
        <list, text>: The response from the chat.completions endpoint

    Throws:
        AICurationError: Raise an exception with the below attributes
            - message (str): A user-friendly message
            - dev_message (str): The actual error message returned by the API
            - status_code (int): The actual error code returned by the API
    """
    LOGGER.info('[AI_CURATION] [CHAT_COMPLETIONS] Prompt: [%s]', messages)

    headers = {'Content-Type': 'application/json'}
    message_list = []
    for message in messages:
        message_list.append({'role': 'user', 'content': message['content']})
    body = {
        'messages': message_list,
        'client_id': settings.XPERT_AI_CLIENT_ID,
        'system_message': system_message
    }
    response = requests.post(
        settings.XPERT_AI_API_V2,
        headers=headers,
        data=json.dumps(body),
        timeout=(
            settings.CHAT_COMPLETION_API_CONNECT_TIMEOUT,
            settings.CHAT_COMPLETION_API_READ_TIMEOUT
        )
    )
    LOGGER.info('[AI_CURATION] [CHAT_COMPLETIONS] Response: [%s]', response.json())
    try:
        response_content = response.json()[0].get('content')
        response_content = re.sub(r'```json\n?|```', '', response_content)
        if response_format == 'json':
            return json.loads(response_content)
        return response_content
    except json.decoder.JSONDecodeError as ex:
        LOGGER.error(
            '[AI_CURATION] Invalid JSON response received: Prompt: [%s], Response: [%s]',
            messages,
            response.json()
        )
        raise InvalidJSONResponseError('Invalid response received.') from ex
