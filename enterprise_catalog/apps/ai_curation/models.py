"""
Models for AI Curation
"""
from datetime import timedelta

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone
from model_utils.models import TimeStampedModel

from enterprise_catalog.apps.ai_curation.enums import AICurationStatus


class AICurationTask(TimeStampedModel):
    """
    Model for AI Curation Task.

    .. no_pii:
    """
    task_id = models.UUIDField(primary_key=True, editable=False, unique=True)
    status = models.CharField(max_length=255, choices=AICurationStatus.choices, default=AICurationStatus.PENDING)
    payload = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    result = models.JSONField(default=dict, encoder=DjangoJSONEncoder)

    class Meta:
        """
        Meta class for AI Curation Task.
        """
        verbose_name = 'AI Curation Task'
        verbose_name_plural = 'AI Curation Tasks'

    def __str__(self):
        return f'AICurationTask {self.task_id}'

    @classmethod
    def clear_outdated_entries(cls):
        """
        Remove entries older than a week.
        """
        cls.objects.filter(created__lt=timezone.now() - timedelta(days=7)).delete()
