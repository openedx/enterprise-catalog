"""
Initialization app for enterprise_catalog.apps.track.
"""
import logging

import analytics
from django.apps import AppConfig
from django.conf import settings


logger = logging.getLogger(__name__)


class TrackConfig(AppConfig):
    """
    Application Configuration for the track app.
    """
    name = 'track'
    default = False

    def ready(self):
        """
        Initialize Segment analytics module by setting the write_key.
        """
        if getattr(settings, 'SEGMENT_KEY', None):
            logger.debug("Found segment key, setting up analytics library")
            analytics.write_key = settings.SEGMENT_KEY
