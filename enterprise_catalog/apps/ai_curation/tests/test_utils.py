"""
Tests for the views of the ai_curation app.
"""
from unittest import mock

from django.test import TestCase

from enterprise_catalog.apps.ai_curation.utils import (
    fetch_catalog_metadata_from_algolia,
)


class TestUtils(TestCase):
    """
    Tests for the AI Curation util functions.
    """
    mock_algolia_hits = {'hits': [
        {
            'aggregation_key': 'course:MITx+19',
            'subjects': ["Business & Management", "Computer Science", "Data Analysis & Statistics"],
            'content_type': 'course',
            'course_type': 'executive-education-2u',
            'objectID': 'course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf9-catalog-query-uuids-0'
        },
        {
            'aggregation_key': 'course:MITx+20',
            'subjects': ["Business & Management", "Economics & Finance", "Philosophy & Ethics", "Engineering"],
            'content_type': 'course',
            'course_type': 'verified',
            'objectID': 'course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf7-catalog-query-uuids-0'
        },
        {
            'aggregation_key': 'program:MITx+21',
            'subjects': ["Computer Science", "Engineering", "Electronics"],
            'content_type': 'program',
            'objectID': 'course-3543aa4e-3c64-4d9a-a343-5d5eda1dacf7-catalog-query-uuids-0'
        }
    ]}

    @mock.patch('enterprise_catalog.apps.ai_curation.utils.get_initialized_algolia_client')
    def test_fetch_catalog_metadata_from_algolia(self, mock_algolia_client):
        """
        Verify that the catalog metadata from algolia is fetched correctly.
        """
        mock_algolia_client.return_value.algolia_index.search.side_effect = [self.mock_algolia_hits, {'hits': []}]
        ocm_courses, exec_ed_courses, programs, subjects = fetch_catalog_metadata_from_algolia('test_query_title')
        self.assertEqual(ocm_courses, ['course:MITx+20'])
        self.assertEqual(exec_ed_courses, ['course:MITx+19'])
        self.assertEqual(programs, ['program:MITx+21'])
        self.assertEqual(sorted(subjects), ["Business & Management", "Computer Science",
                                            "Data Analysis & Statistics", "Economics & Finance",
                                            "Electronics", "Engineering", "Philosophy & Ethics"])
