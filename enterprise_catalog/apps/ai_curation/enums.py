"""
Enums for AI Curation.
"""
from django.db import models


class AICurationStatus(models.TextChoices):
    """
    Enum for AI Curation status.
    """
    PENDING = 'PENDING'
    IN_PROGRESS = 'IN_PROGRESS'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'
