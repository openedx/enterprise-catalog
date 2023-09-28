""" Tests for catalog query filtering. """
import json
import logging

import ddt
import pytest
from django.test import TestCase

from enterprise_catalog.apps.catalog import filters


logger = logging.getLogger(__name__)


@ddt.ddt
class QueryFilterTests(TestCase):
    """
    Tests for filtering content metadata based on queries without elasticsearch
    """

    @ddt.data(
        {
            'raw_query_key': 'status',
            'expected_field': 'status',
            'expected_comparison_kind': 'exact'
        },
        {
            'raw_query_key': 'aggregation_key__exclude',
            'expected_field': 'aggregation_key',
            'expected_comparison_kind': 'exclude'
        },
    )
    @ddt.unpack
    def test_extract_field_and_comparison_kind(self, raw_query_key, expected_field, expected_comparison_kind):
        extracted_field, extracted_comparison_kind = filters.extract_field_and_comparison_kind(raw_query_key)
        self.assertEqual(extracted_field, expected_field)
        self.assertEqual(extracted_comparison_kind, expected_comparison_kind)

    @ddt.data(
        {'raw_query_key': 'status__deeper__field'},
        {'raw_query_key': 'aggregation_key__notreal'},
    )
    @ddt.unpack
    def test_invalid_extract_field_and_comparison_kind(self, raw_query_key):
        with pytest.raises(filters.QueryFilterException):
            filters.extract_field_and_comparison_kind(raw_query_key)

    def test_invalid_query_key(self):
        query_json = """
        {
            "content_type":"course",
            "aggregation_key__notreal":"course:MITx+6.002.3x"
        }
        """
        content_metadata_json = """
        {
            "aggregation_key": "course:MITx+6.002.3x",
            "content_type": "course"
        }
        """
        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        with pytest.raises(filters.QueryFilterException):
            filters.does_query_match_content(query_data, content_metadata)

    def test_matching_exclude_list(self):
        """
        A matching query using an exclude list
        """
        query_json = """
        {
            "content_type":"course",
            "aggregation_key__exclude":[
                "course:edX+DemoX.1",
                "course:MITx+6.002.1x",
                "course:MITx+6.002.2x",
                "course:MITx+6.002.3x"
            ]
        }
        """

        content_metadata_json = """
        {
            "aggregation_key": "course:StellenboschX+AMDP.1",
            "content_type": "course",
            "key": "StellenboschX+AMDP.1",
            "title": "Freedom of expression in the African media and digital policy landscape",
            "card_image_url": null,
            "image_url": "https://prod-discovery.edx-cdn.org/media/course/image/3a836be6-9d49-4a2b-99f3-05a38def865b-f7efe0348a13.small.jpeg"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert filters.does_query_match_content(query_data, content_metadata)

    def test_non_matching_exclude_list(self):
        """
        A non-matching query using an exclude list.
        """
        query_json = """
        {
            "content_type":"course",
            "aggregation_key__exclude":[
                "course:edX+DemoX.1",
                "course:MITx+6.002.1x",
                "course:MITx+6.002.2x",
                "course:MITx+6.002.3x"
            ]
        }
        """

        content_metadata_json = """
        {
            "aggregation_key": "course:MITx+6.002.3x",
            "content_type": "course"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert not filters.does_query_match_content(query_data, content_metadata)

    def test_non_matching_exclude_key(self):
        """
        A non-matching query using an exclude key.
        """
        query_json = """
        {
            "content_type":"course",
            "aggregation_key__exclude":"course:MITx+6.002.3x"
        }
        """

        content_metadata_json = """
        {
            "aggregation_key": "course:MITx+6.002.3x",
            "content_type": "course"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert not filters.does_query_match_content(query_data, content_metadata)

    def test_matching_missing_exclude(self):
        """
        A matching query where an exclude references a missing key (valid).
        """
        query_json = """
        {
            "content_type":"course",
            "aggregation_key__exclude":"course:MITx+6.002.3x"
        }
        """

        content_metadata_json = """
        {
            "content_type": "course"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert filters.does_query_match_content(query_data, content_metadata)

    def test_matching_not_key(self):
        """
        A matching query using a not key.
        """
        query_json = """
        {
            "content_type":"course",
            "aggregation_key__not":"course:MITx+6.002.3x"
        }
        """

        content_metadata_json = """
        {
            "aggregation_key": "course:edX+DemoX.1",
            "content_type": "course"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert filters.does_query_match_content(query_data, content_metadata)

    def test_non_matching_not_key(self):
        """
        A non-matching query using an not key.
        """
        query_json = """
        {
            "content_type":"course",
            "aggregation_key__not":"course:MITx+6.002.3x"
        }
        """

        content_metadata_json = """
        {
            "aggregation_key": "course:MITx+6.002.3x",
            "content_type": "course"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert not filters.does_query_match_content(query_data, content_metadata)

    def test_matching_lte_key(self):
        """
        A non-matching query using an lte key.
        """
        query_json = """
        {
            "content_type":"course",
            "first_enrollable_paid_seat_price__lte":"301"
        }
        """

        content_metadata_json = """
        {
            "first_enrollable_paid_seat_price": 301,
            "content_type": "course"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert filters.does_query_match_content(query_data, content_metadata)

    def test_non_matching_lte_key(self):
        """
        A non-matching query using an lte key.
        """
        query_json = """
        {
            "content_type":"course",
            "first_enrollable_paid_seat_price__lte":"301"
        }
        """

        content_metadata_json = """
        {
            "first_enrollable_paid_seat_price": 302,
            "content_type": "course"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert not filters.does_query_match_content(query_data, content_metadata)

    def test_matching_lt_key(self):
        """
        A non-matching query using an lt key.
        """
        query_json = """
        {
            "content_type":"course",
            "first_enrollable_paid_seat_price__lt":"301"
        }
        """

        content_metadata_json = """
        {
            "first_enrollable_paid_seat_price": 300,
            "content_type": "course"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert filters.does_query_match_content(query_data, content_metadata)

    def test_non_matching_lt_key(self):
        """
        A non-matching query using an lt key.
        """
        query_json = """
        {
            "content_type":"course",
            "first_enrollable_paid_seat_price__lt":"301"
        }
        """

        content_metadata_json = """
        {
            "first_enrollable_paid_seat_price": 301,
            "content_type": "course"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert not filters.does_query_match_content(query_data, content_metadata)

    def test_matching_gte_key(self):
        """
        A non-matching query using an gte key.
        """
        query_json = """
        {
            "content_type":"course",
            "first_enrollable_paid_seat_price__gte":"301"
        }
        """

        content_metadata_json = """
        {
            "first_enrollable_paid_seat_price": 301,
            "content_type": "course"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert filters.does_query_match_content(query_data, content_metadata)

    def test_non_matching_gte_key(self):
        """
        A non-matching query using an gte key.
        """
        query_json = """
        {
            "content_type":"course",
            "first_enrollable_paid_seat_price__gte":"301"
        }
        """

        content_metadata_json = """
        {
            "first_enrollable_paid_seat_price": 300,
            "content_type": "course"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert not filters.does_query_match_content(query_data, content_metadata)

    def test_matching_gt_key(self):
        """
        A non-matching query using an gt key.
        """
        query_json = """
        {
            "content_type":"course",
            "first_enrollable_paid_seat_price__gt":"300"
        }
        """

        content_metadata_json = """
        {
            "first_enrollable_paid_seat_price": 301,
            "content_type": "course"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert filters.does_query_match_content(query_data, content_metadata)

    def test_non_matching_gt_key(self):
        """
        A non-matching query using an gt key.
        """
        query_json = """
        {
            "content_type":"course",
            "first_enrollable_paid_seat_price__gt":"301"
        }
        """

        content_metadata_json = """
        {
            "first_enrollable_paid_seat_price": 301,
            "content_type": "course"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert not filters.does_query_match_content(query_data, content_metadata)

    def test_exact_list(self):
        """
        A matching query using a list exact key (aka include)
        """

        query_json = """
            {
                "partner":"edx",
                "status":[
                    "published",
                    "active"
                ],
                "content_type":[
                    "learnerpathway",
                    "course"
                ],
                "include_learner_pathways":"True",
                "aggregation_key":[
                    "learnerpathway:786bbe57-e06c-4eee-92f4-49087fccc200",
                    "learnerpathway:88a35038-d8d4-400e-a1dd-2d9e28d7740b",
                    "learnerpathway:01deb04e-8965-4a77-b6b3-30c3b1a6e81d",
                    "learnerpathway:bb233836-e6ae-4521-9727-91da454e0276",
                    "learnerpathway:5202ccd8-ea91-4da2-8a23-bcf2c612074d",
                    "learnerpathway:0610ee5a-2e78-4209-a47b-a2b6aae91a7f",
                    "learnerpathway:339994f8-1b3e-480c-9a92-a43e8f4db82f",
                    "learnerpathway:9e6607f2-d02e-4823-968d-02b0484a5a38",
                    "learnerpathway:77bca285-7891-46e1-ab17-d4d4ecb34f92",
                    "learnerpathway:46df6bad-6751-466a-9cbd-13cedab75403",
                    "learnerpathway:a4176150-e3a5-4229-8be6-7198d7f16221",
                    "learnerpathway:08d1928c-3a2a-4d0b-8cd6-566a722d3e4f",
                    "learnerpathway:c7fafa58-7b67-4c69-82fe-e4098fbeb48c",
                    "learnerpathway:5ad9fd53-93e1-46f9-8b17-ddc0102c1594"
                ]
            }
        """

        content_metadata_json = """
        {
            "status":"published",
            "partner":"edx",
            "content_type": "course",
            "include_learner_pathways":"True",
            "aggregation_key": "learnerpathway:786bbe57-e06c-4eee-92f4-49087fccc200"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert filters.does_query_match_content(query_data, content_metadata)

    def test_non_match_exact_list(self):
        """
        A matching query using a list exact key (aka include)
        """

        query_json = """
            {
                "partner":"edx",
                "status":[
                    "published",
                    "active"
                ],
                "content_type":[
                    "learnerpathway",
                    "course"
                ],
                "include_learner_pathways":"True",
                "aggregation_key":[
                    "learnerpathway:786bbe57-e06c-4eee-92f4-49087fccc200",
                    "learnerpathway:88a35038-d8d4-400e-a1dd-2d9e28d7740b",
                    "learnerpathway:01deb04e-8965-4a77-b6b3-30c3b1a6e81d",
                    "learnerpathway:bb233836-e6ae-4521-9727-91da454e0276",
                    "learnerpathway:5202ccd8-ea91-4da2-8a23-bcf2c612074d",
                    "learnerpathway:0610ee5a-2e78-4209-a47b-a2b6aae91a7f",
                    "learnerpathway:339994f8-1b3e-480c-9a92-a43e8f4db82f",
                    "learnerpathway:9e6607f2-d02e-4823-968d-02b0484a5a38",
                    "learnerpathway:77bca285-7891-46e1-ab17-d4d4ecb34f92",
                    "learnerpathway:46df6bad-6751-466a-9cbd-13cedab75403",
                    "learnerpathway:a4176150-e3a5-4229-8be6-7198d7f16221",
                    "learnerpathway:08d1928c-3a2a-4d0b-8cd6-566a722d3e4f",
                    "learnerpathway:c7fafa58-7b67-4c69-82fe-e4098fbeb48c",
                    "learnerpathway:5ad9fd53-93e1-46f9-8b17-ddc0102c1594"
                ]
            }
        """

        content_metadata_json = """
        {
            "status":"published",
            "partner":"edx",
            "content_type": "course",
            "include_learner_pathways":"True",
            "aggregation_key": "course:MITx+6.002.3x"
        }
        """

        query_data = json.loads(query_json)
        content_metadata = json.loads(content_metadata_json)
        assert not filters.does_query_match_content(query_data, content_metadata)
