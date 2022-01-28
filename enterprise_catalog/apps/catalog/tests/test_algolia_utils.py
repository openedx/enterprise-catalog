from unittest import mock
from uuid import uuid4

import ddt
from django.test import TestCase

from enterprise_catalog.apps.catalog.algolia_utils import (
    ALGOLIA_INDEX_SETTINGS,
    _should_index_course,
    configure_algolia_index,
    get_advertised_course_run,
    get_course_availability,
    get_course_card_image_url,
    get_course_language,
    get_course_partners,
    get_course_program_titles,
    get_course_program_types,
    get_course_skill_names,
    get_course_subjects,
    get_initialized_algolia_client,
    get_program_availability,
    get_program_banner_image_url,
    get_program_learning_items,
    get_program_level_type,
    get_program_partners,
    get_program_prices,
    get_program_skill_names,
    get_program_subjects,
    get_program_title,
    get_program_type,
    get_upcoming_course_runs,
)
from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)


ADVERTISED_COURSE_RUN_UUID = uuid4()
FUTURE_COURSE_RUN_UUID_1 = uuid4()
FUTURE_COURSE_RUN_UUID_2 = uuid4()


@ddt.ddt
class AlgoliaUtilsTests(TestCase):
    """
    Tests for Algolia utils.
    """

    @ddt.data(
        {'expected_result': False, 'has_advertised_course_run': False},
        {'expected_result': False, 'has_owners': False},
        {'expected_result': False, 'advertised_course_run_hidden': True},
        {'expected_result': False, 'advertised_course_run_status': 'unpublished'},
        {'expected_result': False, 'is_enrollable': False},
        {'expected_result': False, 'is_marketable': False},
    )
    @ddt.unpack
    def test_should_index_course(
        self,
        expected_result,
        has_advertised_course_run=True,
        has_owners=True,
        advertised_course_run_hidden=False,
        advertised_course_run_status='published',
        is_enrollable=True,
        is_marketable=True,
    ):
        """
        Verify that only a course that has a non-hidden advertised course run, at least one owner, and a marketing slug
        is marked as indexable.
        """
        advertised_course_run_uuid = uuid4()
        course_run_uuid = advertised_course_run_uuid if has_advertised_course_run else uuid4()
        owners = [{'name': 'edX'}] if has_owners else []
        json_metadata = {
            'advertised_course_run_uuid': advertised_course_run_uuid,
            'course_runs': [
                {
                    'hidden': advertised_course_run_hidden,
                    'uuid': course_run_uuid,
                    'status': advertised_course_run_status,
                    'is_enrollable': is_enrollable,
                    'is_marketable': is_marketable,
                },
            ],
            'owners': owners,
        }
        course_metadata = ContentMetadataFactory.create(
            content_type=COURSE,
            json_metadata=json_metadata,
        )
        assert _should_index_course(course_metadata) is expected_result

    @ddt.data(
        (
            {
                'course_runs': [{
                    'uuid': ADVERTISED_COURSE_RUN_UUID,
                    'content_language_search_facet_name': 'English',
                }],
                'advertised_course_run_uuid': ADVERTISED_COURSE_RUN_UUID,
            },
            'English',
        ),
        (
            {
                'course_runs': [{
                    'uuid': ADVERTISED_COURSE_RUN_UUID,
                    'content_language_search_facet_name': 'Chinese - Mandarin',
                }],
                'advertised_course_run_uuid': ADVERTISED_COURSE_RUN_UUID,
            },
            'Chinese - Mandarin',
        ),
        (
            {
                'course_runs': [{
                    'uuid': ADVERTISED_COURSE_RUN_UUID,
                    'content_language_search_facet_name': None,
                }],
                'advertised_course_run_uuid': ADVERTISED_COURSE_RUN_UUID,
            },
            None,
        ),
        (
            {
                'advertised_course_run_uuid': None,
            },
            None,
        ),
    )
    @ddt.unpack
    def test_get_course_language(self, course_metadata, expected_course_language):
        """
        Assert correct parsing of ``content_language`` for a given course run.
        """
        course_language = get_course_language(course_metadata)
        assert course_language == expected_course_language

    @ddt.data(
        (
            {'image_url': 'https://fake.image'},
            'https://fake.image',
        ),
        (
            {'image_url': None},
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
                'upgrade_deadline': 32503680000.0,
            },
        ),
        (
            {
                'course_runs': [{
                    'uuid': uuid4(),
                }],
                'advertised_course_run_uuid': ADVERTISED_COURSE_RUN_UUID
            },
            None,
        ),
        (
            {
                'course_runs': [{
                    'key': 'course-v1:org+course+1T2021',
                    'uuid': ADVERTISED_COURSE_RUN_UUID,
                    'pacing_type': 'instructor_paced',
                    'start': '2013-10-16T14:00:00Z',
                    'end': '2014-10-16T14:00:00Z',
                    'seats': [{
                        'type': 'audit',
                        'upgrade_deadline': None,
                    }, {
                        'type': 'verified',
                        'upgrade_deadline': '2015-01-04T15:52:00Z',
                    }],
                }],
                'advertised_course_run_uuid': ADVERTISED_COURSE_RUN_UUID
            },
            {
                'key': 'course-v1:org+course+1T2021',
                'pacing_type': 'instructor_paced',
                'start': '2013-10-16T14:00:00Z',
                'end': '2014-10-16T14:00:00Z',
                'upgrade_deadline': 1420386720.0,
            }
        ),
        (
            {
                'course_runs': [{
                    'key': 'course-v1:org+course+1T2021',
                    'uuid': ADVERTISED_COURSE_RUN_UUID,
                    'pacing_type': 'instructor_paced',
                    'start': '2013-10-16T14:00:00Z',
                    'end': '2014-10-16T14:00:00Z',
                    'seats': [{
                        'type': 'verified',
                        'upgrade_deadline': None,
                    }],
                }],
                'advertised_course_run_uuid': ADVERTISED_COURSE_RUN_UUID
            },
            {
                'key': 'course-v1:org+course+1T2021',
                'pacing_type': 'instructor_paced',
                'start': '2013-10-16T14:00:00Z',
                'end': '2014-10-16T14:00:00Z',
                'upgrade_deadline': 32503680000.0,
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

    @ddt.data(
        (
            {
                'course_runs': [
                    {
                        'key': 'course-v1:org+course+1T2021',
                        'uuid': ADVERTISED_COURSE_RUN_UUID,
                        'pacing_type': 'instructor_paced',
                        'status': 'published',
                        'is_enrollable': True,
                        'is_marketable': True,
                        'availability': 'Current'
                    },
                    {
                        'key': 'course-v1:org+course+1T2021',
                        'uuid': FUTURE_COURSE_RUN_UUID_1,
                        'pacing_type': 'instructor_paced',
                        'status': 'published',
                        'is_enrollable': True,
                        'is_marketable': True,
                        'availability': 'Upcoming'
                    },
                    {
                        'key': 'course-v1:org+course+1T2021',
                        'uuid': FUTURE_COURSE_RUN_UUID_1,
                        'pacing_type': 'instructor_paced',
                        'status': 'unpublished',
                        'is_enrollable': True,
                        'is_marketable': True,
                        'availability': 'Starting Soon'
                    }
                ],
                'advertised_course_run_uuid': ADVERTISED_COURSE_RUN_UUID
            },
            1,
        ),
    )
    @ddt.unpack
    def test_get_upcoming_course_runs(self, searchable_course, expected_course_runs):
        """
        Assert get_advertised_course_runs fetches just enough info about advertised course run
        """
        upcoming_course_runs = get_upcoming_course_runs(searchable_course)
        assert upcoming_course_runs == expected_course_runs

    @ddt.data(
        (
            {
                'course_runs': [{
                    'status': 'published',
                    'is_enrollable': True,
                    'is_marketable': True,
                    'availability': 'Current'
                }]
            },
            ['Available Now'],
        ),
        (
            {
                'course_runs': [{
                    'status': 'published',
                    'is_enrollable': True,
                    'is_marketable': True,
                    'availability': 'Upcoming'
                }]
            },
            ['Upcoming'],
        ),
        (
            {
                'course_runs': [{
                    'status': 'published',
                    'is_enrollable': True,
                    'is_marketable': True,
                    'availability': 'Archived'
                }]
            },
            ['Archived'],
        ),
        (
            {
                'course_runs': [{
                    'status': 'published',
                    'is_enrollable': True,
                    'is_marketable': True,
                    'availability': 'Starting Soon'
                }]
            },
            ['Starting Soon'],
        ),
        (
            {
                'course_runs': [{
                    'status': 'published',
                    'is_enrollable': True,
                    'is_marketable': True,
                }]
            },
            ['Archived'],
        ),
    )
    @ddt.unpack
    def test_get_course_availability(self, course_metadata, expected_availability):
        """
        Assert the course availability is parsed and formatted correctly.
        """
        availability = get_course_availability(course_metadata)
        assert availability == expected_availability

    @ddt.data(
        (
            {'programs': [{'type': 'Professional Certificate'}]},
            ['Professional Certificate'],
        ),
        (
            {'programs': [{'title': 'Synchronicity'}]},
            [],
        ),
        (
            {'programs': [{'type': '', 'title': 'Yes'}]},
            [],
        ),
    )
    @ddt.unpack
    def test_get_course_program_types(self, course_metadata, expected_program_types):
        """
        Assert that the list of program types associated with a course is properly parsed and formatted.
        """
        program_types = get_course_program_types(course_metadata)
        assert program_types == expected_program_types

    @ddt.data(
        (
            {'expected_learning_items': ['a', 'b', 'x']},
            ['a', 'b', 'x'],
        ),
        (
            {},
            [],
        ),
    )
    @ddt.unpack
    def test_get_course_learning_items(self, program_metadata, expected_program_types):
        """
        Assert that the list of program types associated with a course is properly parsed and formatted.
        """
        learning_items = get_program_learning_items(program_metadata)
        assert learning_items == expected_program_types

    @ddt.data(
        (
            {'programs': [{'type': 'Masters', 'title': 'Reverse Psychology'}]},
            ['Reverse Psychology'],
        ),
        (
            {'programs': [{'type': 'Professional Certificate'}]},
            [],
        ),
        (
            {'programs': [{'type': 'Professional Certificate', 'title': ''}]},
            [],
        ),
    )
    @ddt.unpack
    def test_get_course_program_titles(self, course_metadata, expected_program_titles):
        """
        Assert that the list of program titles associated with a course is properly parsed and formatted.
        """
        program_titles = get_course_program_titles(course_metadata)
        assert program_titles == expected_program_titles

    @ddt.data(
        (
            {'skill_names': ['Python', 'Programming']},
            ['Python', 'Programming'],
        ),
    )
    @ddt.unpack
    def test_get_course_skill_names(self, course_metadata, expected_skill_names):
        """
        Assert the list of skill names associated with a course is properly parsed.
        """
        skill_names = get_course_skill_names(course_metadata)
        assert sorted(skill_names) == sorted(expected_skill_names)

    @mock.patch('enterprise_catalog.apps.catalog.algolia_utils.AlgoliaSearchClient')
    def test_get_initialized_algolia_client(self, mock_search_client):
        """
        Verify that `get_initialized_algolia_client` makes calls to initialize the index and configure index settings.
        """
        get_initialized_algolia_client()
        mock_search_client.return_value.init_index.assert_called_once()

    @mock.patch('enterprise_catalog.apps.catalog.algolia_utils.AlgoliaSearchClient')
    def test_configure_algolia_index(self, mock_search_client):
        """
        Verify that `configure_algolia_index_settings` makes call to configure index settings.
        """
        algolia_client = get_initialized_algolia_client()
        configure_algolia_index(algolia_client)
        mock_search_client.return_value.set_index_settings.assert_called_once_with(ALGOLIA_INDEX_SETTINGS)

    @ddt.data(
        (
            {'courses': [{'key': 'program_course_key'}]},
            {'skill_names': ['Python', 'Programming']},
            ['Python', 'Programming'],
        ),
    )
    @ddt.unpack
    def test_get_program_skill_names(self, program_metadata, course_metadata, expected_skill_names):
        """
        Assert that the list of skill names associated with a program is properly parsed.
        """
        ContentMetadataFactory.create(
            content_key=program_metadata['courses'][0]['key'],
            content_type=COURSE,
            json_metadata=course_metadata,
        )
        skill_names = get_program_skill_names(program_metadata)
        self.assertEqual(sorted(skill_names), sorted(expected_skill_names))

    @ddt.data(
        (
            {'type': 'Professional Certificate'},
            'Professional Certificate',
        ),
    )
    @ddt.unpack
    def test_get_program_type(self, program_metadata, expected_type):
        """
        Assert that the type associated with a program is properly parsed.
        """
        program_type = get_program_type(program_metadata)
        self.assertEqual(expected_type, program_type)

    @ddt.data(
        (
            {'price_ranges': [{'currency': 'USD', 'total': 169}, {'currency': 'GBP', 'total': 1}]},
            {'usd_total': 169},
        ),
    )
    @ddt.unpack
    def test_get_program_prices(self, program_metadata, expected_type):
        """
        Assert that the prices associated with a program is properly parsed.
        """
        program_prices = get_program_prices(program_metadata)
        self.assertEqual(expected_type, program_prices)

    @ddt.data(
        (
            {'banner_image': {'large': {'url': 'https://test'}}},
            'https://test',
        ),
        (
            {'banner_image': {}},
            None,
        ),
        (
            {'banner_image': {'large': {}}},
            None,
        ),
    )
    @ddt.unpack
    def test_get_program_banner_image(self, program_metadata, expected_type):
        """
        Assert that the prices associated with a program is properly parsed.
        """
        image_url = get_program_banner_image_url(program_metadata)
        self.assertEqual(expected_type, image_url)

    @ddt.data(
        (
            {'title': 'edX Demonstration Program'},
            'edX Demonstration Program',
        ),
    )
    @ddt.unpack
    def test_get_program_title(self, program_metadata, expected_title):
        """
        Assert that the title associated with a program is properly parsed.
        """
        program_title = get_program_title(program_metadata)
        self.assertEqual(expected_title, program_title)

    @ddt.data(
        (
            {'courses': [{
                'course_runs': [{
                    'status': 'published',
                    'is_enrollable': True,
                    'is_marketable': True,
                    'availability': 'Current'
                }]
            }]},
            ['Available Now'],
        ),
        (
            {'courses': [{
                'course_runs': [{
                    'status': 'published',
                    'is_enrollable': True,
                    'is_marketable': True,
                    'availability': 'Upcoming'
                }]
            }]},
            ['Upcoming'],
        ),
        (
            {'courses': [{
                'course_runs': [{
                    'status': 'published',
                    'is_enrollable': True,
                    'is_marketable': True,
                    'availability': 'Archived'
                }]
            }]},
            ['Archived'],
        ),
        (
            {'courses': [{
                'course_runs': [{
                    'status': 'published',
                    'is_enrollable': True,
                    'is_marketable': True,
                    'availability': 'Starting Soon'
                }]
            }]},
            ['Starting Soon'],
        ),
        (
            {'courses': [{
                'course_runs': [{
                    'status': 'published',
                    'is_enrollable': True,
                    'is_marketable': True,
                }]
            }]},
            ['Archived'],
        ),
        (
            {
                'type': 'Masters',
                'courses': [{
                    'course_runs': [{
                        'status': 'published',
                        'is_enrollable': True,
                        'is_marketable': True,
                        'availability': 'Archived'
                    }]
                }]
            },
            ['Available now'],
        ),
    )
    @ddt.unpack
    def test_get_program_availability(self, program_metadata, expected_availability):
        """
        Assert that the Availability associated with a program is properly parsed.
        """
        program_availability = get_program_availability(program_metadata)
        self.assertEqual(expected_availability, program_availability)

    @ddt.data(
        (
            {'courses': [{'owners': None}]},
            [],
        ),
        (
            {'courses': [{'owners': []}]},
            [],
        ),
        (
            {'courses': [{
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
            }]},
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
    def test_get_program_partners(self, program_metadata, expected_partners):
        """
        Assert that the Partners associated with a program are properly parsed.
        """
        program_partners = get_program_partners(program_metadata)
        self.assertEqual(expected_partners, program_partners)

    @ddt.data(
        (
            {'courses': [{'key': 'program_course_key'}]},
            {'subjects': ['Computer Science', 'Communication']},
            ['Computer Science', 'Communication'],
        ),
        (
            {'courses': [{'key': 'program_course_key'}]},
            {'subjects': [
                {'name': 'Computer Science'},
                {'name': 'Communication'},
            ]},
            ['Computer Science', 'Communication'],
        ),
        (
            {'courses': [{'key': 'program_course_key'}]},
            {'subjects': None},
            [],
        ),
        (
            {'courses': [{'key': 'program_course_key'}]},
            {'subjects': []},
            [],
        ),
    )
    @ddt.unpack
    def test_get_program_subjects(self, program_metadata, course_metadata, expected_subjects):
        """
        Assert that the Subjects associated with a program are properly parsed.
        """
        ContentMetadataFactory.create(
            content_key=program_metadata['courses'][0]['key'],
            content_type=COURSE,
            json_metadata=course_metadata,
        )
        program_subjects = get_program_subjects(program_metadata)
        self.assertEqual(sorted(expected_subjects), sorted(program_subjects))

    @ddt.data(
        (
            {'courses': [
                {'key': 'program_course_key1'},
                {'key': 'program_course_key2'},
                {'key': 'program_course_key3'},
            ]},
            [
                {'key': 'program_course_key1', 'level_type': 'Intermediate'},
                {'key': 'program_course_key2', 'level_type': 'Intermediate'},
                {'key': 'program_course_key3', 'level_type': 'Introductory'},
            ],
            'Intermediate',
        ),
        (
            {'courses': [
                {'key': 'program_course_key1'},
                {'key': 'program_course_key2'},
                {'key': 'program_course_key3'},
            ]},
            [
                {'key': 'program_course_key1', 'level_type': None},
                {'key': 'program_course_key2', 'level_type': ''},
                {'key': 'program_course_key3', 'level_type': None},
            ],
            '',
        ),
    )
    @ddt.unpack
    def test_get_program_level_type(self, program_metadata, course_metadata, expected_level_type):
        """
        Assert that the level_type associated with a program is properly parsed.
        """
        for i in range(3):
            ContentMetadataFactory.create(
                content_key=program_metadata['courses'][i]['key'],
                content_type=COURSE,
                json_metadata=course_metadata[i],
            )
        program_level_type = get_program_level_type(program_metadata)
        self.assertEqual(expected_level_type, program_level_type)
