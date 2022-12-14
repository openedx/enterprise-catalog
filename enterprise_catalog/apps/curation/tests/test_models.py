"""
Tests for curation models
"""

import ddt
from django.test import TestCase

from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    LEARNER_PATHWAY,
    PROGRAM,
)
from enterprise_catalog.apps.catalog.models import ContentMetadata
from enterprise_catalog.apps.catalog.tests.factories import (
    FAKE_CONTENT_AUTHOR_NAME,
    FAKE_CONTENT_AUTHOR_UUID,
    ContentMetadataFactory,
)
from enterprise_catalog.apps.curation.models import HighlightedContent
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
        # COURSE_RUN and LEARNER_PATHWAY intentionally untested because they are unsupported.
    )
    @ddt.unpack
    def test_authoring_organizations(self, content_type):
        """
        Ensure that authoring_organiztaions() returns the test content author defined in test factories from the catalog
        app.
        """
        content_metadata = ContentMetadataFactory(content_type=content_type)
        highlighted_content = HighlightedContentFactory(content_metadata=content_metadata)
        authoring_organizations_under_test = highlighted_content.authoring_organizations
        assert authoring_organizations_under_test[0]['uuid'] == str(FAKE_CONTENT_AUTHOR_UUID)
        assert authoring_organizations_under_test[0]['name'] == FAKE_CONTENT_AUTHOR_NAME
        assert authoring_organizations_under_test[0]['logo_image_url'].startswith('https://')
        assert authoring_organizations_under_test[0]['logo_image_url'].endswith('.jpg')

    @ddt.data(
        {'content_type': COURSE, 'content_title': 'Test Course Title'},
        {'content_type': COURSE_RUN, 'content_title': 'Test Courserun Title'},
        {'content_type': PROGRAM, 'content_title': 'Test Program Title'},
        {'content_type': LEARNER_PATHWAY, 'content_title': 'Test Learner Pathway Title'},
    )
    @ddt.unpack
    def test_title(self, content_type, content_title):
        """
        Ensure that the title property is correctly found from within the content metadata.
        """
        content_metadata = ContentMetadataFactory(content_type=content_type, title=content_title)
        highlighted_content = HighlightedContentFactory(content_metadata=content_metadata)
        assert highlighted_content.title == content_title

    @ddt.data(
        {'content_type': COURSE},
        {'content_type': COURSE_RUN},
        {'content_type': PROGRAM},
        {'content_type': LEARNER_PATHWAY},
    )
    @ddt.unpack
    def test_card_image_url(self, content_type):
        """
        Ensure that the card_image_url property is correctly found from within the content metadata.
        """
        test_card_image_url = 'https://example.com/card_image_url.jpg'
        content_metadata = ContentMetadataFactory(content_type=content_type, card_image_url=test_card_image_url)
        highlighted_content = HighlightedContentFactory(content_metadata=content_metadata)
        assert highlighted_content.card_image_url == test_card_image_url

    @ddt.data(
        {'content_type': COURSE, 'url_is_null': True},
        {'content_type': COURSE, 'url_is_null': False},
        {'content_type': COURSE_RUN, 'url_is_null': True},
        {'content_type': COURSE_RUN, 'url_is_null': False},
        {'content_type': PROGRAM, 'url_is_null': True},
        {'content_type': PROGRAM, 'url_is_null': False},
        {'content_type': LEARNER_PATHWAY, 'url_is_null': True},
        {'content_type': LEARNER_PATHWAY, 'url_is_null': False},
    )
    @ddt.unpack
    def test_missing_card_image_url(self, content_type, url_is_null):
        """
        Ensure that a missing card_image_url property does not crash the request.
        """
        # Setup some base ContentMetadata and HighlightedContent objects.
        if url_is_null:
            # Create a content metadata object with a (JSON) null card image URL.
            if content_type == LEARNER_PATHWAY:
                # LEARNER_PATHWAY is a special case because we expect the top-level key to be set to null, not the
                # nested `url` leaf key.
                content_metadata = ContentMetadataFactory(content_type=content_type)
                content_metadata_orm_object = ContentMetadata.objects.get(content_key=content_metadata.content_key)
                content_metadata_orm_object.json_metadata['card_image'] = None
                content_metadata_orm_object.save()
            else:
                content_metadata = ContentMetadataFactory(content_type=content_type, card_image_url=None)
        else:
            # Create the content metdata object, but also edit it to remove the card image url field.
            content_metadata = ContentMetadataFactory(content_type=content_type)
            content_metadata_orm_object = ContentMetadata.objects.get(content_key=content_metadata.content_key)
            for k in ('card_image', 'card_image_url', 'image_url'):
                try:
                    del content_metadata_orm_object.json_metadata[k]
                except KeyError:
                    pass
            content_metadata_orm_object.save()
        highlighted_content = HighlightedContentFactory(content_metadata=content_metadata)
        # Make sure no 500 error is thrown when attempting to pull up a card_image_url.
        highlighted_content_orm_object = HighlightedContent.objects.get(uuid=highlighted_content.uuid)
        assert highlighted_content_orm_object.card_image_url is None
