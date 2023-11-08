from uuid import uuid4

import factory
from factory.fuzzy import FuzzyText

from enterprise_catalog.apps.academy.models import Academy, Tag
from enterprise_catalog.apps.catalog.tests.factories import (
    EnterpriseCatalogFactory,
)


class TagFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `Tag` model
    """
    class Meta:
        model = Tag


class AcademyFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `Academy` model
    """
    class Meta:
        model = Academy

    uuid = factory.LazyFunction(uuid4)
    title = FuzzyText(length=32)
    short_description = FuzzyText(length=32)
    long_description = FuzzyText(length=255)
    enterprise_catalogs = factory.RelatedFactoryList(
        EnterpriseCatalogFactory,
        size=4,
    )
    tags = factory.RelatedFactoryList(
        TagFactory,
        size=4,
    )
