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

    @factory.post_generation
    def enterprise_catalogs(self, create, extracted, **kwargs):  # pylint: disable=unused-argument
        if extracted:
            for enterprise_catalog in extracted:
                self.enterprise_catalogs.add(enterprise_catalog)  # pylint: disable=no-member
        else:
            enterprise_catalog1 = EnterpriseCatalogFactory()
            enterprise_catalog2 = EnterpriseCatalogFactory()
            self.enterprise_catalogs.set([enterprise_catalog1, enterprise_catalog2])  # pylint: disable=no-member

    @factory.post_generation
    def tags(self, create, extracted, **kwargs):  # pylint: disable=unused-argument
        if extracted:
            for tag in extracted:
                self.tags.add(tag)  # pylint: disable=no-member
        else:
            tag1 = TagFactory()
            tag2 = TagFactory()
            self.tags.set([tag1, tag2])  # pylint: disable=no-member
