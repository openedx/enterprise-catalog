"""
Tests for curation models
"""

import ddt
from django.test import TestCase

from enterprise_catalog.apps.catalog.constants import COURSE, PROGRAM
from enterprise_catalog.apps.catalog.tests.factories import (
    FAKE_CONTENT_AUTHOR_NAME,
    FAKE_CONTENT_AUTHOR_UUID,
    ContentMetadataFactory,
)
from enterprise_catalog.apps.curation.tests.factories import (
    HighlightedContentFactory,
)


@ddt.ddt
class TestModels(TestCase):
    """
    curation models tests
    """

    @ddt.data(
        {'content_type': COURSE},
        {'content_type': PROGRAM},
    )
    @ddt.unpack
    def test_authoring_organizations(self, content_type):
        content_metadata = ContentMetadataFactory(
            content_key='edX+testX',
            content_type=content_type,
        )
        highlighted_content = HighlightedContentFactory(content_metadata=content_metadata)
        authoring_organizations_under_test = highlighted_content.authoring_organizations
        self.assertEqual(authoring_organizations_under_test[0]['uuid'], str(FAKE_CONTENT_AUTHOR_UUID))
        self.assertEqual(authoring_organizations_under_test[0]['name'], FAKE_CONTENT_AUTHOR_NAME)
        self.assertTrue(authoring_organizations_under_test[0]['logo_image_url'].startswith('https://'))
        self.assertTrue(authoring_organizations_under_test[0]['logo_image_url'].endswith('.jpg'))
