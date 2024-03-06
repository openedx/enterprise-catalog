"""
Utility functions for ai_curation app.
"""
from logging import getLogger

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
