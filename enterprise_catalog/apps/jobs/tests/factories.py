from uuid import uuid4

import factory
from factory.fuzzy import FuzzyInteger, FuzzyText

from enterprise_catalog.apps.jobs.models import Job, JobEnterprise, JobSkill


class JobFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `Job` model
    """
    class Meta:
        model = Job

    job_id = FuzzyInteger(0, 100)
    title = FuzzyText(length=32)
    description = FuzzyText(length=255)


class JobEnterpriseFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `JobEnterprise` model
    """
    class Meta:
        model = JobEnterprise

    enterprise_uuid = factory.LazyFunction(uuid4)
    job = factory.SubFactory(JobFactory)


class JobSkillFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `JobSkill` model
    """
    class Meta:
        model = JobSkill

    skill_id = FuzzyText(length=32)
    name = FuzzyText(length=32)
    significance = FuzzyInteger(0, 100)
