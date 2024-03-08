"""
Utility functions for ai_curation app.
"""
from logging import getLogger

from django.conf import settings

from enterprise_catalog.apps.ai_curation.openai_client import chat_completions
from enterprise_catalog.apps.catalog.algolia_utils import (
    get_initialized_algolia_client,
)


LOGGER = getLogger(__name__)


def fetch_catalog_metadata_from_algolia(enterprise_catalog_query_title):
    """
    Returns the ocm_courses, exec_ed_courses, programs, subjects from the
    Algolia response for the provided catalog_query_title
    """
    algolia_client = get_initialized_algolia_client()
    search_options = {
        'facetFilters': [f'enterprise_catalog_query_titles:{enterprise_catalog_query_title}',],
        'attributesToRetrieve': ['aggregation_key', 'content_type', 'course_type', 'subjects',],
        'hitsPerPage': 100,
        'page': 0,
    }
    page = algolia_client.algolia_index.search('', search_options)
    ocm_courses = []
    exec_ed_courses = []
    programs = []
    subjects = set()

    while len(page['hits']) > 0:
        for hit in page.get('hits', []):
            if hit.get('content_type') == 'course':
                is_exec_ed = hit.get('course_type') == 'executive-education-2u'
                if is_exec_ed:
                    exec_ed_courses.append(hit.get('aggregation_key'))
                else:
                    ocm_courses.append(hit.get('aggregation_key'))
                subjects.update(hit.get('subjects'))
            elif hit.get('content_type') == 'program':
                programs.append(hit.get('aggregation_key'))
                subjects.update(hit.get('subjects'))

        search_options['page'] = search_options['page'] + 1
        page = algolia_client.algolia_index.search('', search_options)

    return ocm_courses, exec_ed_courses, programs, list(subjects)


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
