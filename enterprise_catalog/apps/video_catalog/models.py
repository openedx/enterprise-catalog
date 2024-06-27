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

    Here is sample json_metadata:
    ```json
    {
      "client_video_id": "style-720p.mp4",
      "course_video_image_url": "https://prod-images.edx-video.net/video-images/a1be2e276d3e40598e3d4a5d67d30a69.png",
      "created": "2024-01-04 03:27:55+00:00",
      "duration": 694.593,
      "edx_video_id": "d289bdea-5c23-4e1b-8954-cb55ba7772c5",
      "error_description": null,
      "status": "Ready",
      "file_size": 67700414,
      "download_link": "https://edx-video.net/d289bdea-5c23-4e1b-8954-cb55ba7772c5-mp4_720p.mp4",
      "transcript_urls": {
        "ar": "https://example.com/video-transcripts/d289bdea-5c23-4e1b-8954-cb55ba7772c5_ar.sjson",
        "de": "https://example.com/video-transcripts/d289bdea-5c23-4e1b-8954-cb55ba7772c5_de.sjson",
        "en": "https://example.com/video-transcripts/53149c10ad7b46f1b70c528f333fd681.sjson",
        "es": "https://example.com/video-transcripts/d289bdea-5c23-4e1b-8954-cb55ba7772c5_es.sjson",
        "fr": "https://example.com/video-transcripts/d289bdea-5c23-4e1b-8954-cb55ba7772c5_fr.sjson",
        "hi": "https://example.com/video-transcripts/d289bdea-5c23-4e1b-8954-cb55ba7772c5_hi.sjson",
        "id": "https://example.com/video-transcripts/d289bdea-5c23-4e1b-8954-cb55ba7772c5_id.sjson",
        "pt": "https://example.com/video-transcripts/d289bdea-5c23-4e1b-8954-cb55ba7772c5_pt.sjson",
        "sw": "https://example.com/video-transcripts/d289bdea-5c23-4e1b-8954-cb55ba7772c5_sw.sjson",
        "te": "https://example.com/video-transcripts/d289bdea-5c23-4e1b-8954-cb55ba7772c5_te.sjson",
        "tr": "https://example.com/video-transcripts/d289bdea-5c23-4e1b-8954-cb55ba7772c5_tr.sjson",
        "zh": "https://example.com/video-transcripts/d289bdea-5c23-4e1b-8954-cb55ba7772c5_zh.sjson"
      },
      "transcription_status": "",
      "transcripts": [
        "ar",
        "de",
        "en",
        "es",
        "fr",
        "hi",
        "id",
        "pt",
        "sw",
        "te",
        "tr",
        "zh"
      ]
    }
    ```

    .. no_pii:
    """
    edx_video_id = models.CharField(primary_key=True, max_length=255, help_text=_('EdX video id'))
    client_video_id = models.CharField(max_length=255, help_text=_('Client video id'))
    video_usage_key = models.CharField(max_length=255, help_text=_('Video Xblock Usage Key'))
    parent_content_metadata = models.ForeignKey(
        ContentMetadata,
        related_name='videos',
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


class VideoShortlist(models.Model):
    """
    Stores the shortlisted videos for microlearning index and search.

    Example video_usage_key
    block-v1:UnivX+QMB1+2T2017+type@video+block@0accf77cf6634c93b0f095f65fed41a1

    .. no_pii:
    """
    video_usage_key = models.CharField(primary_key=True, max_length=255, help_text=_('Video Xblock Usage Key'))

    class Meta:
        verbose_name = _("Shortlisted Video")
        verbose_name_plural = _("Shortlisted Videos")
        app_label = 'video_catalog'

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return (
            "<VideoShortlist for '{usage_key}'>".format(
                usage_key=str(self.video_usage_key)
            )
        )
