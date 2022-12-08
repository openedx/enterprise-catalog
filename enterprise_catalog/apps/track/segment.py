"""
Wrapper methods for emitting events to Segment.
"""
import logging

import analytics
from django.conf import settings


logger = logging.getLogger(__name__)


def track_event(lms_user_id, event_name, properties):
    """
    Send a tracking event to segment

    Args:
        lms_user_id (str): LMS User ID of the user we want tracked with this event for cross-platform tracking.
        event_name (str): Name of the event.
        properties (dict): All the properties of an event.

    Returns:
        None
    """
    if hasattr(settings, "SEGMENT_KEY") and settings.SEGMENT_KEY:
        try:  # We should never raise an exception when not able to send a tracking event.
            analytics.track(user_id=lms_user_id, event=event_name, properties=properties)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception(exc)
    else:
        logger.warning(
            "Segment event %s for user_id %s not tracked because SEGMENT_KEY not set", event_name, lms_user_id
        )
