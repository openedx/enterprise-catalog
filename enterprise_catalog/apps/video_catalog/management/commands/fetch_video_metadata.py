"""
Management command for fetching video metadata from LMS
"""
import logging

from django.core.management.base import BaseCommand
from rest_framework.exceptions import ValidationError

from enterprise_catalog.apps.video_catalog.models import VideoShortlist
from enterprise_catalog.apps.video_catalog.utils import fetch_video


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command for fetching video metadata from LMS

    Example Usage:
    >> python manage.py fetch_video_metadata
    """
    help = (
        'Fetch video content metadata from LMS'
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
        Fetch video content metadata from LMS.
        """
        shortlisted_videos = VideoShortlist.objects.filter(is_processed=False)
        if options.get('force', False):
            shortlisted_videos = VideoShortlist.objects.all()
        for shorlisted_video in shortlisted_videos:
            try:
                fetch_video(shorlisted_video)
                shorlisted_video.is_processed = True
                shorlisted_video.save()
            except ValidationError:
                logger.error(
                    '[FETCH_VIDEO_METADATA] Video usage key:  "%s" could not be validated.',
                    shorlisted_video.video_usage_key
                )
