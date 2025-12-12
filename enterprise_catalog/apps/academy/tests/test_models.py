"""
Tests for Academy app models.
"""
from django.test import TestCase

from enterprise_catalog.apps.academy.tests.factories import (
    AcademyFactory,
    TagFactory,
)


class TagModelTests(TestCase):
    """
    Tests for the Tag model.
    """

    def test_tag_str_method(self):
        """
        Test that the Tag __str__ method returns the expected format.
        """
        tag = TagFactory(title='Test Tag')
        expected_str = '<Tag title="Test Tag">'
        self.assertEqual(str(tag), expected_str)


class AcademyModelTests(TestCase):
    """
    Tests for the Academy model.
    """

    def test_academy_creation(self):
        """
        Test that an Academy can be created successfully.
        """
        academy = AcademyFactory(title='Test Academy')
        self.assertIsNotNone(academy.uuid)
        self.assertEqual(academy.title, 'Test Academy')
