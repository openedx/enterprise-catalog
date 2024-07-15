"""
Management command for fetching video skills from taxonomy connector
"""
import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.video_catalog.models import Video, VideoSkill
from enterprise_catalog.apps.video_catalog.utils import store_video_skills


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command for fetching video skills from taxonomy connector

    Example Usage:
    >> python manage.py fetch_video_skills
    """
    help = (
        'Fetch the skills associated with videos from taxonomy connector'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            default=False,
            action='store_true',
            help='Force execution and re-process any previously processed rows.',
        )

    def handle(self, *args, **options):
        """
        Fetch the skills associated with videos from taxonomy connector.
        """
        processed_videos = VideoSkill.objects.all().values_list('video__edx_video_id', flat=True)
        videos = Video.objects.exclude(edx_video_id__in=processed_videos)
        if options.get('force', False):
            videos = Video.objects.all()
        for video in videos:
            try:
                store_video_skills(video)
                logger.info(
                    '[FETCH_VIDEO_SKILLS] Skills for Video id: "%s" saved successfully.',
                    video.edx_video_id
                )
            except Exception as ex:  # pylint: disable=broad-exception-caught
                logger.error(
                    '[FETCH_VIDEO_SKILLS] Failure in storing Skills for Video id: "%s". Ex:  "%s".',
                    video.edx_video_id,
                    str(ex)
                )
