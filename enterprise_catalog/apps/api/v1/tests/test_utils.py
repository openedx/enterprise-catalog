import ddt
from django.test import TestCase

from enterprise_catalog.apps.api.v1.utils import get_course_subjects


@ddt.ddt
class EnterpriseCatalogApiUtilsTests(TestCase):
    """
    Tests for enterprise_catalog.apps.api.v1.utils.
    """

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
