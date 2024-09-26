from uuid import uuid4

import factory
from factory.fuzzy import FuzzyText

from enterprise_catalog.apps.jobs.models import EnterpriseCustomer, Job


class JobFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `Job` model
    """
    class Meta:
        model = Job

    title = FuzzyText(length=32)
    description = FuzzyText(length=255)


class EnterpriseCustomerFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `EnterpriseCustomer` model
    """
    class Meta:
        model = EnterpriseCustomer

    uuid = factory.LazyFunction(uuid4)
    name = FuzzyText(length=32)
    slug = FuzzyText(length=32)
