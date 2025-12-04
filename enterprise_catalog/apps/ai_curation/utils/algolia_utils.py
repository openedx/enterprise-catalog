"""
Utility functions for Algolia.
"""
from dataclasses import dataclass

from django.utils.html import strip_tags


@dataclass
class ContentType:
    """
    Dataclass for the content types.
    """
    COURSE = 'course'
    PROGRAM = 'program'


@dataclass
class CourseType:
    """
    Dataclass for the course types.
    """
    EXEC_ED = 'executive-education-2u'


def extract_course_data(hit: dict):
    """
    Extract course information from the Algolia hit.
    """
    return {
        'key': hit.get('key'),
        'aggregation_key': hit.get('aggregation_key'),
        'content_type': hit.get('content_type'),
        'course_type': hit.get('course_type'),
        'title': hit.get('title', ''),
        'short_description': strip_tags(hit.get('full_description', '')),
        'full_description': strip_tags(hit.get('full_description', '')),
        'outcome': strip_tags(hit.get('outcome', '')),
        'program_titles': hit.get('program_titles', []),
        'skills': hit.get('skill_names', []),
        'subjects': hit.get('subjects', []),
        'availability': hit.get('availability', [])
    }


def extract_program_data(hit: dict):
    """
    Extract program information from the Algolia hit.
    """
    return {
        'aggregation_key': hit.get('aggregation_key'),
        'title': hit.get('title', ''),
        'short_description': hit.get('full_description', ''),
        'skills': hit.get('skill_names', []),
        'subjects': hit.get('subjects', []),
    }


def get_initialized_algolia_client():
    """
    Initializes and returns an Algolia client for updating search indices
    """
    from enterprise_catalog.apps.api_client.algolia import \
        AlgoliaSearchClient  # pylint: disable=import-outside-toplevel
    algolia_client = AlgoliaSearchClient()
    algolia_client.init_index()
    return algolia_client


def fetch_catalog_metadata_from_algolia(enterprise_catalog_query_title: str):
    """
    Returns the ocm_courses, exec_ed_courses, programs, subjects from the
    Algolia response for the provided catalog_query_title
    """
    algolia_client = get_initialized_algolia_client()
    search_options = {
        'facetFilters': [
            [
                'availability:Available Now',
                'availability:Starting Soon',
                'availability:Upcoming'
            ],
            [
                f'enterprise_catalog_query_titles:{enterprise_catalog_query_title}'
            ]
        ],
        'filters': 'learning_type:course OR learning_type:program OR learning_type:"Executive Education"',
        'attributesToRetrieve': [
            'key',
            'aggregation_key',
            'content_type',
            'course_type',
            'availability',
            'title',
            'short_description',
            'full_description',
            'outcome',
            'program_titles',
            'skill_names',
            'subjects',
        ],
        'facetingAfterDistinct': True,
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
            if hit.get('content_type') == ContentType.COURSE:
                if hit.get('course_type') == CourseType.EXEC_ED:
                    exec_ed_courses.append(
                        extract_course_data(hit)
                    )
                else:
                    ocm_courses.append(
                        extract_course_data(hit)
                    )
                subjects.update(hit.get('subjects'))
            elif hit.get('content_type') == ContentType.PROGRAM:
                programs.append(
                    extract_program_data(hit)
                )
                subjects.update(hit.get('subjects'))

        search_options['page'] = search_options['page'] + 1
        page = algolia_client.algolia_index.search('', search_options)

    return ocm_courses, exec_ed_courses, programs, list(subjects)
