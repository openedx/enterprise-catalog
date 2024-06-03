"""
Models for the video catalog application.
"""
import collections

from django.db import models
from django.utils.translation import gettext as _
from jsonfield.encoder import JSONEncoder
from jsonfield.fields import JSONField
from model_utils.models import TimeStampedModel
from simple_history.models import HistoricalRecords

from enterprise_catalog.apps.catalog.models import ContentMetadata


class Video(TimeStampedModel):
    """
    Model to store data for videos associated with content.

    .. no_pii:
    """
    edx_video_id = models.CharField(primary_key=True, max_length=255, help_text=_('EdX video id'))
    client_video_id = models.CharField(max_length=255, help_text=_('Client video id'))
    parent_content_metadata = models.OneToOneField(
        ContentMetadata,
        related_name='parent_metadata',
        on_delete=models.DO_NOTHING,
    )
    json_metadata = JSONField(
        default={},
        blank=True,
        null=True,
        load_kwargs={'object_pairs_hook': collections.OrderedDict},
        dump_kwargs={'indent': 4, 'cls': JSONEncoder, 'separators': (',', ':')},
        help_text=_(
            "The metadata about a particular video as retrieved from the LMS service, "
            "specified as a JSON object."
        )
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _('Video')
        verbose_name_plural = _('Videos')
        app_label = 'video_catalog'

    def __str__(self):
        """
            Return human-readable string representation.
        """

        return f'<Video edx_video_id="{self.edx_video_id}">'


class VideoTranscriptSummary(TimeStampedModel):
    """
    Stores the AI generated summary of video transcript.

    .. no_pii:
    """
    video = models.ForeignKey(
        Video,
        blank=True,
        null=True,
        related_name='summary_transcripts',
        on_delete=models.deletion.SET_NULL,
    )
    summary = models.TextField(help_text=_('Video transcript summary'))

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Video Transcript Summary")
        verbose_name_plural = _("Video Transcript Summaries")
        app_label = 'video_catalog'

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return (
            "<VideoTranscriptSummary for '{video_id}'>".format(
                video_id=str(self.video)
            )
        )
