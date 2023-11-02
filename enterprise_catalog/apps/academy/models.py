"""
Models for academy app.
"""
from uuid import uuid4

from django.db import models
from django.utils.translation import gettext as _
from model_utils.models import TimeStampedModel
from simple_history.models import HistoricalRecords

from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


class Tag(models.Model):
    """
    Model that can be used to tag records on any model.

    .. no_pii:
    """
    title = models.CharField(max_length=255, help_text=_('Tag title'))
    description = models.TextField(help_text=_('Tag description.'))

    class Meta:
        verbose_name = _('Tag')
        verbose_name_plural = _('Tags')
        app_label = 'academy'

    def __str__(self):
        """
            Return human-readable string representation.
        """

        return f'<Tag title="{self.title}">'


class Academy(TimeStampedModel):
    """
    Model for storing academy related information.

    .. no_pii:
    """
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    title = models.CharField(max_length=255, help_text=_('Academy title'))
    enterprise_catalogs = models.ManyToManyField(EnterpriseCatalog, related_name='academies')
    short_description = models.TextField(help_text=_('Short description of the academy.'))
    long_description = models.TextField(help_text=_('Long description of the academy.'))
    image = models.URLField(help_text=_('URL of the image shown on academy card on the frontend.'))

    tags = models.ManyToManyField(Tag, related_name='academies')

    history = HistoricalRecords()

    class Meta:
        verbose_name = _('Academy')
        verbose_name_plural = _('Academies')
        app_label = 'academy'

    def __str__(self):
        """
            Return human-readable string representation.
        """

        return f'<Academy UUID="{self.uuid}">'
