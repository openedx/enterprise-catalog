"""
Models for job app.
"""
from django.db import models
from django.utils.translation import gettext as _
from model_utils.models import TimeStampedModel
from simple_history.models import HistoricalRecords


class Job(TimeStampedModel):
    """
    Model for storing job related information.

    .. no_pii:
    """
    job_id = models.IntegerField(unique=True, help_text=_('The job ID received from API.'))
    external_id = models.CharField(
        max_length=255,
        unique=True,
        help_text=_(
            'The external identifier for the job received from API.'
        )
    )
    title = models.CharField(max_length=255, help_text=_('Job title'))
    description = models.TextField(help_text=_('Job description.'))

    history = HistoricalRecords()

    class Meta:
        verbose_name = _('Job')
        verbose_name_plural = _('Jobs')
        app_label = 'jobs'

    def __str__(self):
        """
            Return human-readable string representation.
        """

        return f'<Job id="{self.job_id}">'


class JobSkill(TimeStampedModel):
    """
    Stores the skills associated with a Job.

    .. no_pii:
    """
    job = models.ForeignKey(
        Job,
        related_name='skills',
        on_delete=models.CASCADE,
    )
    skill_id = models.CharField(max_length=255, help_text=_('Skill id'))
    name = models.CharField(max_length=255, help_text=_('Skill name'))
    significance = models.FloatField(
        blank=False,
        help_text=_(
            'The significance of skill for the job.'
        )
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Job Skill")
        verbose_name_plural = _("Job Skills")
        app_label = 'jobs'

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return (
            "<JobSkill for '{job_id} and {skill_id}'>".format(
                job_id=str(self.job),
                skill_id=self.skill_id
            )
        )


class JobEnterprise(TimeStampedModel):
    """
    Stores the enterprises associated with a Job.

    .. no_pii:
    """
    job = models.ForeignKey(
        Job,
        related_name='enterprises',
        on_delete=models.CASCADE,
    )
    enterprise_uuid = models.UUIDField()

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Job Enterprise")
        verbose_name_plural = _("Job Enterprises")
        app_label = 'jobs'

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return (
            "<JobEnterprise for '{job_id} and {enterprise_id}'>".format(
                job_id=str(self.job),
                enterprise_id=str(self.enterprise_uuid)
            )
        )
