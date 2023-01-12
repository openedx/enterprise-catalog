"""
Test factories for curation models
"""

from uuid import uuid4

import factory
from factory.fuzzy import FuzzyText

from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)
from enterprise_catalog.apps.curation.models import (
    EnterpriseCurationConfig,
    HighlightedContent,
    HighlightSet,
)


class EnterpriseCurationConfigFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `EnterpriseCurationConfig` model
    """
    class Meta:
        model = EnterpriseCurationConfig

    uuid = factory.LazyFunction(uuid4)
    title = FuzzyText(length=255)
    enterprise_uuid = factory.LazyFunction(uuid4)
    is_highlight_feature_active = True
    can_only_view_highlight_sets = False


class HighlightSetFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `HighlightSet` model
    """
    class Meta:
        model = HighlightSet

    uuid = factory.LazyFunction(uuid4)
    title = FuzzyText(length=255)
    enterprise_curation = factory.SubFactory(EnterpriseCurationConfigFactory)
    is_published = True


class HighlightedContentFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `HighlightedContent` model
    """
    class Meta:
        model = HighlightedContent

    uuid = factory.LazyFunction(uuid4)
    catalog_highlight_set = factory.SubFactory(HighlightSetFactory)
    content_metadata = factory.SubFactory(ContentMetadataFactory)
