import functools
import logging

import backoff
import simplejson
from django.conf import settings
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from enterprise_catalog.apps.ai_curation.errors import (
    AICurationError,
    InvalidJSONResponseError,
)


LOGGER = logging.getLogger(__name__)

client = OpenAI(api_key=settings.OPENAI_API_KEY)


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
        except (APIError, AICurationError) as ex:
            LOGGER.exception('[AI_CURATION] API Error: Prompt: [%s]', kwargs.get('messages'))
            # status_code attribute is not available for all exceptions, such as APIConnectionError and APITimeoutError
            status_code = getattr(ex, 'status_code', None)
            message = getattr(ex, 'message', None)
            raise AICurationError(dev_message=message, status_code=status_code) from ex
    return wrapper


@api_error_handler
@backoff.on_exception(
    backoff.expo,
    (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError, InvalidJSONResponseError),
    max_tries=3,
)
def chat_completions(
    messages,
    response_format='json',
    response_type=list,
    model="gpt-4",
    temperature=0.3,
    max_tokens=500,
):
    """
    Get a response from the chat.completions endpoint

    Args:
        messages (list): List of messages to send to the chat.completions endpoint
        response_format (str): Format of the response. Can be 'json' or 'text'
        response_type (any): Expected type of the response. For now we only expect `list`
        model (str): Model to use for the completion
        temperature (number): Make model output more focused and deterministic
        max_tokens (int): Maximum number of tokens that can be generated in the chat completion

    Returns:
        <list, text>: The response from the chat.completions endpoint

    Throws:
        AICurationError: Raise an exception with the below attributes
            - message (str): A user-friendly message
            - dev_message (str): The actual error message returned by the API
            - status_code (int): The actual error code returned by the API
    """
    LOGGER.info('[AI_CURATION] [CHAT_COMPLETIONS] Prompt: [%s]', messages)
    response = client.chat.completions.create(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    LOGGER.info('[AI_CURATION] [CHAT_COMPLETIONS] Response: [%s]', response)
    response_content = response.choices[0].message.content

    if response_format == 'json':
        try:
            json_response = simplejson.loads(response_content)
            if isinstance(json_response, response_type):
                return json_response
            LOGGER.error(
                '[AI_CURATION] JSON response received but response type is incorrect: Prompt: [%s], Response: [%s]',
                messages,
                response
            )
            raise InvalidJSONResponseError('Invalid response type received from chatgpt')
        except simplejson.errors.JSONDecodeError as ex:
            LOGGER.error(
                '[AI_CURATION] Invalid JSON response received from chatgpt: Prompt: [%s], Response: [%s]',
                messages,
                response
            )
            raise InvalidJSONResponseError('Invalid JSON response received from chatgpt') from ex

    return response_content
