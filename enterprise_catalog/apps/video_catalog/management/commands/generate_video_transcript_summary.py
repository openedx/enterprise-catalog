"""
Management command to generate a summary of video transcripts for all videos in the system.
"""
import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.video_catalog.models import (
    Video,
    VideoTranscriptSummary,
)
from enterprise_catalog.apps.video_catalog.utils import (
    generate_transcript_summary,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command to generate a summary of video transcripts for all videos in the system.

    Example Usage:
    >> python manage.py generate_video_transcript_summary
    """
    help = (
        'Generate a summary of video transcripts for all videos in the system.'
    )

    def handle(self, *args, **options):
        """
        Generate a summary of video transcripts for all videos in the system.
        """
        logger.info("Generating video transcript summaries...")
        processed_videos = VideoTranscriptSummary.objects.all().values_list('video_id', flat=True)
        videos = Video.objects.exclude(edx_video_id__in=processed_videos)
        for video in videos:
            try:
                summary = generate_transcript_summary(video)
                if summary:
                    VideoTranscriptSummary.objects.create(video=video, summary=summary)
            except Exception as ex:  # pylint: disable=broad-exception-caught
                logger.error(
                    '[FETCH_VIDEO_TRANSCRIPT_SUMMARY] Failure in generating transcript \
                    summary for Video id: "%s". Ex:  "%s".',
                    video.edx_video_id,
                    str(ex)
                )
