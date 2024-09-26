"""
Models for job app.
"""
from uuid import uuid4

from django.db import models
from django.utils.translation import gettext as _
from model_utils.models import TimeStampedModel
from simple_history.models import HistoricalRecords


class Job(models.Model):
    """
    Model for storing job related information.

    .. no_pii:
    """
    title = models.CharField(max_length=255, help_text=_('Job title'))
    description = models.TextField(help_text=_('Job description.'))

    class Meta:
        verbose_name = _('Job')
        verbose_name_plural = _('Jobs')
        app_label = 'job'

    def __str__(self):
        """
            Return human-readable string representation.
        """

        return f'<Job title="{self.title}">'


class EnterpriseCustomer(TimeStampedModel):
    """
    Model for storing enterprise related information.

    .. no_pii:
    """
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=255, blank=False, null=False, help_text=_("Enterprise Customer name."))
    slug = models.SlugField(
        max_length=30, unique=True, default='default',
        help_text=(
            'A short string uniquely identifying this enterprise. '
        )
    )

    jobs = models.ManyToManyField(Job, related_name='enterprise_customers')

    history = HistoricalRecords()

    class Meta:
        app_label = 'job'
        verbose_name = _("Enterprise Customer")
        verbose_name_plural = _("Enterprise Customers")

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return "<EnterpriseCustomer {code:x}: {name}>".format(code=self.uuid.time_low, name=self.name)

    def __repr__(self):
        """
        Return uniquely identifying string representation.
        """
        return self.__str__()
