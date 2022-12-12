from edx_rbac.utils import get_decoded_jwt

from enterprise_catalog.apps.track.segment import track_event


def track_highlight_set_changes(request, highlight_set, event_name, additional_properties=None):
    """
    Send tracking events for changes to a highlight set.

    Args:
        highlight_set (HighlightSet): The HighlightSet to describe.
        event_name (str):
            Name of the event in the format of: edx.server.enterprise-catalog.highlight-set-lifecycle.<new-status>, see
            constants.SegmentEvents.
        additional_properties: (dict):
            Additional properties to track for each event, overrides default fields.

    Returns:
        None
    """
    if not additional_properties:
        additional_properties = {}
    default_event_properties = {
        'highlight_set_uuid': str(highlight_set.uuid),
        'enterprise_customer_uuid': str(highlight_set.enterprise_curation.enterprise_uuid),
        'enterprise_curation_uuid': str(highlight_set.enterprise_curation.uuid),
    }
    event_properties = {**default_event_properties, **additional_properties}
    decoded_jwt = get_decoded_jwt(request)
    lms_user_id = decoded_jwt.get('user_id')
    track_event(lms_user_id, event_name, event_properties)
