from unittest import mock
from uuid import uuid4

import ddt
from django.test import TestCase

from enterprise_catalog.apps.catalog.algolia_utils import (
    ALGOLIA_INDEX_SETTINGS,
    _should_index_course,
    get_advertised_course_run,
    get_course_card_image_url,
    get_course_partners,
    get_course_subjects,
    get_initialized_algolia_client,
)
from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)


ADVERTISED_COURSE_RUN_UUID = uuid4()


@ddt.ddt
class AlgoliaUtilsTests(TestCase):
    """
    Tests for Algolia utils.
    """

    @ddt.data(
        {'expected_result': False, 'has_advertised_course_run': False},
        {'expected_result': False, 'has_owners': False},
        {'expected_result': False, 'has_url_slug': False},
        {'expected_result': False, 'advertised_course_run_hidden': True},
        {'expected_result': True},
    )
    @ddt.unpack
    def test_should_index_course(
        self,
        expected_result,
        has_advertised_course_run=True,
        has_owners=True,
        has_url_slug=True,
        advertised_course_run_hidden=False,
    ):
        """
        Verify that only a course that has a non-hidden advertised course run, at least one owner, and a marketing slug
        is marked as indexable.
        """
        advertised_course_run_uuid = uuid4()
        course_run_uuid = advertised_course_run_uuid if has_advertised_course_run else uuid4()
        owners = [{'name': 'edX'}] if has_owners else []
        url_slug = 'test-slug' if has_url_slug else ''
        json_metadata = {
            'advertised_course_run_uuid': advertised_course_run_uuid,
            'course_runs': [
                {
                    'hidden': advertised_course_run_hidden,
                    'uuid': course_run_uuid,
                },
            ],
            'owners': owners,
            'url_slug': url_slug,
        }
        course_metadata = ContentMetadataFactory.create(
            content_type=COURSE,
            json_metadata=json_metadata,
        )
        assert _should_index_course(course_metadata) is expected_result

    @ddt.data(
        (
            {'original_image': {'src': 'https://fake.image'}},
            'https://fake.image',
        ),
        (
            {'original_image': None},
            None,
        ),
        (
            {'original_image': {}},
            None,
        ),
    )
    @ddt.unpack
    def test_get_course_card_image_url(self, course_metadata, expected_image_url):
        """
        Assert get_course_card_image_url returns the expected course card image url.
        """
        card_image_url = get_course_card_image_url(course_metadata)
        assert card_image_url == expected_image_url

    @ddt.data(
        (
            {'owners': None},
            [],
        ),
        (
            {'owners': []},
            [],
        ),
        (
            {
                'owners': [
                    {
                        'name': 'Test Org Name',
                        'logo_image_url': 'https://fake.image1',
                        'ignored_attr': None,
                    },
                    {
                        'name': 'Another Org Name',
                        'logo_image_url': 'https://fake.image2',
                        'ignored_attr': None,
                    },
                ]
            },
            [
                {
                    'name': 'Test Org Name',
                    'logo_image_url': 'https://fake.image1',
                },
                {
                    'name': 'Another Org Name',
                    'logo_image_url': 'https://fake.image2',
                },
            ],
        ),
    )
    @ddt.unpack
    def test_get_course_partners(self, course_metadata, expected_partners):
        """
        Assert get_course_partners returns the expected partner metadata for various inputs.
        """
        course_partners = get_course_partners(course_metadata)
        assert course_partners == expected_partners

    @ddt.data(
        (
            {'subjects': ['Computer Science', 'Communication']},
            ['Computer Science', 'Communication'],
        ),
        (
            {
                'subjects': [
                    {'name': 'Computer Science'},
                    {'name': 'Communication'},
                ],
            },
            ['Computer Science', 'Communication'],
        ),
        (
            {'subjects': None},
            [],
        ),
        (
            {'subjects': []},
            [],
        ),
    )
    @ddt.unpack
    def test_get_course_subjects(self, course_metadata, expected_subjects):
        """
        Assert get_course_subjects is flexible enough to support both a list of strings
        and a list of dictionaries.
        """
        course_subjects = get_course_subjects(course_metadata)
        assert sorted(course_subjects) == sorted(expected_subjects)

    @ddt.data(
        (
            {
                'course_runs': [{
                    'key': 'course-v1:org+course+1T2021',
                    'uuid': ADVERTISED_COURSE_RUN_UUID,
                    'pacing_type': 'instructor_paced',
                    'start': '2013-10-16T14:00:00Z',
                    'end': '2014-10-16T14:00:00Z',
                }],
                'advertised_course_run_uuid': ADVERTISED_COURSE_RUN_UUID
            },
            {
                'key': 'course-v1:org+course+1T2021',
                'pacing_type': 'instructor_paced',
                'start': '2013-10-16T14:00:00Z',
                'end': '2014-10-16T14:00:00Z',
            }
        )
    )
    @ddt.unpack
    def test_get_advertised_course_run(self, searchable_course, expected_course_run):
        """
        Assert get_advertised_course_runs fetches just enough info about advertised course run
        """
        advertised_course_run = get_advertised_course_run(searchable_course)
        assert advertised_course_run == expected_course_run

    @mock.patch('enterprise_catalog.apps.catalog.algolia_utils.AlgoliaSearchClient')
    def test_get_initialized_algolia_client(self, mock_search_client):
        """
        Verify that `get_initialized_algolia_client` makes calls to initialize the index and configure index settings.
        """
        get_initialized_algolia_client()

        mock_search_client.return_value.init_index.assert_called_once()
        mock_search_client.return_value.set_index_settings.assert_called_once_with(ALGOLIA_INDEX_SETTINGS)
