"""
Utilities for firing segment events.
"""
from enterprise_catalog.apps.track.segment import track_anonymous_event


def track_ai_curation(task_id, event_name, properties):
    """
    Track AI curation events.
    """
    track_anonymous_event(
        anonymous_id=task_id,
        event_name=event_name,
        properties=properties
    )
