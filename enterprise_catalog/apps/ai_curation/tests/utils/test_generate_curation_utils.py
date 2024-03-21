"""
Tests for ai_curation app utils.
"""
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase

from enterprise_catalog.apps.ai_curation.utils.generate_curation_utils import (
    apply_keywords_filter,
    apply_programs_filter,
    apply_subjects_filter,
    apply_tfidf_filter,
    count_terms_in_description,
    generate_curation,
)


class TestUtils(TestCase):
    """
    Tests for the AI Curation generation curation utils functions.
    """

    def test_count_terms_in_description(self):
        """
        Validate count_terms_in_description function.
        """
        search_terms = ['python', 'data']
        assert count_terms_in_description(search_terms, 'Python for data science') == 2
        assert count_terms_in_description(search_terms, 'Test String') == 0
        assert count_terms_in_description([], 'Python for data science') == 0
        assert count_terms_in_description(search_terms, '') == 0

    def test_apply_subjects_filter(self):
        """
        Validate apply_subjects_filter function.
        """
        courses = [
            {'subjects': {'python', 'data'}},
            {'subjects': {'python', 'data', 'java'}},
            {'subjects': {'java'}},
        ]
        subjects = {'python'}
        assert apply_subjects_filter(courses, subjects) == [
            {'subjects': {'python', 'data'}},
            {'subjects': {'python', 'data', 'java'}},
        ]
        subjects = {'java'}
        assert apply_subjects_filter(courses, subjects) == [
            {'subjects': {'python', 'data', 'java'}},
            {'subjects': {'java'}},
        ]

        assert apply_subjects_filter(courses, set()) == []

    def test_apply_keywords_filter(self):
        """
        Validate apply_keywords_filter function.
        """
        courses = [
            {
                'description': 'Python for data science',
                'title': 'Python for data science',
                'skills': ['python', 'data engineering']
            },
            {
                'description': 'Test String',
                'title': 'Test String',
                'skills': []
            },
            {
                'description': 'Java for data science',
                'title': 'Java for data science',
                'skills': ['java']
            },
        ]
        keywords = ['python', 'data', 'data engineering']
        assert apply_keywords_filter(courses, keywords) == [
            {
                'description': 'Python for data science',
                'skills': ['python', 'data engineering'],
                'title': 'Python for data science'
            }
        ]

        # Test with kw_threshold
        keywords = ['java', 'data science']
        assert apply_keywords_filter(courses, keywords, kw_threshold=1) == [
            {
                'description': 'Java for data science',
                'title': 'Java for data science',
                'skills': ['java']
            }
        ]

        assert apply_keywords_filter(courses, ['java']) == []

    @patch('enterprise_catalog.apps.ai_curation.openai_client.client.chat.completions.create')
    @patch('enterprise_catalog.apps.ai_curation.utils.open_ai_utils.get_query_keywords')
    def test_apply_tfidf_filter(self, mock_get_query_keywords, mock_create):
        """
        Validate apply_tfidf_filter function.
        """
        mock_get_query_keywords.return_value = ['keyword1', 'keyword2']
        mock_create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps(['Learn data science with python'])))]
        )

        courses = [
            {
                'title': 'Python for data science',
                'skills': ['python', 'data science'],
                'short_description': 'How to use python for data science',
                'outcome': 'Learn data science with python'
            },
            {
                'title': 'Java for data science',
                'skills': ['java', 'data science'],
                'short_description': 'How to use java for data science',
                'outcome': 'Learn data science with java'
            },
            {
                'title': 'Software Engineering',
                'skills': ['C', 'C++', 'Rust'],
                'short_description': 'How to use C, C++, Rust for software engineering',
                'outcome': 'Learn software engineering with C, C++, Rust'
            },
        ]

        filtered_courses = apply_tfidf_filter('python data science', courses, tfidf_threshold=0.2)

        assert {c['title'] for c in filtered_courses} == {'Python for data science', 'Java for data science'}

    def test_apply_programs_filter(self):
        """
        Validate apply_programs_filter function.
        """
        courses = [
            {'program_titles': ['Python for data science', 'Java for data science']},
            {'program_titles': ['Python for data science']},
            {'program_titles': ['Java for data science']},
        ]
        programs = [
            {'title': 'Python for data science'},
            {'title': 'Java for data science'},
            {'title': 'Software Engineering'},
        ]

        assert apply_programs_filter(courses, programs) == [
            {'title': 'Python for data science'},
            {'title': 'Java for data science'},
        ]

        assert apply_programs_filter(courses, []) == []

    @patch('enterprise_catalog.apps.ai_curation.utils.generate_curation_utils.fetch_catalog_metadata_from_algolia')
    @patch('enterprise_catalog.apps.ai_curation.utils.generate_curation_utils.get_keywords_to_prose')
    @patch('enterprise_catalog.apps.ai_curation.utils.generate_curation_utils.get_filtered_subjects')
    @patch('enterprise_catalog.apps.ai_curation.utils.generate_curation_utils.get_query_keywords')
    def test_generate_curation(
        self, mock_get_query_keywords, mock_get_filtered_subjects, mock_get_keywords_to_prose,
        mock_fetch_catalog_metadata_from_algolia
    ):
        """
        Validate apply_tfidf_filter function.
        """
        mock_get_query_keywords.return_value = ['python', 'Data Science', 'Data Analysis', 'Statistics']
        mock_get_filtered_subjects.return_value = ['python', 'Computer Science', 'Data Analysis & Statistics']
        mock_get_keywords_to_prose.return_value = 'Python for data science data analysis and statistics'

        ocm_courses = [
            {
                'aggregation_key': 'course:MITx+19',
                'subjects': ["Python", "Computer Science", "Data Analysis & Statistics"],
                'content_type': 'course',
                'course_type': 'executive-education-2u',
                'skills': ['Business', 'Data Analysis', 'Data Science', 'Statistics'],
                'title': 'Python for data science',
                'short_description': 'Learn java for data science',
                'outcome': 'Learn data science with Python',
                'program_titles': []
            },
            {
                'aggregation_key': 'course:MITx+20',
                'subjects': ["Java", "C", 'C++'],
                'content_type': 'course',
                'course_type': 'verified',
                'skills': ['Programming Basics', 'Software Engineering'],
                'title': 'Programming Basics',
                'short_description': 'Learn Programming Basics',
                'outcome': 'Learn Programming Basics',
                'program_titles': []
            },
        ]

        exec_ed_courses = [
            {
                'aggregation_key': 'course:MITx+21',
                'subjects': ["Java", "Computer Science", "Data Analysis & Statistics", ],
                'content_type': 'course',
                'course_type': 'executive-education-2u',
                'skills': ['Java', 'Computer Science', 'Data Science'],
                'title': 'Java for data science',
                'short_description': 'Learn Java for data science',
                'program_titles': [],
                'outcome': 'Learn data science with Java',
            },
        ]
        mock_fetch_catalog_metadata_from_algolia.return_value = (
            ocm_courses,
            exec_ed_courses,
            [],
            ['Python', 'Data Analysis & Statistics', 'Computer Science', "Java", "C", "C++"]
        )

        result = generate_curation('python data science', 'Test Catalog')

        assert result['exec_ed_courses'] == []
        assert result['programs'] == []
        assert len(result['ocm_courses']) == 1
        assert result['ocm_courses'][0]['title'] == 'Python for data science'
        assert result['ocm_courses'][0]['aggregation_key'] == 'course:MITx+19'
