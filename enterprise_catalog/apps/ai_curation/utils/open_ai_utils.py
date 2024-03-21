"""
Utility functions for communication with OpenAI.
"""
from logging import getLogger

from django.conf import settings

from enterprise_catalog.apps.ai_curation.openai_client import chat_completions


LOGGER = getLogger(__name__)


def get_filtered_subjects(query, subjects):
    """
    Find the top 2-3 most relevant subjects based on the query

    Args:
        query (str): Search query given by the user
        subjects (list): The list of available course subjects

    Returns:
        list: Top 2-3 most relevant subjects
    """
    content = settings.AI_CURATION_FILTER_SUBJECTS_PROMPT.format(query=query, subjects=subjects)
    messages = [
        {
            'role': 'system',
            'content': content
        }
    ]
    LOGGER.info('[AI_CURATION] Filtering subjects. Prompt: [%s]', messages)
    filtered_subjects = chat_completions(messages=messages)
    LOGGER.info('[AI_CURATION] Filtering subjects. Response: [%s]', filtered_subjects)
    return filtered_subjects


def get_query_keywords(query):
    """
    Generate a list of 4-8 single word keywords to transform the query into relevant subjects and skills

    Args:
        query (str): Search query given by the user

    Returns:
        list: 4-8 single word keywords
    """
    content = settings.AI_CURATION_QUERY_TO_KEYWORDS_PROMPT.format(query=query)
    messages = [
        {
            'role': 'system',
            'content': content
        }
    ]
    LOGGER.info('[AI_CURATION] Generating keywords. Prompt: [%s]', messages)
    keywords = chat_completions(messages=messages)
    LOGGER.info('[AI_CURATION] Generating keywords. Response: [%s]', keywords)
    return keywords


def get_keywords_to_prose(query):
    """
    Get an expanded version of the query, roughly 100 words in length, stuffed with the keywords

    Args:
        query (str): Search query given by the user

    Returns:
        str: Expanded version of the query
    """
    keywords = get_query_keywords(query)
    content = settings.AI_CURATION_KEYWORDS_TO_PROSE_PROMPT.format(query=query, keywords=keywords)
    messages = [
        {
            'role': 'system',
            'content': content
        }
    ]
    LOGGER.info('[AI_CURATION] Generating prose from keywords. Prompt: [%s]', messages)
    keywords_to_prose = chat_completions(messages=messages)
    LOGGER.info('[AI_CURATION] Generating prose from keywords. Response: [%s]', keywords_to_prose)
    # keywords_to_prose will always be a list - empty or with a valid prose
    if keywords_to_prose:
        return keywords_to_prose[0]

    return ''
