"""
Factories for AI Curation app.
"""
from uuid import uuid4

import factory
from django_celery_results.models import TaskResult


class TaskResultFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `AICurationTask` model
    """
    class Meta:
        model = TaskResult

    task_id = factory.LazyFunction(uuid4)
