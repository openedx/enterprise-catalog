import ddt
from django.test import TestCase

from enterprise_catalog.apps.api.v1.utils import (
    get_course_card_image_url,
    get_course_partners,
    get_course_subjects,
)


@ddt.ddt
class EnterpriseCatalogApiUtilsTests(TestCase):
    """
    Tests for enterprise_catalog.apps.api.v1.utils.
    """

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
