import functools
import json
import logging

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
):
    """
    Pass message list to chat endpoint, as defined by the CHAT_COMPLETION_API setting.

    Args:
        messages (list): List of messages to send to the chat.completions endpoint
        response_format (str): Format of the response. Can be 'json' or 'text'

    Returns:
        <list, text>: The response from the chat.completions endpoint

    Throws:
        AICurationError: Raise an exception with the below attributes
            - message (str): A user-friendly message
            - dev_message (str): The actual error message returned by the API
            - status_code (int): The actual error code returned by the API
    """
    LOGGER.info('[AI_CURATION] [CHAT_COMPLETIONS] Prompt: [%s]', messages)

    headers = {'Content-Type': 'application/json', 'x-api-key': settings.CHAT_COMPLETION_API_KEY}
    message_list = []
    for message in messages:
        message_list.append({'role': 'assistant', 'content': message['content']})
    body = {'message_list': message_list}
    response = requests.post(
        settings.CHAT_COMPLETION_API,
        headers=headers,
        data=json.dumps(body),
        timeout=(
            settings.CHAT_COMPLETION_API_CONNECT_TIMEOUT,
            settings.CHAT_COMPLETION_API_READ_TIMEOUT
        )
    )
    LOGGER.info('[AI_CURATION] [CHAT_COMPLETIONS] Response: [%s]', response.json())
    try:
        response_content = response.json().get('content')
        if response_format == 'json':
            return json.loads(response_content)
        return json.loads(response_content)[0]
    except json.decoder.JSONDecodeError as ex:
        LOGGER.error(
            '[AI_CURATION] Invalid JSON response received: Prompt: [%s], Response: [%s]',
            messages,
            response.json()
        )
        raise InvalidJSONResponseError('Invalid response received.') from ex
